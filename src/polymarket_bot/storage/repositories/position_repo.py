"""
Position repository for tracking trading positions.

Handles:
- positions: Open and closed positions
- exit_events: Exit event records
- daily_pnl: Daily P&L summaries
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import DailyPnl, ExitEvent, Position
from polymarket_bot.storage.repositories.base import BaseRepository


class PositionRepository(BaseRepository[Position]):
    """Repository for trading positions."""

    table_name = "positions"
    model_class = Position

    async def create(self, position: Position) -> Position:
        """Create a new position."""
        query = """
            INSERT INTO positions
            (token_id, condition_id, market_id, outcome, outcome_index, side,
             size, entry_price, entry_cost, current_price, current_value,
             unrealized_pnl, realized_pnl, status, entry_order_id,
             entry_timestamp, description, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            position.token_id,
            position.condition_id,
            position.market_id,
            position.outcome,
            position.outcome_index,
            position.side,
            position.size,
            position.entry_price,
            position.entry_cost,
            position.current_price,
            position.current_value,
            position.unrealized_pnl,
            position.realized_pnl,
            position.status,
            position.entry_order_id,
            position.entry_timestamp,
            position.description,
            position.created_at,
        )
        return self._record_to_model(record)

    async def get_open(self) -> list[Position]:
        """Get all open positions."""
        query = """
            SELECT * FROM positions
            WHERE status = 'open'
            ORDER BY created_at DESC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_by_status(self, status: str, limit: int = 100) -> list[Position]:
        """Get positions by status."""
        query = """
            SELECT * FROM positions
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, status, limit)
        return self._records_to_models(records)

    async def get_by_token(self, token_id: str) -> list[Position]:
        """Get all positions for a token."""
        query = """
            SELECT * FROM positions
            WHERE token_id = $1
            ORDER BY created_at DESC
        """
        records = await self.db.fetch(query, token_id)
        return self._records_to_models(records)

    async def get_open_by_token(self, token_id: str) -> Optional[Position]:
        """Get open position for a token (should be at most one)."""
        query = """
            SELECT * FROM positions
            WHERE token_id = $1 AND status = 'open'
            LIMIT 1
        """
        record = await self.db.fetchrow(query, token_id)
        return self._record_to_model(record)

    async def update_price(
        self, position_id: int, current_price: float
    ) -> Optional[Position]:
        """Update position's current price and recalculate P&L."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE positions
            SET current_price = $2,
                current_value = size * $2,
                unrealized_pnl = (size * $2) - entry_cost,
                updated_at = $3
            WHERE id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, position_id, current_price, now)
        return self._record_to_model(record)

    async def close(
        self,
        position_id: int,
        exit_price: float,
        exit_order_id: Optional[str] = None,
        realized_pnl: Optional[float] = None,
    ) -> Optional[Position]:
        """Close a position."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE positions
            SET status = 'closed',
                current_price = $2,
                current_value = size * $2,
                realized_pnl = COALESCE($4, (size * $2) - entry_cost),
                unrealized_pnl = 0,
                exit_order_id = $3,
                exit_timestamp = $5,
                updated_at = $5
            WHERE id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(
            query, position_id, exit_price, exit_order_id, realized_pnl, now
        )
        return self._record_to_model(record)

    async def resolve(
        self,
        position_id: int,
        resolution: str,
        final_value: float,
    ) -> Optional[Position]:
        """Mark position as resolved by market outcome."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE positions
            SET status = 'resolved',
                resolution = $2,
                current_value = $3,
                realized_pnl = $3 - entry_cost,
                unrealized_pnl = 0,
                resolved_at = $4,
                updated_at = $4
            WHERE id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, position_id, resolution, final_value, now)
        return self._record_to_model(record)

    async def get_total_exposure(self) -> float:
        """Get total capital at risk in open positions."""
        query = "SELECT COALESCE(SUM(entry_cost), 0) FROM positions WHERE status = 'open'"
        return await self.db.fetchval(query)


class ExitEventRepository(BaseRepository[ExitEvent]):
    """Repository for exit events."""

    table_name = "exit_events"
    model_class = ExitEvent

    async def create(self, event: ExitEvent) -> ExitEvent:
        """Create an exit event."""
        query = """
            INSERT INTO exit_events
            (position_id, token_id, condition_id, exit_type, entry_price,
             exit_price, size, gross_pnl, net_pnl, hours_held,
             exit_order_id, status, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            event.position_id,
            event.token_id,
            event.condition_id,
            event.exit_type,
            event.entry_price,
            event.exit_price,
            event.size,
            event.gross_pnl,
            event.net_pnl,
            event.hours_held,
            event.exit_order_id,
            event.status,
            event.reason,
            event.created_at,
        )
        return self._record_to_model(record)

    async def get_pending(self) -> list[ExitEvent]:
        """Get pending exit events."""
        query = """
            SELECT * FROM exit_events
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_by_position(self, position_id: str) -> list[ExitEvent]:
        """Get exit events for a position."""
        query = """
            SELECT * FROM exit_events
            WHERE position_id = $1
            ORDER BY created_at DESC
        """
        records = await self.db.fetch(query, position_id)
        return self._records_to_models(records)

    async def mark_executed(self, event_id: int) -> Optional[ExitEvent]:
        """Mark exit event as executed."""
        now = datetime.utcnow().isoformat()
        query = """
            UPDATE exit_events
            SET status = 'executed', executed_at = $2
            WHERE id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, event_id, now)
        return self._record_to_model(record)

    async def mark_failed(self, event_id: int, reason: str) -> Optional[ExitEvent]:
        """Mark exit event as failed."""
        query = """
            UPDATE exit_events
            SET status = 'failed', reason = $2
            WHERE id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, event_id, reason)
        return self._record_to_model(record)


class DailyPnlRepository(BaseRepository[DailyPnl]):
    """Repository for daily P&L summaries."""

    table_name = "daily_pnl"
    model_class = DailyPnl

    async def get_or_create(self, date: str) -> DailyPnl:
        """Get or create daily P&L record."""
        query = """
            INSERT INTO daily_pnl (date)
            VALUES ($1)
            ON CONFLICT (date) DO UPDATE SET date = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, date)
        return self._record_to_model(record)

    async def update(
        self,
        date: str,
        realized_pnl: float,
        unrealized_pnl: float,
        num_trades: int,
        num_wins: int,
        num_losses: int,
    ) -> DailyPnl:
        """Update daily P&L."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO daily_pnl
            (date, realized_pnl, unrealized_pnl, total_pnl, num_trades, num_wins, num_losses, updated_at)
            VALUES ($1, $2, $3, $2 + $3, $4, $5, $6, $7)
            ON CONFLICT (date) DO UPDATE
            SET realized_pnl = $2,
                unrealized_pnl = $3,
                total_pnl = $2 + $3,
                num_trades = $4,
                num_wins = $5,
                num_losses = $6,
                updated_at = $7
            RETURNING *
        """
        record = await self.db.fetchrow(
            query, date, realized_pnl, unrealized_pnl, num_trades, num_wins, num_losses, now
        )
        return self._record_to_model(record)

    async def get_recent(self, days: int = 30) -> list[DailyPnl]:
        """Get recent daily P&L records."""
        query = """
            SELECT * FROM daily_pnl
            ORDER BY date DESC
            LIMIT $1
        """
        records = await self.db.fetch(query, days)
        return self._records_to_models(records)

    async def get_total_realized(self) -> float:
        """Get all-time realized P&L."""
        query = "SELECT COALESCE(SUM(realized_pnl), 0) FROM daily_pnl"
        return await self.db.fetchval(query)
