"""
Order repository for paper and live trading.

Handles:
- paper_trades: Simulated trades for backtesting/paper trading
- live_orders: Real orders submitted to Polymarket
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import LiveOrder, PaperTrade
from polymarket_bot.storage.repositories.base import BaseRepository


class PaperTradeRepository(BaseRepository[PaperTrade]):
    """Repository for paper (simulated) trades."""

    table_name = "paper_trades"
    model_class = PaperTrade

    async def create(self, trade: PaperTrade) -> PaperTrade:
        """Create a paper trade record."""
        query = """
            INSERT INTO paper_trades
            (candidate_id, token_id, condition_id, threshold, trigger_timestamp,
             candidate_price, fill_price, size, model_score, model_version,
             decision, reason, created_at, description, outcome, outcome_index)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            trade.candidate_id,
            trade.token_id,
            trade.condition_id,
            trade.threshold,
            trade.trigger_timestamp,
            trade.candidate_price,
            trade.fill_price,
            trade.size,
            trade.model_score,
            trade.model_version,
            trade.decision,
            trade.reason,
            trade.created_at,
            trade.description,
            trade.outcome,
            trade.outcome_index,
        )
        return self._record_to_model(record)

    async def get_by_candidate(self, candidate_id: int) -> Optional[PaperTrade]:
        """Get paper trade for a candidate."""
        query = "SELECT * FROM paper_trades WHERE candidate_id = $1"
        record = await self.db.fetchrow(query, candidate_id)
        return self._record_to_model(record)

    async def get_recent(self, limit: int = 100) -> list[PaperTrade]:
        """Get recent paper trades."""
        query = """
            SELECT * FROM paper_trades
            ORDER BY created_at DESC
            LIMIT $1
        """
        records = await self.db.fetch(query, limit)
        return self._records_to_models(records)

    async def get_by_decision(
        self, decision: str, limit: int = 100
    ) -> list[PaperTrade]:
        """Get paper trades by decision type."""
        query = """
            SELECT * FROM paper_trades
            WHERE decision = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, decision, limit)
        return self._records_to_models(records)


class LiveOrderRepository(BaseRepository[LiveOrder]):
    """Repository for live orders submitted to Polymarket."""

    table_name = "live_orders"
    model_class = LiveOrder

    async def create(self, order: LiveOrder) -> LiveOrder:
        """Create a live order record."""
        query = """
            INSERT INTO live_orders
            (order_id, candidate_id, token_id, condition_id, threshold,
             order_price, order_size, status, reason, submitted_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            order.order_id,
            order.candidate_id,
            order.token_id,
            order.condition_id,
            order.threshold,
            order.order_price,
            order.order_size,
            order.status,
            order.reason,
            order.submitted_at,
        )
        return self._record_to_model(record)

    async def get_by_order_id(self, order_id: str) -> Optional[LiveOrder]:
        """Get order by Polymarket order ID."""
        query = "SELECT * FROM live_orders WHERE order_id = $1"
        record = await self.db.fetchrow(query, order_id)
        return self._record_to_model(record)

    async def get_active(self) -> list[LiveOrder]:
        """Get all active (non-terminal) orders."""
        query = """
            SELECT * FROM live_orders
            WHERE status IN ('submitted', 'partial')
            ORDER BY submitted_at DESC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_by_status(self, status: str, limit: int = 100) -> list[LiveOrder]:
        """Get orders by status."""
        query = """
            SELECT * FROM live_orders
            WHERE status = $1
            ORDER BY submitted_at DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, status, limit)
        return self._records_to_models(records)

    async def get_by_token(self, token_id: str) -> list[LiveOrder]:
        """Get all orders for a token."""
        query = """
            SELECT * FROM live_orders
            WHERE token_id = $1
            ORDER BY submitted_at DESC
        """
        records = await self.db.fetch(query, token_id)
        return self._records_to_models(records)

    async def update_status(
        self,
        order_id: str,
        status: str,
        fill_price: Optional[float] = None,
        fill_size: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> Optional[LiveOrder]:
        """Update order status and optionally fill details."""
        now = datetime.utcnow().isoformat()
        filled_at = now if status == "filled" else None

        query = """
            UPDATE live_orders
            SET status = $2,
                fill_price = COALESCE($3, fill_price),
                fill_size = COALESCE($4, fill_size),
                reason = COALESCE($5, reason),
                filled_at = COALESCE($6, filled_at),
                updated_at = $7
            WHERE order_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(
            query, order_id, status, fill_price, fill_size, reason, filled_at, now
        )
        return self._record_to_model(record)

    async def mark_filled(
        self, order_id: str, fill_price: float, fill_size: float
    ) -> Optional[LiveOrder]:
        """Mark order as filled."""
        return await self.update_status(
            order_id, "filled", fill_price=fill_price, fill_size=fill_size
        )

    async def mark_cancelled(
        self, order_id: str, reason: Optional[str] = None
    ) -> Optional[LiveOrder]:
        """Mark order as cancelled."""
        return await self.update_status(order_id, "cancelled", reason=reason)

    async def mark_rejected(
        self, order_id: str, reason: str
    ) -> Optional[LiveOrder]:
        """Mark order as rejected."""
        return await self.update_status(order_id, "rejected", reason=reason)
