"""
Approval repository for human-in-the-loop trading.

Handles:
- trade_approvals: Human approval records
- approval_alerts: Alerts pending approval
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import ApprovalAlert, TradeApproval
from polymarket_bot.storage.repositories.base import BaseRepository


class TradeApprovalRepository(BaseRepository[TradeApproval]):
    """Repository for trade approvals."""

    table_name = "trade_approvals"
    model_class = TradeApproval

    async def create(self, approval: TradeApproval) -> TradeApproval:
        """Create a trade approval."""
        query = """
            INSERT INTO trade_approvals
            (token_id, condition_id, approved_at, approved_by, max_price, expires_at, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (token_id) DO UPDATE
            SET condition_id = $2,
                approved_at = $3,
                approved_by = $4,
                max_price = $5,
                expires_at = $6,
                status = $7
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            approval.token_id,
            approval.condition_id,
            approval.approved_at,
            approval.approved_by,
            approval.max_price,
            approval.expires_at,
            approval.status,
        )
        return self._record_to_model(record)

    async def get_by_token(self, token_id: str) -> Optional[TradeApproval]:
        """Get approval for a token."""
        query = "SELECT * FROM trade_approvals WHERE token_id = $1"
        record = await self.db.fetchrow(query, token_id)
        return self._record_to_model(record)

    async def get_pending(self) -> list[TradeApproval]:
        """Get all pending approvals."""
        query = """
            SELECT * FROM trade_approvals
            WHERE status = 'pending'
            ORDER BY approved_at DESC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_valid(self, token_id: str, max_price: Decimal) -> Optional[TradeApproval]:
        """
        Get valid (non-expired, within price) approval for a token.

        Returns None if no valid approval exists.
        """
        now = datetime.utcnow().isoformat()
        query = """
            SELECT * FROM trade_approvals
            WHERE token_id = $1
              AND status = 'pending'
              AND max_price >= $2
              AND (expires_at IS NULL OR expires_at > $3)
        """
        record = await self.db.fetchrow(query, token_id, max_price, now)
        return self._record_to_model(record)

    async def mark_executed(self, token_id: str) -> Optional[TradeApproval]:
        """Mark approval as executed."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE trade_approvals
            SET status = 'executed', executed_at = $2
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id, now)
        return self._record_to_model(record)

    async def mark_expired(self, token_id: str) -> Optional[TradeApproval]:
        """Mark approval as expired."""
        query = """
            UPDATE trade_approvals
            SET status = 'expired'
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id)
        return self._record_to_model(record)

    async def expire_old(self) -> int:
        """Expire all past-due approvals. Returns count expired."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE trade_approvals
            SET status = 'expired'
            WHERE status = 'pending'
              AND expires_at IS NOT NULL
              AND expires_at < $1
        """
        result = await self.db.execute(query, now)
        # Parse "UPDATE N" to get count
        return int(result.split()[-1]) if result else 0


class ApprovalAlertRepository(BaseRepository[ApprovalAlert]):
    """Repository for approval alerts."""

    table_name = "approval_alerts"
    model_class = ApprovalAlert

    async def create(self, alert: ApprovalAlert) -> ApprovalAlert:
        """Create an approval alert."""
        query = """
            INSERT INTO approval_alerts
            (token_id, condition_id, question, price, model_score, alerted_at, approved)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (token_id) DO UPDATE
            SET condition_id = $2,
                question = $3,
                price = $4,
                model_score = $5,
                alerted_at = $6,
                approved = $7
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            alert.token_id,
            alert.condition_id,
            alert.question,
            alert.price,
            alert.model_score,
            alert.alerted_at,
            alert.approved,
        )
        return self._record_to_model(record)

    async def get_pending(self) -> list[ApprovalAlert]:
        """Get alerts pending approval."""
        query = """
            SELECT * FROM approval_alerts
            WHERE approved = FALSE
            ORDER BY alerted_at DESC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def approve(self, token_id: str) -> Optional[ApprovalAlert]:
        """Mark alert as approved."""
        query = """
            UPDATE approval_alerts
            SET approved = TRUE
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id)
        return self._record_to_model(record)

    async def delete_old(self, days: int = 7) -> int:
        """Delete alerts older than N days. Returns count deleted."""
        # Use make_interval for parameterized interval to prevent SQL injection
        query = """
            DELETE FROM approval_alerts
            WHERE alerted_at < NOW() - make_interval(days => $1)
        """
        result = await self.db.execute(query, days)
        return int(result.split()[-1]) if result else 0
