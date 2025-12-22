"""
Price Candle Repository for Tier 2 data.

Stores OHLCV candles at multiple resolutions.
Uses standard SQL (no TimescaleDB dependency).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import PriceCandle, OrderbookSnapshot
from polymarket_bot.storage.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


# Resolution to timedelta mapping
RESOLUTION_INTERVALS = {
    "5m": timedelta(minutes=5),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


class CandleRepository(BaseRepository[PriceCandle]):
    """
    Repository for price_candles table (Tier 2).

    Provides:
    - Candle storage and retrieval
    - Aggregation from trades
    - Multiple resolutions (5m, 1h, 1d)
    """

    table_name = "price_candles"
    model_class = PriceCandle

    async def upsert(self, candle: PriceCandle) -> None:
        """Insert or update a candle."""
        await self.db.execute(
            """
            INSERT INTO price_candles (
                condition_id, token_id, resolution, bucket_start,
                open_price, high_price, low_price, close_price,
                volume, trade_count, vwap
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (condition_id, token_id, resolution, bucket_start) DO UPDATE SET
                high_price = GREATEST(price_candles.high_price, EXCLUDED.high_price),
                low_price = LEAST(price_candles.low_price, EXCLUDED.low_price),
                close_price = EXCLUDED.close_price,
                volume = price_candles.volume + EXCLUDED.volume,
                trade_count = price_candles.trade_count + EXCLUDED.trade_count,
                vwap = EXCLUDED.vwap
            """,
            candle.condition_id,
            candle.token_id,
            candle.resolution,
            candle.bucket_start,
            candle.open_price,
            candle.high_price,
            candle.low_price,
            candle.close_price,
            candle.volume,
            candle.trade_count,
            candle.vwap,
        )

    async def get_candles(
        self,
        condition_id: str,
        token_id: str,
        resolution: str,
        start: datetime,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[PriceCandle]:
        """Get candles for a market within a time range."""
        if end is None:
            end = datetime.utcnow()

        records = await self.db.fetch(
            """
            SELECT * FROM price_candles
            WHERE condition_id = $1
              AND token_id = $2
              AND resolution = $3
              AND bucket_start >= $4
              AND bucket_start <= $5
            ORDER BY bucket_start DESC
            LIMIT $6
            """,
            condition_id,
            token_id,
            resolution,
            start,
            end,
            limit,
        )
        return self._records_to_models(records)

    async def get_latest_candle(
        self,
        condition_id: str,
        token_id: str,
        resolution: str,
    ) -> Optional[PriceCandle]:
        """Get most recent candle."""
        record = await self.db.fetchrow(
            """
            SELECT * FROM price_candles
            WHERE condition_id = $1 AND token_id = $2 AND resolution = $3
            ORDER BY bucket_start DESC
            LIMIT 1
            """,
            condition_id,
            token_id,
            resolution,
        )
        return self._record_to_model(record)

    async def aggregate_from_trades(
        self,
        condition_id: str,
        token_id: str,
        resolution: str,
        since: Optional[datetime] = None,
    ) -> int:
        """
        Aggregate trades into candles using standard SQL.

        This is a pure SQL implementation without TimescaleDB.
        Uses delete-then-insert for idempotency - running multiple times
        gives the same result without double-counting.
        """
        interval = RESOLUTION_INTERVALS.get(resolution)
        if not interval:
            raise ValueError(f"Unknown resolution: {resolution}")

        if since is None:
            since = datetime.utcnow() - timedelta(days=1)

        # Get interval in seconds for bucketing
        interval_seconds = int(interval.total_seconds())

        # Phase 1: Delete existing candles in the time range (idempotent approach)
        # This prevents double-counting when re-aggregating the same time range
        await self.db.execute(
            """
            DELETE FROM price_candles
            WHERE condition_id = $1
              AND token_id = $2
              AND resolution = $3
              AND bucket_start >= $4
            """,
            condition_id,
            token_id,
            resolution,
            since,
        )

        # Phase 2: Aggregate trades into fresh candles
        result = await self.db.execute(
            f"""
            INSERT INTO price_candles (
                condition_id, token_id, resolution, bucket_start,
                open_price, high_price, low_price, close_price,
                volume, trade_count, vwap
            )
            SELECT
                $1 as condition_id,
                $2 as token_id,
                $3 as resolution,
                to_timestamp(
                    floor(extract(epoch from to_timestamp(timestamp / 1000)) / $4) * $4
                ) as bucket_start,
                -- Open price: first price in bucket (min timestamp)
                (array_agg(price ORDER BY timestamp ASC))[1] as open_price,
                max(price) as high_price,
                min(price) as low_price,
                -- Close price: last price in bucket (max timestamp)
                (array_agg(price ORDER BY timestamp DESC))[1] as close_price,
                sum(size * price) as volume,
                count(*) as trade_count,
                CASE WHEN sum(size) > 0 THEN sum(size * price) / sum(size) ELSE NULL END as vwap
            FROM polymarket_trades
            WHERE condition_id = $1
              AND token_id = $2
              AND timestamp >= extract(epoch from $5::timestamp) * 1000
              AND price IS NOT NULL
              AND size IS NOT NULL
            GROUP BY bucket_start
            """,
            condition_id,
            token_id,
            resolution,
            interval_seconds,
            since,
        )

        # Parse affected row count
        try:
            return int(result.split()[-1]) if result else 0
        except (ValueError, IndexError):
            return 0

    async def aggregate_all_resolutions(
        self,
        condition_id: str,
        token_id: str,
        since: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Aggregate trades into all resolution candles."""
        results = {}
        for resolution in RESOLUTION_INTERVALS.keys():
            count = await self.aggregate_from_trades(
                condition_id, token_id, resolution, since
            )
            results[resolution] = count
        return results

    async def cleanup_old_candles(self) -> int:
        """
        Delete old candles based on retention policy.

        - 5m candles: 7 days
        - 1h candles: 90 days
        - 1d candles: keep forever
        """
        total = 0

        # 5m candles: 7 days
        result = await self.db.execute(
            """
            DELETE FROM price_candles
            WHERE resolution = '5m' AND bucket_start < NOW() - INTERVAL '7 days'
            """
        )
        try:
            total += int(result.split()[-1])
        except (ValueError, IndexError):
            pass

        # 1h candles: 90 days
        result = await self.db.execute(
            """
            DELETE FROM price_candles
            WHERE resolution = '1h' AND bucket_start < NOW() - INTERVAL '90 days'
            """
        )
        try:
            total += int(result.split()[-1])
        except (ValueError, IndexError):
            pass

        if total > 0:
            logger.info(f"Cleaned up {total} old candles")

        return total


class OrderbookRepository(BaseRepository[OrderbookSnapshot]):
    """
    Repository for orderbook_snapshots table (Tier 3).
    """

    table_name = "orderbook_snapshots"
    model_class = OrderbookSnapshot

    async def save(self, snapshot: OrderbookSnapshot) -> None:
        """Save an orderbook snapshot."""
        import json

        bids_json = json.dumps(snapshot.bids) if snapshot.bids else None
        asks_json = json.dumps(snapshot.asks) if snapshot.asks else None

        await self.db.execute(
            """
            INSERT INTO orderbook_snapshots (
                condition_id, token_id, snapshot_at,
                best_bid, best_ask, spread, mid_price,
                bids, asks, bid_depth_5pct, ask_depth_5pct
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (condition_id, token_id, snapshot_at) DO NOTHING
            """,
            snapshot.condition_id,
            snapshot.token_id,
            snapshot.snapshot_at,
            snapshot.best_bid,
            snapshot.best_ask,
            snapshot.spread,
            snapshot.mid_price,
            bids_json,
            asks_json,
            snapshot.bid_depth_5pct,
            snapshot.ask_depth_5pct,
        )

    async def get_latest(
        self,
        condition_id: str,
        token_id: str,
    ) -> Optional[OrderbookSnapshot]:
        """Get most recent orderbook snapshot."""
        record = await self.db.fetchrow(
            """
            SELECT * FROM orderbook_snapshots
            WHERE condition_id = $1 AND token_id = $2
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            condition_id,
            token_id,
        )
        if record is None:
            return None

        import json

        data = dict(record)
        if data.get("bids") and isinstance(data["bids"], str):
            data["bids"] = json.loads(data["bids"])
        if data.get("asks") and isinstance(data["asks"], str):
            data["asks"] = json.loads(data["asks"])

        return OrderbookSnapshot(**data)

    async def get_history(
        self,
        condition_id: str,
        token_id: str,
        hours: int = 24,
    ) -> list[OrderbookSnapshot]:
        """Get orderbook snapshots from the last N hours."""
        records = await self.db.fetch(
            """
            SELECT * FROM orderbook_snapshots
            WHERE condition_id = $1
              AND token_id = $2
              AND snapshot_at >= NOW() - make_interval(hours => $3)
            ORDER BY snapshot_at DESC
            """,
            condition_id,
            token_id,
            hours,
        )

        import json

        snapshots = []
        for r in records:
            data = dict(r)
            if data.get("bids") and isinstance(data["bids"], str):
                data["bids"] = json.loads(data["bids"])
            if data.get("asks") and isinstance(data["asks"], str):
                data["asks"] = json.loads(data["asks"])
            snapshots.append(OrderbookSnapshot(**data))

        return snapshots

    async def cleanup_old_snapshots(self) -> int:
        """Delete snapshots older than 7 days."""
        result = await self.db.execute(
            """
            DELETE FROM orderbook_snapshots
            WHERE snapshot_at < NOW() - INTERVAL '7 days'
            """
        )
        try:
            count = int(result.split()[-1])
            if count > 0:
                logger.info(f"Cleaned up {count} old orderbook snapshots")
            return count
        except (ValueError, IndexError):
            return 0
