"""
Trigger repository with dual-key deduplication.

Handles:
- polymarket_first_triggers: First time a token hit a threshold
- trigger_watermarks: Tracks processing state per threshold

CRITICAL: Implements dual-key deduplication (G2 gotcha fix).
Must check BOTH token_id AND condition_id to prevent duplicate trades
when multiple token_ids map to the same market.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import PolymarketFirstTrigger, TriggerWatermark
from polymarket_bot.storage.repositories.base import BaseRepository


class TriggerRepository(BaseRepository[PolymarketFirstTrigger]):
    """
    Repository for first-hit triggers.

    Ensures each (token_id, threshold) combination only triggers once.
    Also tracks condition_id to prevent duplicate token_id spam (G2).
    """

    table_name = "polymarket_first_triggers"
    model_class = PolymarketFirstTrigger

    async def create(self, trigger: PolymarketFirstTrigger) -> PolymarketFirstTrigger:
        """
        Record a new trigger event.

        Uses ON CONFLICT to ensure (token_id, condition_id, threshold) uniqueness.
        This is the G2 gotcha fix - prevents duplicate trades when multiple
        token_ids map to the same condition.
        """
        query = """
            INSERT INTO polymarket_first_triggers
            (token_id, condition_id, threshold, trigger_timestamp, price, size,
             created_at, model_score, model_version, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (token_id, condition_id, threshold) DO NOTHING
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            trigger.token_id,
            trigger.condition_id,
            trigger.threshold,
            trigger.trigger_timestamp,
            trigger.price,
            trigger.size,
            trigger.created_at,
            trigger.model_score,
            trigger.model_version,
            trigger.outcome,
            trigger.outcome_index,
        )
        return self._record_to_model(record) if record else trigger

    async def has_triggered(
        self, token_id: str, condition_id: str, threshold: float
    ) -> bool:
        """
        Check if this exact token+condition has already triggered at this threshold.

        Must include condition_id to match the PK (token_id, condition_id, threshold).
        Without condition_id, migrated rows with empty condition_id could cause
        false suppressions for new triggers with actual condition_ids.
        """
        query = """
            SELECT 1 FROM polymarket_first_triggers
            WHERE token_id = $1 AND condition_id = $2 AND threshold = $3
        """
        result = await self.db.fetchval(query, token_id, condition_id, threshold)
        return result is not None

    async def has_condition_triggered(
        self, condition_id: str, threshold: float
    ) -> bool:
        """
        Check if ANY token for this condition has triggered.

        CRITICAL: This is the G2 gotcha fix. Multiple token_ids can map
        to the same condition_id. We must check both to prevent duplicates.
        """
        query = """
            SELECT 1 FROM polymarket_first_triggers
            WHERE condition_id = $1 AND threshold = $2
        """
        result = await self.db.fetchval(query, condition_id, threshold)
        return result is not None

    async def should_trigger(
        self, token_id: str, condition_id: str, threshold: float
    ) -> bool:
        """
        Check if a new trigger should be created.

        Returns True only if:
        1. This exact (token_id, condition_id, threshold) doesn't exist
        2. No other token for this condition_id has triggered at this threshold (G2)

        This is the safe way to check before creating a trigger.
        """
        # Check exact match first (handles the PK correctly)
        token_triggered = await self.has_triggered(token_id, condition_id, threshold)
        if token_triggered:
            return False

        # G2 protection: check if any OTHER token for this condition triggered
        condition_triggered = await self.has_condition_triggered(condition_id, threshold)
        return not condition_triggered

    async def get_by_token(
        self, token_id: str, limit: int = 100
    ) -> list[PolymarketFirstTrigger]:
        """Get all triggers for a token."""
        query = """
            SELECT * FROM polymarket_first_triggers
            WHERE token_id = $1
            ORDER BY trigger_timestamp DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, token_id, limit)
        return self._records_to_models(records)

    async def get_by_condition(
        self, condition_id: str, limit: int = 100
    ) -> list[PolymarketFirstTrigger]:
        """Get all triggers for a condition (across all token_ids)."""
        query = """
            SELECT * FROM polymarket_first_triggers
            WHERE condition_id = $1
            ORDER BY trigger_timestamp DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, condition_id, limit)
        return self._records_to_models(records)

    async def get_recent(
        self, since_timestamp: int, threshold: Optional[float] = None
    ) -> list[PolymarketFirstTrigger]:
        """Get triggers since a timestamp, optionally filtered by threshold."""
        if threshold is not None:
            query = """
                SELECT * FROM polymarket_first_triggers
                WHERE trigger_timestamp >= $1 AND threshold = $2
                ORDER BY trigger_timestamp DESC
            """
            records = await self.db.fetch(query, since_timestamp, threshold)
        else:
            query = """
                SELECT * FROM polymarket_first_triggers
                WHERE trigger_timestamp >= $1
                ORDER BY trigger_timestamp DESC
            """
            records = await self.db.fetch(query, since_timestamp)
        return self._records_to_models(records)


class TriggerWatermarkRepository(BaseRepository[TriggerWatermark]):
    """Watermark repository for trigger processing."""

    table_name = "trigger_watermarks"
    model_class = TriggerWatermark

    async def get(self, threshold: float) -> Optional[TriggerWatermark]:
        """Get watermark for a threshold."""
        query = "SELECT * FROM trigger_watermarks WHERE threshold = $1"
        record = await self.db.fetchrow(query, threshold)
        return self._record_to_model(record)

    async def get_timestamp(self, threshold: float) -> int:
        """Get last processed timestamp, or 0 if none."""
        query = "SELECT last_timestamp FROM trigger_watermarks WHERE threshold = $1"
        result = await self.db.fetchval(query, threshold)
        return result or 0

    async def update(self, threshold: float, timestamp: int) -> TriggerWatermark:
        """Update watermark to new timestamp."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO trigger_watermarks (threshold, last_timestamp, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (threshold) DO UPDATE
            SET last_timestamp = GREATEST(trigger_watermarks.last_timestamp, $2),
                updated_at = $3
            RETURNING *
        """
        record = await self.db.fetchrow(query, threshold, timestamp, now)
        return self._record_to_model(record)
