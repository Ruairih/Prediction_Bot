"""
Candidate repository for the trading pipeline.

Handles:
- polymarket_candidates: Candidates awaiting decision
- candidate_watermarks: Tracks processing state
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import CandidateWatermark, PolymarketCandidate
from polymarket_bot.storage.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[PolymarketCandidate]):
    """
    Repository for trade candidates.

    A candidate is a trigger that's awaiting a trading decision.
    The workflow is: trigger → candidate → paper_trade or live_order
    """

    table_name = "polymarket_candidates"
    model_class = PolymarketCandidate

    async def create(self, candidate: PolymarketCandidate) -> PolymarketCandidate:
        """Create a new candidate."""
        query = """
            INSERT INTO polymarket_candidates
            (token_id, condition_id, threshold, trigger_timestamp, price, status,
             score, created_at, model_score, model_version, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            candidate.token_id,
            candidate.condition_id,
            candidate.threshold,
            candidate.trigger_timestamp,
            candidate.price,
            candidate.status,
            candidate.score,
            candidate.created_at,
            candidate.model_score,
            candidate.model_version,
            candidate.outcome,
            candidate.outcome_index,
        )
        return self._record_to_model(record)

    async def get_pending(self, limit: int = 100) -> list[PolymarketCandidate]:
        """Get candidates pending decision."""
        query = """
            SELECT * FROM polymarket_candidates
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT $1
        """
        records = await self.db.fetch(query, limit)
        return self._records_to_models(records)

    async def get_by_status(
        self, status: str, limit: int = 100
    ) -> list[PolymarketCandidate]:
        """Get candidates by status."""
        query = """
            SELECT * FROM polymarket_candidates
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, status, limit)
        return self._records_to_models(records)

    async def get_by_token(self, token_id: str) -> list[PolymarketCandidate]:
        """Get all candidates for a token."""
        query = """
            SELECT * FROM polymarket_candidates
            WHERE token_id = $1
            ORDER BY created_at DESC
        """
        records = await self.db.fetch(query, token_id)
        return self._records_to_models(records)

    async def update_status(
        self, candidate_id: int, status: str, score: Optional[float] = None
    ) -> Optional[PolymarketCandidate]:
        """Update candidate status."""
        now = datetime.utcnow().isoformat()
        if score is not None:
            query = """
                UPDATE polymarket_candidates
                SET status = $2, score = $3, updated_at = $4
                WHERE id = $1
                RETURNING *
            """
            record = await self.db.fetchrow(query, candidate_id, status, score, now)
        else:
            query = """
                UPDATE polymarket_candidates
                SET status = $2, updated_at = $3
                WHERE id = $1
                RETURNING *
            """
            record = await self.db.fetchrow(query, candidate_id, status, now)
        return self._record_to_model(record)

    async def approve(self, candidate_id: int) -> Optional[PolymarketCandidate]:
        """Mark candidate as approved."""
        return await self.update_status(candidate_id, "approved")

    async def reject(
        self, candidate_id: int, score: Optional[float] = None
    ) -> Optional[PolymarketCandidate]:
        """Mark candidate as rejected."""
        return await self.update_status(candidate_id, "rejected", score)

    async def mark_executed(self, candidate_id: int) -> Optional[PolymarketCandidate]:
        """Mark candidate as executed."""
        return await self.update_status(candidate_id, "executed")


class CandidateWatermarkRepository(BaseRepository[CandidateWatermark]):
    """Watermark repository for candidate processing."""

    table_name = "candidate_watermarks"
    model_class = CandidateWatermark

    async def get(self, threshold: float) -> Optional[CandidateWatermark]:
        """Get watermark for a threshold."""
        query = "SELECT * FROM candidate_watermarks WHERE threshold = $1"
        record = await self.db.fetchrow(query, threshold)
        return self._record_to_model(record)

    async def get_last_created_at(self, threshold: float) -> Optional[str]:
        """Get last processed created_at, or None if never processed."""
        query = "SELECT last_created_at FROM candidate_watermarks WHERE threshold = $1"
        return await self.db.fetchval(query, threshold)

    async def update(self, threshold: float, created_at: str) -> CandidateWatermark:
        """
        Update watermark with monotonic guarantee.

        Uses GREATEST() to ensure watermark never moves backwards,
        preventing duplicate processing from out-of-order events.
        """
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO candidate_watermarks (threshold, last_created_at, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (threshold) DO UPDATE
            SET last_created_at = GREATEST(candidate_watermarks.last_created_at, $2),
                updated_at = $3
            RETURNING *
        """
        record = await self.db.fetchrow(query, threshold, created_at, now)
        return self._record_to_model(record)
