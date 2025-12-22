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
    token_id: str
    condition_id: str
    exit_type: str  # e.g., "profit_target", "stop_loss", "resolution", "manual"
    entry_price: Decimal
    exit_price: Decimal
    size: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal  # After fees (for now same as gross)
    hours_held: float
    reason: str
    created_at: datetime
    exit_order_id: Optional[str] = None
    status: str = "pending"  # pending, executed, failed


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

        Handles both full fills (FILLED) and partial fills (PARTIAL).
        For partial fills, uses filled_size instead of total size.

        Args:
            order: Order with fill (FILLED or PARTIAL status)

        Returns:
            Position that was created or updated
        """
        # Accept both FILLED and PARTIAL orders
        if order.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            return None

        # Use filled_size for partial fills, or full size for complete fills
        fill_size = order.filled_size
        if fill_size <= Decimal("0"):
            return None  # No fill to record

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

    async def record_fill_delta(
        self,
        order: Order,
        delta_size: Decimal,
    ) -> Optional[Position]:
        """
        Record a fill delta and create/update position.

        Unlike record_fill which uses order.filled_size, this method
        explicitly takes the delta size to avoid double-counting when
        called multiple times during partial fill syncs.

        Args:
            order: Order with fill information (for price, token_id, etc.)
            delta_size: The NEW fill amount to add (not total filled)

        Returns:
            Position that was created or updated
        """
        if delta_size <= Decimal("0"):
            return None

        fill_price = order.avg_fill_price or order.price

        # Check for existing position
        existing_position_id = self._token_positions.get(order.token_id)

        if existing_position_id and existing_position_id in self.positions:
            # Aggregate with existing position
            position = self.positions[existing_position_id]

            if order.side == "BUY":
                # Add to position - calculate weighted average price
                old_cost = position.entry_cost
                new_cost = delta_size * fill_price
                total_size = position.size + delta_size
                total_cost = old_cost + new_cost

                position.size = total_size
                position.entry_cost = total_cost
                position.entry_price = total_cost / total_size if total_size > 0 else Decimal("0")

            else:  # SELL - reduce position
                sell_ratio = delta_size / position.size if position.size > 0 else Decimal("1")
                position.size -= delta_size
                position.entry_cost -= position.entry_cost * sell_ratio

                # Realized P&L for this exit
                pnl = delta_size * (fill_price - position.entry_price)
                position.realized_pnl += pnl

                if position.size <= 0:
                    position.status = "closed"
                    if order.token_id in self._token_positions:
                        del self._token_positions[order.token_id]

            await self._save_position(position)
            logger.info(f"Updated position {position.position_id}: +{delta_size} (total size={position.size})")
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
                size=delta_size,
                entry_price=fill_price,
                entry_cost=delta_size * fill_price,
                entry_time=now,
            )

            self.positions[position_id] = position
            self._token_positions[order.token_id] = position_id

            await self._save_position(position)
            logger.info(f"Created position {position_id}: {delta_size} @ {fill_price}")
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

        # Calculate hours held
        now = datetime.now(timezone.utc)
        hours_held = (now - position.entry_time).total_seconds() / 3600

        # Create exit event with all schema-required fields
        exit_event = ExitEvent(
            position_id=position_id,
            token_id=position.token_id,
            condition_id=position.condition_id,
            exit_type=reason,  # reason serves as exit_type
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            gross_pnl=pnl,
            net_pnl=pnl,  # Same as gross for now (no fee tracking yet)
            hours_held=hours_held,
            reason=reason,
            created_at=now,
            status="pending",
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
            SELECT id AS position_id, token_id, condition_id, size, entry_price,
                   entry_cost, entry_timestamp AS entry_time, realized_pnl, status
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
            (token_id, condition_id, size, entry_price, entry_cost,
             entry_timestamp, realized_pnl, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (token_id, entry_timestamp) DO UPDATE
            SET size = $3,
                entry_price = $4,
                entry_cost = $5,
                realized_pnl = $7,
                status = $8
        """
        await self._db.execute(
            query,
            position.token_id,
            position.condition_id,
            float(position.size),
            float(position.entry_price),
            float(position.entry_cost),
            position.entry_time.isoformat(),
            float(position.realized_pnl),
            position.status,
            position.entry_time.isoformat(),  # created_at
        )

    async def _save_exit_event(self, event: ExitEvent) -> None:
        """Persist exit event to database."""
        query = """
            INSERT INTO exit_events
            (position_id, token_id, condition_id, exit_type, entry_price,
             exit_price, size, gross_pnl, net_pnl, hours_held,
             exit_order_id, status, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        """
        await self._db.execute(
            query,
            event.position_id,  # Note: schema expects INTEGER but we use string
            event.token_id,
            event.condition_id,
            event.exit_type,
            float(event.entry_price),
            float(event.exit_price),
            float(event.size),
            float(event.gross_pnl),
            float(event.net_pnl),
            event.hours_held,
            event.exit_order_id,
            event.status,
            event.reason,
            event.created_at.isoformat(),
        )
