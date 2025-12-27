"""
Market Sync Service with scheduling, locking, and status tracking.

This service runs as a background process to keep market data fresh.
Uses PostgreSQL advisory locks to prevent concurrent sync runs.

Usage:
    python -m explorer.services.sync_service

Environment variables:
    EXPLORER_DATABASE_URL - PostgreSQL connection string
    SYNC_INTERVAL_SECONDS - Full sync interval (default: 300 = 5 min)
    SYNC_PRICE_INTERVAL_SECONDS - Price-only sync interval (default: 30)
"""

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import httpx

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from explorer.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_service")

# Configuration
GAMMA_API = "https://gamma-api.polymarket.com"
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL_SECONDS", "300"))  # 5 min default
PRICE_SYNC_INTERVAL = int(os.environ.get("SYNC_PRICE_INTERVAL_SECONDS", "30"))
ADVISORY_LOCK_ID = 12345  # Unique lock ID for market sync


class SyncService:
    """Background service for syncing market data."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.running = True
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.lock_holder = f"{self.hostname}:{self.pid}"

    async def start(self):
        """Start the sync service."""
        logger.info("Starting Market Explorer Sync Service")
        logger.info(f"Full sync interval: {SYNC_INTERVAL}s, Price sync: {PRICE_SYNC_INTERVAL}s")

        # Connect to database
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=5,
        )
        logger.info("Database connection pool established")

        # Ensure schema exists
        await self._ensure_schema()

        # Run sync loops
        await asyncio.gather(
            self._full_sync_loop(),
            self._price_sync_loop(),
        )

    async def stop(self):
        """Stop the sync service gracefully."""
        logger.info("Stopping sync service...")
        self.running = False
        if self.pool:
            await self.pool.close()
        logger.info("Sync service stopped")

    async def _ensure_schema(self):
        """Ensure sync tracking tables exist."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS explorer_sync_runs (
                    id SERIAL PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,
                    duration_ms INT,
                    rows_fetched INT DEFAULT 0,
                    rows_upserted INT DEFAULT 0,
                    rows_failed INT DEFAULT 0,
                    error_message TEXT,
                    lock_acquired BOOLEAN DEFAULT TRUE,
                    locked_by TEXT,
                    api_calls INT DEFAULT 0,
                    api_retry_count INT DEFAULT 0
                )
            """)

    async def _acquire_lock(self, conn, lock_id: int) -> bool:
        """Try to acquire PostgreSQL advisory lock (non-blocking)."""
        result = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)",
            lock_id
        )
        return result

    async def _release_lock(self, conn, lock_id: int):
        """Release PostgreSQL advisory lock."""
        await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)

    async def _record_sync_start(self, conn, job_name: str) -> int:
        """Record sync job start, return run ID."""
        return await conn.fetchval("""
            INSERT INTO explorer_sync_runs (job_name, status, locked_by)
            VALUES ($1, 'running', $2)
            RETURNING id
        """, job_name, self.lock_holder)

    async def _record_sync_end(
        self,
        conn,
        run_id: int,
        status: str,
        rows_fetched: int = 0,
        rows_upserted: int = 0,
        rows_failed: int = 0,
        error_message: Optional[str] = None,
        api_calls: int = 0,
    ):
        """Record sync job completion."""
        await conn.execute("""
            UPDATE explorer_sync_runs
            SET status = $2,
                finished_at = NOW(),
                duration_ms = EXTRACT(MILLISECONDS FROM (NOW() - started_at))::INT,
                rows_fetched = $3,
                rows_upserted = $4,
                rows_failed = $5,
                error_message = $6,
                api_calls = $7
            WHERE id = $1
        """, run_id, status, rows_fetched, rows_upserted, rows_failed,
             error_message[:500] if error_message else None, api_calls)

    async def _record_sync_skipped(self, conn, job_name: str):
        """Record that sync was skipped due to lock."""
        await conn.execute("""
            INSERT INTO explorer_sync_runs (job_name, status, lock_acquired, finished_at)
            VALUES ($1, 'skipped', FALSE, NOW())
        """, job_name)

    async def _full_sync_loop(self):
        """Main loop for full market sync."""
        while self.running:
            try:
                await self._run_full_sync()
            except Exception as e:
                logger.error(f"Full sync error: {e}", exc_info=True)

            # Wait for next interval
            await asyncio.sleep(SYNC_INTERVAL)

    async def _price_sync_loop(self):
        """Loop for frequent price updates (lighter sync)."""
        # Offset from full sync to avoid collision
        await asyncio.sleep(PRICE_SYNC_INTERVAL / 2)

        while self.running:
            try:
                await self._run_price_sync()
            except Exception as e:
                logger.error(f"Price sync error: {e}", exc_info=True)

            await asyncio.sleep(PRICE_SYNC_INTERVAL)

    async def _run_full_sync(self):
        """Run a full market sync with locking."""
        async with self.pool.acquire() as conn:
            # Try to acquire lock
            if not await self._acquire_lock(conn, ADVISORY_LOCK_ID):
                logger.info("Full sync skipped - another sync is running")
                await self._record_sync_skipped(conn, "market_sync_full")
                return

            run_id = await self._record_sync_start(conn, "market_sync_full")

            try:
                logger.info("Starting full market sync...")
                start_time = time.time()

                # Fetch and sync markets
                stats = await self._sync_markets(conn, active_only=True)

                elapsed = time.time() - start_time
                logger.info(
                    f"Full sync complete: {stats['upserted']} markets "
                    f"in {elapsed:.1f}s ({stats['api_calls']} API calls)"
                )

                await self._record_sync_end(
                    conn, run_id, "success",
                    rows_fetched=stats["fetched"],
                    rows_upserted=stats["upserted"],
                    rows_failed=stats["failed"],
                    api_calls=stats["api_calls"],
                )

            except Exception as e:
                logger.error(f"Full sync failed: {e}")
                await self._record_sync_end(
                    conn, run_id, "failed",
                    error_message=str(e),
                )
                raise

            finally:
                await self._release_lock(conn, ADVISORY_LOCK_ID)

    async def _run_price_sync(self):
        """Run a lighter price-only sync for hot markets."""
        async with self.pool.acquire() as conn:
            # Use different lock ID for price sync
            price_lock_id = ADVISORY_LOCK_ID + 1

            if not await self._acquire_lock(conn, price_lock_id):
                logger.debug("Price sync skipped - another sync is running")
                return

            run_id = await self._record_sync_start(conn, "market_sync_prices")

            try:
                # Only sync top 100 markets by volume (most active)
                stats = await self._sync_markets(
                    conn,
                    active_only=True,
                    limit=200,  # Top 200 by volume
                    price_only=True,
                )

                await self._record_sync_end(
                    conn, run_id, "success",
                    rows_fetched=stats["fetched"],
                    rows_upserted=stats["upserted"],
                    api_calls=stats["api_calls"],
                )

            except Exception as e:
                await self._record_sync_end(
                    conn, run_id, "failed",
                    error_message=str(e),
                )

            finally:
                await self._release_lock(conn, price_lock_id)

    async def _sync_markets(
        self,
        conn,
        active_only: bool = True,
        limit: Optional[int] = None,
        price_only: bool = False,
    ) -> dict:
        """Fetch and sync markets from Polymarket Gamma API."""
        import json
        from decimal import Decimal, InvalidOperation

        def safe_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def safe_decimal(val, max_val=999999999.99):
            if val is None:
                return None
            try:
                f = float(val)
                if f > max_val:
                    f = max_val
                return Decimal(str(round(f, 2)))
            except (ValueError, TypeError, InvalidOperation):
                return None

        stats = {"fetched": 0, "upserted": 0, "failed": 0, "api_calls": 0}

        async with httpx.AsyncClient(timeout=30.0) as client:
            all_markets = []
            offset = 0
            batch_size = 100

            while True:
                params = {"limit": batch_size, "offset": offset}
                if active_only:
                    params["active"] = "true"
                    params["closed"] = "false"

                try:
                    resp = await client.get(f"{GAMMA_API}/markets", params=params)
                    stats["api_calls"] += 1

                    if resp.status_code == 429:
                        # Rate limited - wait and retry
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    markets = resp.json()

                except Exception as e:
                    logger.error(f"API error at offset {offset}: {e}")
                    break

                if not markets:
                    break

                all_markets.extend(markets)
                offset += batch_size

                if limit and len(all_markets) >= limit:
                    all_markets = all_markets[:limit]
                    break

                # Rate limit protection
                await asyncio.sleep(0.1)

            stats["fetched"] = len(all_markets)

            # Upsert markets
            for market in all_markets:
                try:
                    condition_id = market.get("conditionId") or market.get("condition_id")
                    if not condition_id:
                        continue

                    # Parse prices
                    prices = market.get("outcomePrices")
                    yes_price = no_price = None
                    if prices:
                        if isinstance(prices, str):
                            prices = json.loads(prices)
                        if prices and len(prices) >= 2:
                            yes_price = safe_float(prices[0])
                            no_price = safe_float(prices[1])
                        elif prices and len(prices) == 1:
                            yes_price = safe_float(prices[0])
                            no_price = 1.0 - yes_price if yes_price else None

                    # Parse volumes
                    volume_24h = safe_decimal(market.get("volume24hr"))
                    volume_7d = safe_decimal(market.get("volume1wk"))
                    liquidity = safe_decimal(market.get("liquidityNum") or market.get("liquidity"))

                    # Extract event_id from events array
                    event_id = None
                    events = market.get("events")
                    if events and isinstance(events, list) and len(events) > 0:
                        event_id = events[0].get("id")
                    # Fallback to legacy fields
                    if not event_id:
                        event_id = market.get("eventId") or market.get("event_id")

                    if price_only:
                        # Lighter update - just prices and volume
                        await conn.execute("""
                            UPDATE explorer_markets
                            SET yes_price = $2,
                                no_price = $3,
                                volume_24h = $4,
                                volume_7d = $5,
                                liquidity_score = $6,
                                updated_at = NOW()
                            WHERE condition_id = $1
                        """, condition_id, yes_price, no_price, volume_24h, volume_7d, liquidity)
                    else:
                        # Full upsert
                        question = (market.get("question") or "")[:500]
                        description = market.get("description")
                        if description:
                            description = description[:2000]

                        await conn.execute("""
                            INSERT INTO explorer_markets (
                                condition_id, event_id, question, description, yes_price, no_price,
                                volume_24h, volume_7d, liquidity_score, updated_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                            ON CONFLICT (condition_id) DO UPDATE SET
                                event_id = EXCLUDED.event_id,
                                question = EXCLUDED.question,
                                description = EXCLUDED.description,
                                yes_price = EXCLUDED.yes_price,
                                no_price = EXCLUDED.no_price,
                                volume_24h = EXCLUDED.volume_24h,
                                volume_7d = EXCLUDED.volume_7d,
                                liquidity_score = EXCLUDED.liquidity_score,
                                updated_at = NOW()
                        """, condition_id, event_id, question, description, yes_price, no_price,
                             volume_24h, volume_7d, liquidity)

                    stats["upserted"] += 1

                except Exception as e:
                    logger.debug(f"Failed to upsert market: {e}")
                    stats["failed"] += 1

        return stats


async def main():
    """Run the sync service."""
    database_url = os.environ.get(
        "EXPLORER_DATABASE_URL",
        settings.database_url if hasattr(settings, 'database_url') else
        "postgresql://predict:predict@postgres:5432/predict"
    )

    service = SyncService(database_url)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(service.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_handler)

    try:
        await service.start()
    except asyncio.CancelledError:
        pass
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
