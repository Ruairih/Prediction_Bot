#!/usr/bin/env python3
"""Test script to check position timestamp corrections."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from polymarket_bot.storage.database import Database
from polymarket_bot.execution.position_sync import PositionSyncService


async def main():
    # Load credentials to get wallet address
    creds_file = os.path.join(os.path.dirname(__file__), '..', 'polymarket_api_creds.json')
    if not os.path.exists(creds_file):
        print("ERROR: polymarket_api_creds.json not found")
        return

    with open(creds_file) as f:
        creds = json.load(f)

    wallet_address = creds.get("funder")
    if not wallet_address:
        print("ERROR: No 'funder' wallet address in credentials")
        return

    print(f"Wallet: {wallet_address}")
    print()

    # Connect to database
    from polymarket_bot.storage.database import DatabaseConfig
    db_url = os.environ.get("DATABASE_URL", "postgresql://predict:predict@localhost:5432/predict")
    db = Database(DatabaseConfig(url=db_url))
    await db.initialize()

    # Create sync service
    sync_service = PositionSyncService(db)

    # First, fetch trade timestamps to see what we have
    print("=" * 60)
    print("FETCHING TRADE HISTORY...")
    print("=" * 60)
    trade_timestamps = await sync_service.fetch_trade_timestamps(wallet_address)
    print(f"Found {len(trade_timestamps)} token trade timestamps")
    print()

    # Show current position ages vs actual ages
    print("=" * 60)
    print("CURRENT POSITIONS vs ACTUAL TIMESTAMPS")
    print("=" * 60)

    local_positions = await sync_service.get_local_positions()
    print(f"Found {len(local_positions)} open positions in database")
    print()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for token_id, local in sorted(local_positions.items(), key=lambda x: str(x[1].get("hold_start_at", ""))):
        actual_ts = trade_timestamps.get(token_id)

        hold_start = local.get("hold_start_at")
        if hold_start:
            if isinstance(hold_start, str):
                hold_start = datetime.fromisoformat(hold_start.replace("Z", "+00:00"))
            elif not hold_start.tzinfo:
                hold_start = hold_start.replace(tzinfo=timezone.utc)
            db_age = (now - hold_start).days
        else:
            db_age = "N/A"

        if actual_ts:
            actual_age = (now - actual_ts).days
        else:
            actual_age = "N/A"

        description = local.get("description", "Unknown")[:40]
        size = local.get("size", 0)

        needs_fix = "***FIX***" if db_age != actual_age and actual_ts else ""
        exit_ready = ">7d" if isinstance(actual_age, int) and actual_age > 7 else ""
        print(f"DB:{str(db_age):>3}d Actual:{str(actual_age):>3}d | {description:<40} | {needs_fix} {exit_ready}")

    print()

    # Run dry-run correction
    print("=" * 60)
    print("DRY RUN CORRECTION")
    print("=" * 60)
    result = await sync_service.correct_hold_timestamps(wallet_address, dry_run=True)
    print(f"Would correct: {result['corrected']} positions")
    print(f"Errors: {result['errors']}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
