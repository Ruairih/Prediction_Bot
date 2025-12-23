#!/usr/bin/env python3
"""
CLI command for syncing Polymarket positions to local database.

Usage:
    # Dry run (see what would change)
    python -m polymarket_bot.sync_positions --wallet 0x... --dry-run

    # Actual sync with default policy (7-day hold starts fresh)
    python -m polymarket_bot.sync_positions --wallet 0x...

    # Sync with mature policy (exit logic applies immediately)
    python -m polymarket_bot.sync_positions --wallet 0x... --policy mature
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Sync Polymarket positions to local database"
    )
    parser.add_argument(
        "--wallet",
        type=str,
        help="Wallet address to sync (defaults to funder from polymarket_api_creds.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without making changes",
    )
    parser.add_argument(
        "--policy",
        choices=["new", "mature"],
        default="new",
        help="Hold policy: 'new' = 7-day hold starts fresh (default), 'mature' = exit logic applies immediately",
    )
    parser.add_argument(
        "--mature-days",
        type=int,
        default=8,
        help="Days to backdate if policy=mature (default: 8)",
    )

    args = parser.parse_args()

    # Get wallet address
    wallet_address = args.wallet
    if not wallet_address:
        # Try to load from credentials file
        creds_file = "polymarket_api_creds.json"
        if os.path.exists(creds_file):
            with open(creds_file) as f:
                creds = json.load(f)
                wallet_address = creds.get("funder")
                if wallet_address:
                    logger.info(f"Using funder address from {creds_file}: {wallet_address}")

    if not wallet_address:
        logger.error("No wallet address provided. Use --wallet or set funder in polymarket_api_creds.json")
        sys.exit(1)

    # Get database URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try loading from .env
        if os.path.exists(".env"):
            with open(".env") as f:
                for line in f:
                    if line.startswith("DATABASE_URL="):
                        database_url = line.split("=", 1)[1].strip()
                        break

    if not database_url:
        logger.error("DATABASE_URL not set. Set environment variable or add to .env")
        sys.exit(1)

    # Import here to avoid import errors if deps missing
    from polymarket_bot.storage.database import Database, DatabaseConfig
    from polymarket_bot.execution.position_sync import PositionSyncService
    from polymarket_bot.execution.position_tracker import PositionTracker

    # Initialize database
    logger.info("Connecting to database...")
    config = DatabaseConfig(url=database_url)
    db = Database(config)
    await db.initialize()

    try:
        # Create services
        position_tracker = PositionTracker(db)
        sync_service = PositionSyncService(db, position_tracker)

        # Show current state
        logger.info("=" * 60)
        logger.info("POLYMARKET POSITION SYNC")
        logger.info("=" * 60)
        logger.info(f"Wallet: {wallet_address}")
        logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        logger.info(f"Policy: {args.policy}")
        if args.policy == "mature":
            logger.info(f"Mature Days: {args.mature_days}")
        logger.info("=" * 60)

        # Run sync
        result = await sync_service.sync_positions(
            wallet_address=wallet_address,
            dry_run=args.dry_run,
            hold_policy=args.policy,
            mature_days=args.mature_days,
        )

        # Show results
        logger.info("")
        logger.info("=" * 60)
        logger.info("SYNC RESULTS")
        logger.info("=" * 60)
        logger.info(f"Run ID: {result.run_id}")
        logger.info(f"Positions found on Polymarket: {result.positions_found}")
        logger.info(f"Positions imported: {result.positions_imported}")
        logger.info(f"Positions updated: {result.positions_updated}")
        logger.info(f"Positions closed: {result.positions_closed}")
        if result.errors:
            logger.warning(f"Errors: {len(result.errors)}")
            for err in result.errors:
                logger.error(f"  - {err}")
        logger.info(f"Duration: {(result.completed_at - result.started_at).total_seconds():.1f}s")
        logger.info("=" * 60)

        if args.dry_run and result.positions_imported > 0:
            logger.info("")
            logger.info("To apply these changes, run without --dry-run:")
            logger.info(f"  python -m polymarket_bot.sync_positions --wallet {wallet_address}")

        # Show exit logic preview for imported positions
        if not args.dry_run and result.positions_imported > 0:
            logger.info("")
            logger.info("EXIT LOGIC PREVIEW:")
            if args.policy == "new":
                logger.info("  - Imported positions will HOLD for 7 days")
                logger.info("  - After 7 days, profit target (99c) and stop loss (90c) apply")
            else:
                logger.info("  - Exit logic applies IMMEDIATELY")
                logger.info("  - Positions at 99c+ will trigger profit target exit")
                logger.info("  - Positions at 90c- will trigger stop loss exit")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
