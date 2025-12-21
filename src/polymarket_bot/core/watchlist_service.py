"""
Watchlist service for managing tokens pending re-scoring.

Tokens with scores 0.90-0.97 are added to the watchlist and re-scored
periodically. They may be promoted to execution when their score improves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database


@dataclass
class WatchlistEntry:
    """A token being watched for trading."""

    token_id: str
    condition_id: str
    question: Optional[str]
    trigger_price: Decimal
    initial_score: float
    current_score: float
    time_to_end_hours: float
    created_at: datetime
    status: str  # 'watching', 'promoted', 'expired', 'traded'


@dataclass
class Promotion:
    """A watchlist entry that should be promoted to execution."""

    token_id: str
    condition_id: str
    old_score: float
    new_score: float
    reason: str


class WatchlistService:
    """
    Service for managing the trading watchlist.

    Tokens with promising but below-threshold scores are added to the
    watchlist. They are re-scored periodically (e.g., hourly) and may
    be promoted to execution when their score improves above threshold.

    Score evolution:
        - Scores tend to increase as time_to_end decreases
        - A token at 0.92 with 720h remaining might be 0.98 at 48h
        - This captures the "uncertainty reduction" near expiry

    Usage:
        service = WatchlistService(db)

        # Add to watchlist
        await service.add_to_watchlist(
            token_id="tok_abc",
            condition_id="0x123",
            initial_score=0.92,
            time_to_end_hours=720,
        )

        # Re-score all entries
        promotions = await service.rescore_all(scorer)

        # Handle promotions
        for p in promotions:
            await execute_trade(p.token_id)
    """

    def __init__(
        self,
        db: "Database",
        execution_threshold: float = 0.97,
        watchlist_min: float = 0.90,
    ) -> None:
        """
        Initialize the watchlist service.

        Args:
            db: Database connection
            execution_threshold: Minimum score for promotion to execution
            watchlist_min: Minimum score to stay on watchlist
        """
        self._db = db
        self._execution_threshold = execution_threshold
        self._watchlist_min = watchlist_min

    async def add_to_watchlist(
        self,
        token_id: str,
        condition_id: str,
        initial_score: float,
        time_to_end_hours: float,
        trigger_price: Optional[Decimal] = None,
        question: Optional[str] = None,
    ) -> None:
        """
        Add a token to the watchlist.

        Args:
            token_id: The token ID
            condition_id: The market condition ID
            initial_score: Initial model score
            time_to_end_hours: Hours until market resolves
            trigger_price: The price that triggered the addition
            question: The market question
        """
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp())

        query = """
            INSERT INTO trade_watchlist
            (token_id, condition_id, question, trigger_price, initial_score,
             current_score, time_to_end_hours, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'watching', $8, $8)
            ON CONFLICT (token_id) DO UPDATE
            SET current_score = $6,
                time_to_end_hours = $7,
                updated_at = $8
        """
        await self._db.execute(
            query,
            token_id,
            condition_id,
            question,
            float(trigger_price) if trigger_price else None,
            initial_score,
            initial_score,
            time_to_end_hours,
            timestamp,
        )

    async def get_active_entries(self) -> list[WatchlistEntry]:
        """
        Get all active watchlist entries.

        Returns:
            List of entries with status='watching'
        """
        query = """
            SELECT token_id, condition_id, question, trigger_price,
                   initial_score, current_score, time_to_end_hours,
                   created_at, status
            FROM trade_watchlist
            WHERE status = 'watching'
            ORDER BY current_score DESC
        """
        records = await self._db.fetch(query)

        return [
            WatchlistEntry(
                token_id=r["token_id"],
                condition_id=r["condition_id"],
                question=r["question"],
                trigger_price=Decimal(str(r["trigger_price"])) if r["trigger_price"] else Decimal("0"),
                initial_score=r["initial_score"] or 0.0,
                current_score=r["current_score"] or 0.0,
                time_to_end_hours=r["time_to_end_hours"] or 0.0,
                created_at=datetime.fromtimestamp(r["created_at"], tz=timezone.utc) if r["created_at"] else datetime.now(timezone.utc),
                status=r["status"],
            )
            for r in records
        ]

    async def get_entry(
        self,
        token_id: str,
    ) -> Optional[WatchlistEntry]:
        """
        Get a specific watchlist entry.

        Args:
            token_id: The token ID

        Returns:
            WatchlistEntry if found, None otherwise
        """
        query = """
            SELECT token_id, condition_id, question, trigger_price,
                   initial_score, current_score, time_to_end_hours,
                   created_at, status
            FROM trade_watchlist
            WHERE token_id = $1
        """
        r = await self._db.fetchrow(query, token_id)

        if not r:
            return None

        return WatchlistEntry(
            token_id=r["token_id"],
            condition_id=r["condition_id"],
            question=r["question"],
            trigger_price=Decimal(str(r["trigger_price"])) if r["trigger_price"] else Decimal("0"),
            initial_score=r["initial_score"] or 0.0,
            current_score=r["current_score"] or 0.0,
            time_to_end_hours=r["time_to_end_hours"] or 0.0,
            created_at=datetime.fromtimestamp(r["created_at"], tz=timezone.utc) if r["created_at"] else datetime.now(timezone.utc),
            status=r["status"],
        )

    async def update_score(
        self,
        token_id: str,
        new_score: float,
        time_to_end_hours: Optional[float] = None,
    ) -> None:
        """
        Update the score for a watchlist entry.

        Args:
            token_id: The token ID
            new_score: The new model score
            time_to_end_hours: Updated time to end (optional)
        """
        now = int(datetime.now(timezone.utc).timestamp())

        if time_to_end_hours is not None:
            query = """
                UPDATE trade_watchlist
                SET current_score = $2, time_to_end_hours = $3, updated_at = $4
                WHERE token_id = $1
            """
            await self._db.execute(query, token_id, new_score, time_to_end_hours, now)
        else:
            query = """
                UPDATE trade_watchlist
                SET current_score = $2, updated_at = $3
                WHERE token_id = $1
            """
            await self._db.execute(query, token_id, new_score, now)

        # Record score history
        history_query = """
            INSERT INTO score_history (token_id, score, time_to_end_hours, scored_at)
            VALUES ($1, $2, $3, $4)
        """
        await self._db.execute(history_query, token_id, new_score, time_to_end_hours, now)

    async def mark_status(self, token_id: str, status: str) -> None:
        """
        Update the status of a watchlist entry.

        Args:
            token_id: The token ID
            status: New status ('watching', 'promoted', 'expired', 'traded')
        """
        now = int(datetime.now(timezone.utc).timestamp())
        query = """
            UPDATE trade_watchlist
            SET status = $2, updated_at = $3
            WHERE token_id = $1
        """
        await self._db.execute(query, token_id, status, now)

    async def rescore_all(
        self,
        scorer: Optional[callable] = None,
    ) -> list[Promotion]:
        """
        Re-score all active watchlist entries.

        If no scorer is provided, uses a simple time-based heuristic.

        Args:
            scorer: Optional scoring function that takes (entry) -> float

        Returns:
            List of promotions (entries that crossed the threshold)
        """
        entries = await self.get_active_entries()
        promotions: list[Promotion] = []

        for entry in entries:
            old_score = entry.current_score

            # Compute new score
            if scorer:
                new_score = scorer(entry)
            else:
                new_score = self._default_score(entry)

            # Update score
            await self.update_score(entry.token_id, new_score, entry.time_to_end_hours)

            # Check for promotion
            if new_score >= self._execution_threshold and old_score < self._execution_threshold:
                promotions.append(
                    Promotion(
                        token_id=entry.token_id,
                        condition_id=entry.condition_id,
                        old_score=old_score,
                        new_score=new_score,
                        reason=f"Score improved from {old_score:.2f} to {new_score:.2f}",
                    )
                )
                await self.mark_status(entry.token_id, "promoted")

            # Check for removal (score dropped too low)
            elif new_score < self._watchlist_min:
                await self.mark_status(entry.token_id, "expired")

        return promotions

    def _default_score(self, entry: WatchlistEntry) -> float:
        """
        Default scoring heuristic based on time to end.

        As time_to_end decreases, uncertainty decreases and score increases.
        This is a simple linear model; real implementations should use ML.

        Args:
            entry: The watchlist entry

        Returns:
            Estimated score
        """
        # Score increases as time decreases
        # At 720h: +0.00, at 48h: +0.05, at 6h: +0.07
        time_bonus = max(0, (720 - entry.time_to_end_hours) / 720) * 0.07

        return min(1.0, entry.initial_score + time_bonus)

    async def get_score_history(
        self,
        token_id: str,
    ) -> list[dict]:
        """
        Get score history for a token.

        Args:
            token_id: The token ID

        Returns:
            List of score records
        """
        query = """
            SELECT score, time_to_end_hours, scored_at
            FROM score_history
            WHERE token_id = $1
            ORDER BY scored_at ASC
        """
        records = await self._db.fetch(query, token_id)

        return [
            {
                "score": r["score"],
                "time_to_end_hours": r["time_to_end_hours"],
                "scored_at": datetime.fromtimestamp(r["scored_at"], tz=timezone.utc),
            }
            for r in records
        ]

    async def remove_expired(self, min_hours: float = 6.0) -> int:
        """
        Remove entries for markets that have expired or are expiring soon.

        Args:
            min_hours: Minimum hours remaining to keep entry

        Returns:
            Number of entries removed
        """
        now = int(datetime.now(timezone.utc).timestamp())
        query = """
            UPDATE trade_watchlist
            SET status = 'expired', updated_at = $2
            WHERE status = 'watching' AND time_to_end_hours < $1
        """
        result = await self._db.execute(query, min_hours, now)
        return int(result.split()[-1]) if result else 0
