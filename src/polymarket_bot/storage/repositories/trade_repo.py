"""
Trade repository with watermark pattern for idempotent processing.

Handles:
- polymarket_trades: Raw trade data from Polymarket
- trade_watermarks: Tracks last processed trade per condition
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import PolymarketTrade, TradeWatermark
from polymarket_bot.storage.repositories.base import BaseRepository


class TradeRepository(BaseRepository[PolymarketTrade]):
    """Repository for Polymarket trades."""

    table_name = "polymarket_trades"
    model_class = PolymarketTrade

    async def create(self, trade: PolymarketTrade) -> PolymarketTrade:
        """Insert a new trade."""
        query = """
            INSERT INTO polymarket_trades
            (condition_id, trade_id, token_id, price, size, side, timestamp, raw_json, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (condition_id, trade_id) DO NOTHING
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            trade.condition_id,
            trade.trade_id,
            trade.token_id,
            trade.price,
            trade.size,
            trade.side,
            trade.timestamp,
            trade.raw_json,
            trade.outcome,
            trade.outcome_index,
        )
        return self._record_to_model(record) if record else trade

    async def create_many(self, trades: list[PolymarketTrade]) -> int:
        """Bulk insert trades. Returns count of inserted."""
        if not trades:
            return 0

        query = """
            INSERT INTO polymarket_trades
            (condition_id, trade_id, token_id, price, size, side, timestamp, raw_json, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (condition_id, trade_id) DO NOTHING
        """
        async with self.db.transaction() as conn:
            result = await conn.executemany(
                query,
                [
                    (
                        t.condition_id,
                        t.trade_id,
                        t.token_id,
                        t.price,
                        t.size,
                        t.side,
                        t.timestamp,
                        t.raw_json,
                        t.outcome,
                        t.outcome_index,
                    )
                    for t in trades
                ],
            )
        return len(trades)

    async def get_by_condition(
        self, condition_id: str, limit: int = 100
    ) -> list[PolymarketTrade]:
        """Get trades for a condition, most recent first."""
        query = """
            SELECT * FROM polymarket_trades
            WHERE condition_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, condition_id, limit)
        return self._records_to_models(records)

    async def get_recent(
        self, condition_id: str, max_age_seconds: int = 300
    ) -> list[PolymarketTrade]:
        """
        Get trades within max_age_seconds.

        CRITICAL: This prevents the "Belichick Bug" (G1) where old trades
        are mistaken for recent activity.
        """
        cutoff = int(datetime.utcnow().timestamp()) - max_age_seconds
        query = """
            SELECT * FROM polymarket_trades
            WHERE condition_id = $1 AND timestamp >= $2
            ORDER BY timestamp DESC
        """
        records = await self.db.fetch(query, condition_id, cutoff)
        return self._records_to_models(records)

    async def get_latest_timestamp(self, condition_id: str) -> Optional[int]:
        """Get most recent trade timestamp for a condition."""
        query = """
            SELECT MAX(timestamp) FROM polymarket_trades WHERE condition_id = $1
        """
        return await self.db.fetchval(query, condition_id)


class TradeWatermarkRepository(BaseRepository[TradeWatermark]):
    """
    Watermark repository for tracking processed trades.

    The watermark pattern ensures idempotent processing:
    - Before processing trades, check the watermark
    - Only process trades newer than the watermark
    - After processing, update the watermark
    """

    table_name = "trade_watermarks"
    model_class = TradeWatermark

    async def get(self, condition_id: str) -> Optional[TradeWatermark]:
        """Get watermark for a condition."""
        query = "SELECT * FROM trade_watermarks WHERE condition_id = $1"
        record = await self.db.fetchrow(query, condition_id)
        return self._record_to_model(record)

    async def get_timestamp(self, condition_id: str) -> int:
        """Get last processed timestamp, or 0 if none."""
        query = "SELECT last_timestamp FROM trade_watermarks WHERE condition_id = $1"
        result = await self.db.fetchval(query, condition_id)
        return result or 0

    async def update(self, condition_id: str, timestamp: int) -> TradeWatermark:
        """Update watermark to new timestamp."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO trade_watermarks (condition_id, last_timestamp, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (condition_id) DO UPDATE
            SET last_timestamp = GREATEST(trade_watermarks.last_timestamp, $2),
                updated_at = $3
            RETURNING *
        """
        record = await self.db.fetchrow(query, condition_id, timestamp, now)
        return self._record_to_model(record)
