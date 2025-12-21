"""
Trigger tracker for first-trigger deduplication.

We only trade the FIRST time a token crosses a threshold. This module
tracks triggers and prevents duplicate trading on the same market.

Critical Gotcha (G2):
    Multiple token_ids can map to the same market (condition_id).
    We MUST deduplicate by (token_id, condition_id, threshold), not just token_id.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database


@dataclass
class TriggerInfo:
    """Information about a recorded trigger."""

    token_id: str
    condition_id: str
    threshold: Decimal
    price: Decimal
    trade_size: Optional[Decimal]
    model_score: Optional[float]
    triggered_at: datetime


class TriggerTracker:
    """
    Tracks first triggers and prevents duplicate trades.

    G2 Protection: Uses (token_id, condition_id, threshold) as the unique key
    to prevent the same market from being traded multiple times.

    Usage:
        tracker = TriggerTracker(db)

        # Check if this is the first trigger
        if await tracker.is_first_trigger(token_id, condition_id, threshold):
            # Record the trigger
            await tracker.record_trigger(token_id, condition_id, threshold, ...)
            # Execute the trade
            ...
    """

    def __init__(self, db: "Database") -> None:
        """
        Initialize the trigger tracker.

        Args:
            db: Database connection for persistence
        """
        self._db = db

    async def is_first_trigger(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
    ) -> bool:
        """
        Check if this is the first trigger for this token/condition/threshold.

        G2 Protection: Must check BOTH token_id AND condition_id.

        Args:
            token_id: The token that triggered
            condition_id: The market condition ID
            threshold: The price threshold

        Returns:
            True if this is the first trigger, False if already triggered
        """
        query = """
            SELECT 1 FROM polymarket_first_triggers
            WHERE token_id = $1 AND condition_id = $2 AND threshold = $3
            LIMIT 1
        """
        result = await self._db.fetchval(query, token_id, condition_id, float(threshold))
        return result is None

    async def has_condition_triggered(
        self,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
    ) -> bool:
        """
        Check if ANY token for this condition has triggered.

        This is an additional G2 protection - even if the token_id is different,
        we may not want to trade the same market twice.

        Args:
            condition_id: The market condition ID
            threshold: The price threshold

        Returns:
            True if any token for this condition has triggered
        """
        query = """
            SELECT 1 FROM polymarket_first_triggers
            WHERE condition_id = $1 AND threshold = $2
            LIMIT 1
        """
        result = await self._db.fetchval(query, condition_id, float(threshold))
        return result is not None

    async def should_trigger(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
    ) -> bool:
        """
        Comprehensive check: Should we trigger for this token?

        Checks both:
        1. This exact token hasn't triggered
        2. No other token for this condition has triggered (G2)

        Args:
            token_id: The token that triggered
            condition_id: The market condition ID
            threshold: The price threshold

        Returns:
            True if we should trigger, False otherwise
        """
        # Check if this token has triggered
        if not await self.is_first_trigger(token_id, condition_id, threshold):
            return False

        # G2: Check if any token for this condition has triggered
        if await self.has_condition_triggered(condition_id, threshold):
            return False

        return True

    async def record_trigger(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
        price: Optional[Decimal] = None,
        trade_size: Optional[Decimal] = None,
        model_score: Optional[float] = None,
        outcome: Optional[str] = None,
        outcome_index: Optional[int] = None,
    ) -> None:
        """
        Record a new trigger.

        Args:
            token_id: The token that triggered
            condition_id: The market condition ID
            threshold: The price threshold
            price: The trigger price
            trade_size: Size of the triggering trade
            model_score: Model score at trigger time
            outcome: The outcome (Yes/No)
            outcome_index: The outcome index (0/1)
        """
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp() * 1000)

        query = """
            INSERT INTO polymarket_first_triggers
            (token_id, condition_id, threshold, trigger_timestamp, price, size,
             model_score, created_at, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (token_id, condition_id, threshold) DO NOTHING
        """
        await self._db.execute(
            query,
            token_id,
            condition_id,
            float(threshold),
            timestamp,
            float(price) if price else None,
            float(trade_size) if trade_size else None,
            model_score,
            now.isoformat(),
            outcome,
            outcome_index,
        )

    async def try_record_trigger_atomic(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
        price: Optional[Decimal] = None,
        trade_size: Optional[Decimal] = None,
        model_score: Optional[float] = None,
        outcome: Optional[str] = None,
        outcome_index: Optional[int] = None,
    ) -> bool:
        """
        Atomically check and record a trigger.

        CRITICAL: This is the G2-safe method for deduplication.
        It performs an atomic INSERT with ON CONFLICT and checks
        if the insert succeeded (was the first trigger).

        This prevents TOCTOU race conditions where two concurrent
        events both pass should_trigger() but both execute.

        Also checks condition_id level to prevent duplicate trades
        when multiple token_ids map to the same market.

        Args:
            token_id: The token that triggered
            condition_id: The market condition ID
            threshold: The price threshold
            price: The trigger price
            trade_size: Size of the triggering trade
            model_score: Model score at trigger time
            outcome: The outcome (Yes/No)
            outcome_index: The outcome index (0/1)

        Returns:
            True if this was the FIRST trigger (inserted successfully),
            False if a trigger already exists (duplicate)
        """
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp() * 1000)

        # FIX: Use PostgreSQL advisory locks for true atomicity
        # SELECT FOR UPDATE doesn't lock non-existent rows, so we use
        # pg_advisory_xact_lock with a stable hash of (condition_id, threshold)
        # This ensures only one concurrent request can proceed for a given condition

        # Use a transaction to ensure atomicity
        async with self._db.transaction() as conn:
            # Acquire advisory lock based on condition_id + threshold hash
            # This prevents concurrent inserts for the same condition
            # FIX: Use stable SHA256 hash instead of Python's randomized hash()
            # This ensures consistent locking across processes
            lock_input = f"{condition_id}:{float(threshold)}".encode()
            lock_hash = hashlib.sha256(lock_input).digest()
            # Use first 8 bytes as two 32-bit ints for pg_advisory_xact_lock(bigint)
            lock_key = int.from_bytes(lock_hash[:8], 'big', signed=True)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)

            # Now check if ANY token for this condition has triggered (G2)
            condition_check_query = """
                SELECT 1 FROM polymarket_first_triggers
                WHERE condition_id = $1 AND threshold = $2
                LIMIT 1
            """
            existing = await conn.fetchval(
                condition_check_query,
                condition_id,
                float(threshold),
            )
            if existing is not None:
                # Another token for this condition already triggered
                return False

            # Now insert atomically - we hold the lock so no race possible
            insert_query = """
                INSERT INTO polymarket_first_triggers
                (token_id, condition_id, threshold, trigger_timestamp, price, size,
                 model_score, created_at, outcome, outcome_index)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (token_id, condition_id, threshold) DO NOTHING
                RETURNING token_id
            """
            result = await conn.fetchval(
                insert_query,
                token_id,
                condition_id,
                float(threshold),
                timestamp,
                float(price) if price else None,
                float(trade_size) if trade_size else None,
                model_score,
                now.isoformat(),
                outcome,
                outcome_index,
            )

            # If RETURNING returned a value, the insert succeeded
            # Advisory lock is automatically released when transaction commits
            return result is not None

    async def remove_trigger(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
    ) -> bool:
        """
        Remove a trigger record.

        Used when execution fails after atomic claim, to allow retry.

        Args:
            token_id: The token ID
            condition_id: The condition ID
            threshold: The price threshold

        Returns:
            True if a trigger was removed, False if not found
        """
        query = """
            DELETE FROM polymarket_first_triggers
            WHERE token_id = $1 AND condition_id = $2 AND threshold = $3
            RETURNING token_id
        """
        result = await self._db.fetchval(query, token_id, condition_id, float(threshold))
        return result is not None

    async def get_trigger(
        self,
        token_id: str,
        condition_id: str,
        threshold: Decimal = Decimal("0.95"),
    ) -> Optional[TriggerInfo]:
        """
        Get information about a recorded trigger.

        Args:
            token_id: The token ID
            condition_id: The condition ID
            threshold: The price threshold

        Returns:
            TriggerInfo if found, None otherwise
        """
        query = """
            SELECT token_id, condition_id, threshold, price, size, model_score, created_at
            FROM polymarket_first_triggers
            WHERE token_id = $1 AND condition_id = $2 AND threshold = $3
        """
        record = await self._db.fetchrow(query, token_id, condition_id, float(threshold))

        if not record:
            return None

        return TriggerInfo(
            token_id=record["token_id"],
            condition_id=record["condition_id"],
            threshold=Decimal(str(record["threshold"])),
            price=Decimal(str(record["price"])) if record["price"] else Decimal("0"),
            trade_size=Decimal(str(record["size"])) if record["size"] else None,
            model_score=record["model_score"],
            triggered_at=datetime.fromisoformat(record["created_at"]),
        )

    async def get_triggers_for_condition(
        self,
        condition_id: str,
    ) -> list[TriggerInfo]:
        """
        Get all triggers for a condition.

        Args:
            condition_id: The condition ID

        Returns:
            List of triggers for this condition
        """
        query = """
            SELECT token_id, condition_id, threshold, price, size, model_score, created_at
            FROM polymarket_first_triggers
            WHERE condition_id = $1
            ORDER BY created_at DESC
        """
        records = await self._db.fetch(query, condition_id)

        return [
            TriggerInfo(
                token_id=r["token_id"],
                condition_id=r["condition_id"],
                threshold=Decimal(str(r["threshold"])),
                price=Decimal(str(r["price"])) if r["price"] else Decimal("0"),
                trade_size=Decimal(str(r["size"])) if r["size"] else None,
                model_score=r["model_score"],
                triggered_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in records
        ]
