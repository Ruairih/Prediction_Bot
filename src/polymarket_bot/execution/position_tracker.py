"""
Position Tracker for managing open positions.

Tracks positions created from filled orders and calculates P&L.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

from .order_manager import Order, OrderStatus

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open position."""

    position_id: str
    token_id: str
    condition_id: str
    size: Decimal
    entry_price: Decimal
    entry_cost: Decimal  # size * entry_price
    entry_time: datetime
    realized_pnl: Decimal = Decimal("0")
    status: str = "open"  # open, closed


@dataclass
class ExitEvent:
    """Records a position exit."""

    position_id: str
    exit_price: Decimal
    exit_size: Decimal
    realized_pnl: Decimal
    reason: str
    exit_time: datetime


class PositionTracker:
    """
    Tracks positions and calculates P&L.

    Handles:
    - Creating positions from filled orders
    - Aggregating multiple fills for same token
    - Calculating unrealized P&L
    - Recording exits

    Usage:
        tracker = PositionTracker(db)

        # Record a fill
        await tracker.record_fill(filled_order)

        # Get positions
        positions = tracker.get_open_positions()

        # Calculate P&L
        pnl = tracker.calculate_pnl(position_id, current_price)

        # Close position
        await tracker.close_position(position_id, exit_price, "profit_target")
    """

    def __init__(self, db: "Database") -> None:
        """
        Initialize the position tracker.

        Args:
            db: Database connection
        """
        self._db = db

        # Position cache by position_id
        self.positions: Dict[str, Position] = {}

        # Position lookup by token_id
        self._token_positions: Dict[str, str] = {}  # token_id -> position_id

        # Exit events
        self._exit_events: Dict[str, List[ExitEvent]] = {}

    async def record_fill(self, order: Order) -> Optional[Position]:
        """
        Record a fill and create/update position.

        Args:
            order: Filled order

        Returns:
            Position that was created or updated
        """
        if order.status != OrderStatus.FILLED:
            return None

        fill_size = order.filled_size or order.size
        fill_price = order.avg_fill_price or order.price

        # Check for existing position
        existing_position_id = self._token_positions.get(order.token_id)

        if existing_position_id and existing_position_id in self.positions:
            # Aggregate with existing position
            position = self.positions[existing_position_id]

            if order.side == "BUY":
                # Add to position - calculate weighted average price
                old_cost = position.entry_cost
                new_cost = fill_size * fill_price
                total_size = position.size + fill_size
                total_cost = old_cost + new_cost

                position.size = total_size
                position.entry_cost = total_cost
                position.entry_price = total_cost / total_size if total_size > 0 else Decimal("0")

            else:  # SELL - reduce position
                # Reduce position size and entry cost proportionally
                sell_ratio = fill_size / position.size if position.size > 0 else Decimal("1")
                position.size -= fill_size
                position.entry_cost -= position.entry_cost * sell_ratio

                # Realized P&L for this exit
                pnl = fill_size * (fill_price - position.entry_price)
                position.realized_pnl += pnl

                if position.size <= 0:
                    position.status = "closed"
                    # Clear token position mapping so new BUYs create fresh positions
                    if order.token_id in self._token_positions:
                        del self._token_positions[order.token_id]

            await self._save_position(position)
            logger.info(f"Updated position {position.position_id}: size={position.size}")
            return position

        else:
            # Create new position (only for BUY)
            if order.side != "BUY":
                return None

            position_id = f"pos_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc)

            position = Position(
                position_id=position_id,
                token_id=order.token_id,
                condition_id=order.condition_id,
                size=fill_size,
                entry_price=fill_price,
                entry_cost=fill_size * fill_price,
                entry_time=now,
            )

            self.positions[position_id] = position
            self._token_positions[order.token_id] = position_id

            await self._save_position(position)
            logger.info(f"Created position {position_id}: {fill_size} @ {fill_price}")
            return position

    def get_open_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of open positions
        """
        return [p for p in self.positions.values() if p.status == "open"]

    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get a specific position.

        Args:
            position_id: Position ID

        Returns:
            Position if found
        """
        return self.positions.get(position_id)

    def get_position_by_token(self, token_id: str) -> Optional[Position]:
        """
        Get position for a token.

        Args:
            token_id: Token ID

        Returns:
            Position if exists
        """
        position_id = self._token_positions.get(token_id)
        if position_id:
            return self.positions.get(position_id)
        return None

    def calculate_pnl(
        self,
        position_id: str,
        current_price: Decimal,
    ) -> Decimal:
        """
        Calculate unrealized P&L for a position.

        Args:
            position_id: Position to calculate
            current_price: Current market price

        Returns:
            Unrealized P&L (positive = profit, negative = loss)
        """
        position = self.positions.get(position_id)
        if not position:
            return Decimal("0")

        # PnL = size * (current - entry)
        return position.size * (current_price - position.entry_price)

    def calculate_total_pnl(
        self,
        current_prices: Dict[str, Decimal],
    ) -> Decimal:
        """
        Calculate total P&L across all positions.

        Args:
            current_prices: Dict of token_id -> current_price

        Returns:
            Total unrealized P&L
        """
        total = Decimal("0")
        for position in self.get_open_positions():
            price = current_prices.get(position.token_id)
            if price is not None:
                total += self.calculate_pnl(position.position_id, price)
        return total

    async def close_position(
        self,
        position_id: str,
        exit_price: Decimal,
        reason: str,
    ) -> Optional[ExitEvent]:
        """
        Close a position.

        Args:
            position_id: Position to close
            exit_price: Exit price
            reason: Reason for exit (e.g., "profit_target", "stop_loss", "resolution")

        Returns:
            Exit event record
        """
        position = self.positions.get(position_id)
        if not position:
            return None

        # Calculate realized P&L
        pnl = position.size * (exit_price - position.entry_price)

        # Create exit event
        now = datetime.now(timezone.utc)
        exit_event = ExitEvent(
            position_id=position_id,
            exit_price=exit_price,
            exit_size=position.size,
            realized_pnl=pnl,
            reason=reason,
            exit_time=now,
        )

        # Store exit event
        if position_id not in self._exit_events:
            self._exit_events[position_id] = []
        self._exit_events[position_id].append(exit_event)

        # Update position
        position.status = "closed"
        position.realized_pnl += pnl
        position.size = Decimal("0")

        # Clear token position mapping so new BUYs create fresh positions
        if position.token_id in self._token_positions:
            del self._token_positions[position.token_id]

        await self._save_position(position)
        await self._save_exit_event(exit_event)

        logger.info(
            f"Closed position {position_id}: exit={exit_price}, pnl={pnl}, reason={reason}"
        )

        return exit_event

    def get_exit_events(self, position_id: str) -> List[ExitEvent]:
        """
        Get exit events for a position.

        Args:
            position_id: Position ID

        Returns:
            List of exit events
        """
        return self._exit_events.get(position_id, [])

    async def load_positions(self) -> None:
        """Load positions from database."""
        query = """
            SELECT position_id, token_id, condition_id, size, entry_price,
                   entry_cost, entry_time, realized_pnl, status
            FROM positions
            WHERE status = 'open'
        """
        records = await self._db.fetch(query)

        for r in records:
            position = Position(
                position_id=r["position_id"],
                token_id=r["token_id"],
                condition_id=r["condition_id"],
                size=Decimal(str(r["size"])),
                entry_price=Decimal(str(r["entry_price"])),
                entry_cost=Decimal(str(r["entry_cost"])),
                entry_time=datetime.fromisoformat(r["entry_time"]) if isinstance(r["entry_time"], str) else r["entry_time"],
                realized_pnl=Decimal(str(r.get("realized_pnl", 0))),
                status=r["status"],
            )
            self.positions[position.position_id] = position
            self._token_positions[position.token_id] = position.position_id

    async def _save_position(self, position: Position) -> None:
        """Persist position to database."""
        query = """
            INSERT INTO positions
            (position_id, token_id, condition_id, size, entry_price, entry_cost,
             entry_time, realized_pnl, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (position_id) DO UPDATE
            SET size = $4,
                entry_price = $5,
                entry_cost = $6,
                realized_pnl = $8,
                status = $9
        """
        await self._db.execute(
            query,
            position.position_id,
            position.token_id,
            position.condition_id,
            float(position.size),
            float(position.entry_price),
            float(position.entry_cost),
            position.entry_time.isoformat(),
            float(position.realized_pnl),
            position.status,
        )

    async def _save_exit_event(self, event: ExitEvent) -> None:
        """Persist exit event to database."""
        query = """
            INSERT INTO exit_events
            (position_id, exit_price, exit_size, realized_pnl, reason, exit_time)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await self._db.execute(
            query,
            event.position_id,
            float(event.exit_price),
            float(event.exit_size),
            float(event.realized_pnl),
            event.reason,
            event.exit_time.isoformat(),
        )
