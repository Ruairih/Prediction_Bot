"""
Order Manager for submitting and tracking orders.

Handles order submission to Polymarket CLOB and status tracking.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .balance_manager import (
    BalanceManager,
    InsufficientBalanceError,
    PreSubmitValidationError,
)

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


class PriceTooHighError(PreSubmitValidationError):
    """Raised when order price exceeds maximum allowed."""

    def __init__(self, price: Decimal, max_price: Decimal):
        self.price = price
        self.max_price = max_price
        super().__init__(f"Price {price} exceeds maximum {max_price}")


class OrderSubmissionError(Exception):
    """Raised when CLOB order submission returns an invalid order ID."""


class OrderStatus(Enum):
    """Status of an order."""

    PENDING = "pending"
    LIVE = "live"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class OrderConfig:
    """Configuration for order submission."""

    max_price: Decimal = Decimal("0.95")  # Never buy above this
    position_size: Decimal = Decimal("20")  # Default position size
    min_balance_reserve: Decimal = Decimal("100")  # Keep this much in reserve


@dataclass
class Order:
    """Represents an order."""

    order_id: str
    token_id: str
    condition_id: str
    side: str  # "BUY" or "SELL"
    price: Decimal
    size: Decimal
    status: OrderStatus
    filled_size: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OrderManager:
    """
    Manages order submission and tracking.

    Handles:
    - Order submission with price and balance validation
    - Order status synchronization with CLOB
    - Order cancellation
    - Balance reservation management

    Usage:
        manager = OrderManager(db, clob_client, config)

        # Submit order
        order_id = await manager.submit_order(
            token_id="tok_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Sync status
        await manager.sync_order_status(order_id)
    """

    def __init__(
        self,
        db: "Database",
        clob_client: Optional[Any] = None,
        config: Optional[OrderConfig] = None,
        balance_manager: Optional[BalanceManager] = None,
    ) -> None:
        """
        Initialize the order manager.

        Args:
            db: Database connection
            clob_client: Polymarket CLOB client
            config: Order configuration
            balance_manager: Balance manager for reservations
        """
        self._db = db
        self._clob_client = clob_client
        self._config = config or OrderConfig()
        self._balance_manager = balance_manager or BalanceManager(db, clob_client)

        # Local order cache
        self._orders: Dict[str, Order] = {}

    @property
    def config(self) -> OrderConfig:
        """Get order configuration."""
        return self._config

    async def submit_order(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        condition_id: Optional[str] = None,
    ) -> str:
        """
        Submit an order to Polymarket CLOB.

        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            price: Order price
            size: Order size
            condition_id: Market condition ID (optional)

        Returns:
            Order ID

        Raises:
            PriceTooHighError: If price exceeds maximum
            InsufficientBalanceError: If not enough balance
        """
        # Normalize side to uppercase for consistency
        side = side.upper()

        # Validate price for BUY orders
        if side == "BUY" and price > self._config.max_price:
            raise PriceTooHighError(price, self._config.max_price)

        # Calculate order cost
        order_cost = price * size

        # Reserve balance (for BUY orders)
        temp_order_id = f"pending_{token_id}_{datetime.now(timezone.utc).timestamp()}"
        if side == "BUY":
            self._balance_manager.reserve(order_cost, temp_order_id)

        try:
            # Submit to CLOB
            order_id = await self._submit_to_clob(token_id, side, price, size)

            # CRITICAL FIX: Reject empty order IDs
            if not order_id or not str(order_id).strip():
                if side == "BUY":
                    self._balance_manager.release_reservation(temp_order_id)
                logger.error(
                    "CLOB returned empty order ID for %s order: %s @ %s (token=%s)",
                    side,
                    size,
                    price,
                    token_id,
                )
                raise OrderSubmissionError(
                    "CLOB returned empty order ID - submission may have failed"
                )
            order_id = str(order_id).strip()

            # Create order record
            now = datetime.now(timezone.utc)
            order = Order(
                order_id=order_id,
                token_id=token_id,
                condition_id=condition_id or "",
                side=side,
                price=price,
                size=size,
                status=OrderStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
            self._orders[order_id] = order

            # Persist to database
            await self._save_order(order)

            # Transfer reservation to real order ID
            if side == "BUY":
                self._balance_manager.release_reservation(temp_order_id)
                self._balance_manager.reserve(order_cost, order_id)

            logger.info(f"Submitted {side} order {order_id}: {size} @ {price}")
            return order_id

        except OrderSubmissionError:
            raise

        except InsufficientBalanceError:
            if side == "BUY":
                self._balance_manager.release_reservation(temp_order_id)
            raise

        except Exception as e:
            if side == "BUY":
                self._balance_manager.release_reservation(temp_order_id)
            logger.error(f"Failed to submit order: {e}")
            raise

    async def sync_order_status(self, order_id: str) -> Order:
        """
        Sync order status from CLOB.

        FIX: Properly handles partial fills and all CLOB statuses including
        FAILED, REJECTED, EXPIRED to prevent reservation leaks.

        Args:
            order_id: Order to sync

        Returns:
            Updated order
        """
        if not self._clob_client:
            return self._orders.get(order_id)

        try:
            get_order = self._clob_client.get_order
            if inspect.iscoroutinefunction(get_order):
                result = await get_order(order_id)
            else:
                result = await asyncio.to_thread(get_order, order_id)

            if order_id not in self._orders:
                # Create from CLOB data
                self._orders[order_id] = Order(
                    order_id=order_id,
                    token_id=result.get("tokenID", ""),
                    condition_id=result.get("conditionID", ""),
                    side=result.get("side", "BUY"),
                    price=Decimal(str(result.get("price", 0))),
                    size=Decimal(str(result.get("size", 0))),
                    status=OrderStatus.PENDING,
                )

            order = self._orders[order_id]
            previous_filled = order.filled_size
            previous_avg_price = order.avg_fill_price

            # Update status - handle ALL CLOB statuses including edge cases
            clob_status = result.get("status", "").upper()
            filled_size = Decimal(str(result.get("filledSize", 0)))
            size = Decimal(str(result.get("size", order.size)))

            if clob_status == "MATCHED" or filled_size >= size:
                order.status = OrderStatus.FILLED
            elif filled_size > 0:
                order.status = OrderStatus.PARTIAL
            elif clob_status == "LIVE":
                order.status = OrderStatus.LIVE
            elif clob_status == "CANCELLED":
                order.status = OrderStatus.CANCELLED
            elif clob_status in ("FAILED", "REJECTED", "EXPIRED"):
                # FIX: Handle these statuses that were previously unmapped
                order.status = OrderStatus.FAILED
                logger.warning(f"Order {order_id} has status {clob_status}")
            # Unknown statuses remain in current state (PENDING)

            order.filled_size = filled_size
            if result.get("avgPrice"):
                order.avg_fill_price = Decimal(str(result["avgPrice"]))
            order.updated_at = datetime.now(timezone.utc)

            # Update database
            await self._save_order(order)

            # Handle fill - manage reservations properly (G4 protection)
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED):
                # Terminal states - release full reservation
                self._balance_manager.release_reservation(order_id)
                self._balance_manager.refresh_balance()  # G4 protection

            elif order.status == OrderStatus.PARTIAL:
                # FIX: Partial fill - adjust reservation for the filled portion
                new_filled = filled_size - previous_filled
                if new_filled > 0:
                    fill_price = order.avg_fill_price or order.price
                    if order.avg_fill_price and previous_avg_price:
                        filled_cost = (filled_size * order.avg_fill_price) - (
                            previous_filled * previous_avg_price
                        )
                    else:
                        filled_cost = new_filled * fill_price
                    if filled_cost > 0:
                        self._balance_manager.adjust_reservation_for_partial_fill(
                            order_id,
                            filled_cost,
                        )
                self._balance_manager.refresh_balance()  # G4 protection

            logger.debug(f"Order {order_id} status: {order.status.value}")
            return order

        except Exception as e:
            logger.error(f"Failed to sync order {order_id}: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order to cancel

        Returns:
            True if cancelled successfully
        """
        if not self._clob_client:
            return False

        try:
            self._clob_client.cancel(order_id)

            if order_id in self._orders:
                order = self._orders[order_id]
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now(timezone.utc)
                await self._save_order(order)

            # Release reservation
            self._balance_manager.release_reservation(order_id)

            logger.info(f"Cancelled order {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get an order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order if found
        """
        return self._orders.get(order_id)

    def get_open_orders(self) -> List[Order]:
        """
        Get all open orders.

        Returns:
            List of orders that are pending, live, or partial
        """
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.LIVE, OrderStatus.PARTIAL)
        ]

    def get_filled_orders(self) -> List[Order]:
        """
        Get all filled orders.

        Returns:
            List of filled orders
        """
        return [
            o for o in self._orders.values()
            if o.status == OrderStatus.FILLED
        ]

    def get_available_balance(self) -> Decimal:
        """
        Get available balance for trading.

        Returns:
            Available balance
        """
        return self._balance_manager.get_available_balance()

    def refresh_balance(self) -> Decimal:
        """
        Refresh balance from CLOB (G4 protection).

        Returns:
            Fresh balance
        """
        return self._balance_manager.refresh_balance()

    async def _submit_to_clob(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
    ) -> str:
        """Submit order to CLOB and return order ID."""
        if not self._clob_client:
            # Mock order ID for testing
            return f"mock_order_{datetime.now(timezone.utc).timestamp()}"

        try:
            # py-clob-client requires OrderArgs object, not kwargs
            from py_clob_client.clob_types import OrderArgs

            order_args = OrderArgs(
                token_id=token_id,
                side=side.upper(),  # Ensure uppercase (BUY/SELL)
                price=float(price),
                size=float(size),
            )

            # Create and post order in one call
            result = self._clob_client.create_and_post_order(order_args)

            # Result may be the order dict or have nested structure
            if isinstance(result, dict):
                return result.get("orderID", result.get("order_id", result.get("id", "")))
            return str(result) if result else ""

        except Exception as e:
            # Check for balance error
            if "insufficient" in str(e).lower() or "balance" in str(e).lower():
                raise InsufficientBalanceError(
                    required=price * size,
                    available=self._balance_manager.get_available_balance(),
                )
            raise

    async def _save_order(self, order: Order) -> None:
        """Persist order to database."""
        now = int(datetime.now(timezone.utc).timestamp())

        query = """
            INSERT INTO orders
            (order_id, token_id, condition_id, side, price, size, filled_size,
             avg_fill_price, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
            ON CONFLICT (order_id) DO UPDATE
            SET filled_size = $7,
                avg_fill_price = $8,
                status = $9,
                updated_at = $10
        """
        await self._db.execute(
            query,
            order.order_id,
            order.token_id,
            order.condition_id,
            order.side,
            float(order.price),
            float(order.size),
            float(order.filled_size),
            float(order.avg_fill_price) if order.avg_fill_price else None,
            order.status.value,
            now,
        )

    async def load_orders(self) -> int:
        """
        Load open orders from database on startup.

        Restores orders that are pending, live, or partial.
        Also restores balance reservations for these orders.

        Returns:
            Number of orders loaded
        """
        query = """
            SELECT order_id, token_id, condition_id, side, price, size,
                   filled_size, avg_fill_price, status, created_at, updated_at
            FROM orders
            WHERE status IN ('pending', 'live', 'partial')
        """
        records = await self._db.fetch(query)

        count = 0
        for record in records:
            try:
                order = Order(
                    order_id=record["order_id"],
                    token_id=record["token_id"],
                    condition_id=record["condition_id"],
                    side=record["side"],
                    price=Decimal(str(record["price"])),
                    size=Decimal(str(record["size"])),
                    status=OrderStatus(record["status"]),
                    filled_size=Decimal(str(record["filled_size"] or 0)),
                    avg_fill_price=Decimal(str(record["avg_fill_price"]))
                    if record["avg_fill_price"]
                    else None,
                    created_at=datetime.fromtimestamp(
                        record["created_at"], tz=timezone.utc
                    )
                    if record["created_at"]
                    else None,
                    updated_at=datetime.fromtimestamp(
                        record["updated_at"], tz=timezone.utc
                    )
                    if record["updated_at"]
                    else None,
                )

                # Restore balance reservation for unfilled portion BEFORE caching
                # This ensures we don't have an order in cache without reservation
                # Only BUY orders reserve balance (SELL orders don't consume balance)
                unfilled_size = order.size - order.filled_size
                reservation_failed = False

                if order.side == "BUY" and unfilled_size > Decimal("0"):
                    reservation_amount = order.price * unfilled_size
                    try:
                        self._balance_manager.reserve(
                            amount=reservation_amount,
                            order_id=order.order_id,
                        )
                        logger.debug(
                            f"Restored reservation {reservation_amount} for order {order.order_id}"
                        )
                    except InsufficientBalanceError as e:
                        # Still track the order (it's real on CLOB) but warn about balance
                        reservation_failed = True
                        logger.warning(
                            f"Could not restore full reservation for order {order.order_id}: "
                            f"required {reservation_amount}, {e}. Order will still be tracked."
                        )

                # Add to local cache after reservation attempt
                self._orders[order.order_id] = order
                count += 1

                if reservation_failed:
                    logger.warning(
                        f"Order {order.order_id} loaded without full reservation - "
                        f"balance may be insufficient for new orders"
                    )

            except Exception as e:
                logger.error(f"Error loading order {record.get('order_id')}: {e}")

        logger.info(f"Loaded {count} open orders from database")
        return count
