"""
ExecutionService - Facade for coordinating order execution.

Coordinates OrderManager, PositionTracker, ExitManager, and BalanceManager
to handle the full lifecycle of trades.

This is the primary interface the TradingEngine uses to execute trades.
The engine should not call individual managers directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, List, Optional

from .balance_manager import (
    BalanceConfig,
    BalanceManager,
    InsufficientBalanceError,
    PreSubmitValidationError,
)
from .exit_manager import ExitConfig, ExitManager
from .order_manager import Order, OrderConfig, OrderManager, OrderStatus, PriceTooHighError
from .position_tracker import ExitEvent, Position, PositionTracker

if TYPE_CHECKING:
    from polymarket_bot.storage import Database
    from polymarket_bot.strategies import EntrySignal, ExitSignal, StrategyContext

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for the execution service."""

    # Order configuration
    max_price: Decimal = Decimal("0.95")
    default_position_size: Decimal = Decimal("20")
    min_balance_reserve: Decimal = Decimal("100")

    # Exit configuration
    profit_target: Decimal = Decimal("0.99")
    stop_loss: Decimal = Decimal("0.90")
    min_hold_days: int = 7

    # Fill confirmation
    wait_for_fill: bool = True
    fill_timeout_seconds: float = 30.0

    @property
    def order_config(self) -> OrderConfig:
        """Get order configuration."""
        return OrderConfig(
            max_price=self.max_price,
            position_size=self.default_position_size,
            min_balance_reserve=self.min_balance_reserve,
        )

    @property
    def balance_config(self) -> BalanceConfig:
        """Get balance configuration."""
        return BalanceConfig(min_reserve=self.min_balance_reserve)

    @property
    def exit_config(self) -> ExitConfig:
        """Get exit configuration."""
        return ExitConfig(
            profit_target=self.profit_target,
            stop_loss=self.stop_loss,
            min_hold_days=self.min_hold_days,
        )


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""

    success: bool
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # "price_too_high", "insufficient_balance", etc.


class ExecutionService:
    """
    Coordinates execution layer components for trading.

    This service handles the full lifecycle of trade execution:
    1. Balance reservation
    2. Order submission
    3. Order status sync
    4. Position creation/update on fill
    5. Balance refresh (G4 protection)
    6. Exit execution with fill confirmation

    Usage:
        service = ExecutionService(db, clob_client, config)
        await service.load_state()  # Load positions on startup

        # Execute entry
        result = await service.execute_entry(signal, context)
        if result.success:
            print(f"Order {result.order_id} submitted")

        # Execute exit
        result = await service.execute_exit(signal, position)
        if result.success:
            print(f"Position closed")

        # Background sync
        await service.sync_open_orders()
    """

    def __init__(
        self,
        db: "Database",
        clob_client: Optional[Any] = None,
        config: Optional[ExecutionConfig] = None,
    ) -> None:
        """
        Initialize the execution service.

        Args:
            db: Database connection
            clob_client: Polymarket CLOB client (None for dry run)
            config: Execution configuration
        """
        self._db = db
        self._clob_client = clob_client
        self._config = config or ExecutionConfig()

        # Initialize managers
        self._balance_manager = BalanceManager(
            db=db,
            clob_client=clob_client,
            config=self._config.balance_config,
        )
        self._order_manager = OrderManager(
            db=db,
            clob_client=clob_client,
            config=self._config.order_config,
            balance_manager=self._balance_manager,
        )
        self._position_tracker = PositionTracker(db=db)
        self._exit_manager = ExitManager(
            db=db,
            clob_client=clob_client,
            position_tracker=self._position_tracker,
            balance_manager=self._balance_manager,
            config=self._config.exit_config,
        )

    @property
    def position_tracker(self) -> PositionTracker:
        """Access to position tracker for queries."""
        return self._position_tracker

    @property
    def balance_manager(self) -> BalanceManager:
        """Access to balance manager for queries."""
        return self._balance_manager

    @property
    def order_manager(self) -> OrderManager:
        """Access to order manager for queries."""
        return self._order_manager

    async def load_state(self) -> None:
        """
        Load state from database on startup.

        Should be called during initialization to restore:
        - Open positions
        - Open orders (with balance reservations)
        - Balance cache
        """
        # Refresh balance from CLOB first (before loading orders that reserve balance)
        self._balance_manager.refresh_balance()

        # Load open orders and restore reservations
        orders_loaded = await self._order_manager.load_orders()

        # Load open positions
        await self._position_tracker.load_positions()

        open_positions = len(self._position_tracker.get_open_positions())
        open_orders = len(self._order_manager.get_open_orders())
        logger.info(
            f"Loaded state: {open_positions} positions, {open_orders} orders"
        )

    async def execute_entry(
        self,
        signal: "EntrySignal",
        context: "StrategyContext",
    ) -> ExecutionResult:
        """
        Execute an entry signal.

        Handles:
        1. Price validation
        2. Balance check/reservation
        3. Order submission
        4. Order sync (optional wait for fill)
        5. Position creation
        6. Balance refresh (G4)

        Args:
            signal: Entry signal from strategy
            context: Strategy context with market data

        Returns:
            ExecutionResult with order_id and position_id on success
        """
        try:
            # Submit order (includes price and balance validation)
            order_id = await self._order_manager.submit_order(
                token_id=signal.token_id,
                side=signal.side,
                price=signal.price,
                size=signal.size,
                condition_id=context.condition_id,
            )

            logger.info(f"Submitted order {order_id} for {signal.token_id}")

            # Sync order status
            order = await self._order_manager.sync_order_status(order_id)

            # Create position if filled
            position_id = None
            if order and order.status == OrderStatus.FILLED:
                position = await self._position_tracker.record_fill(order)
                if position:
                    position_id = position.position_id
                    logger.info(f"Created position {position_id} from order {order_id}")

            return ExecutionResult(
                success=True,
                order_id=order_id,
                position_id=position_id,
            )

        except PriceTooHighError as e:
            logger.warning(f"Price too high: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type="price_too_high",
            )

        except InsufficientBalanceError as e:
            logger.warning(f"Insufficient balance: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type="insufficient_balance",
            )

        except PreSubmitValidationError as e:
            # Other pre-submit validation errors
            logger.warning(f"Pre-submit validation failed: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type="validation_error",
            )

        except Exception as e:
            logger.error(f"Execution error: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type="execution_error",
            )

    async def execute_exit(
        self,
        signal: "ExitSignal",
        position: Position,
        current_price: Optional[Decimal] = None,
    ) -> ExecutionResult:
        """
        Execute an exit signal.

        Handles:
        1. Exit order submission
        2. Fill confirmation (wait for fill)
        3. Position closure
        4. Balance refresh (G4)

        Args:
            signal: Exit signal from strategy
            position: Position to close
            current_price: Current market price for exit

        Returns:
            ExecutionResult indicating success/failure
        """
        try:
            exit_price = current_price or position.entry_price  # Fallback

            success = await self._exit_manager.execute_exit(
                position=position,
                current_price=exit_price,
                reason=signal.reason,
                wait_for_fill=self._config.wait_for_fill,
                fill_timeout_seconds=self._config.fill_timeout_seconds,
            )

            if success:
                logger.info(f"Exited position {position.position_id}: {signal.reason}")
                return ExecutionResult(
                    success=True,
                    position_id=position.position_id,
                )
            else:
                return ExecutionResult(
                    success=False,
                    position_id=position.position_id,
                    error="Exit order not confirmed",
                    error_type="fill_timeout",
                )

        except Exception as e:
            logger.error(f"Exit error for {position.position_id}: {e}")
            return ExecutionResult(
                success=False,
                position_id=position.position_id,
                error=str(e),
                error_type="exit_error",
            )

    async def sync_open_orders(self) -> int:
        """
        Sync status of all open orders with CLOB.

        Should be called periodically to detect fills.
        Handles both full fills (FILLED) and partial fills (PARTIAL).

        Returns:
            Number of orders synced
        """
        open_orders = self._order_manager.get_open_orders()
        synced_count = 0

        for order in open_orders:
            try:
                # Get old filled size to detect new fills
                old_filled = order.filled_size

                updated = await self._order_manager.sync_order_status(order.order_id)
                synced_count += 1

                if updated:
                    # Check for any new fills (partial or full)
                    new_filled = updated.filled_size - old_filled
                    if new_filled > Decimal("0"):
                        # Record ONLY the delta fill, not total filled_size
                        # Create a copy with filled_size set to the delta to avoid double-counting
                        await self._position_tracker.record_fill_delta(
                            order=updated,
                            delta_size=new_filled,
                        )
                        logger.info(
                            f"Order {order.order_id} fill detected: "
                            f"+{new_filled} (total: {updated.filled_size}/{updated.size})"
                        )

                    # Reservation adjustments are handled in OrderManager.sync_order_status

            except Exception as e:
                logger.error(f"Error syncing order {order.order_id}: {e}")

        return synced_count

    async def evaluate_exits(
        self,
        current_prices: dict[str, Decimal],
    ) -> List[tuple[Position, str]]:
        """
        Evaluate all positions for exit conditions.

        Args:
            current_prices: Dict of token_id -> current_price

        Returns:
            List of (position, reason) tuples that should be exited
        """
        exits_to_execute = []

        for position in self._position_tracker.get_open_positions():
            current_price = current_prices.get(position.token_id)
            if current_price is None:
                continue

            should_exit, reason = self._exit_manager.evaluate_exit(
                position=position,
                current_price=current_price,
            )

            if should_exit:
                exits_to_execute.append((position, reason))

        return exits_to_execute

    async def handle_resolution(
        self,
        token_id: str,
        resolved_price: Decimal,
    ) -> Optional[ExitEvent]:
        """
        Handle market resolution for a token.

        Args:
            token_id: Token that resolved
            resolved_price: Resolution price (1.0 for Yes, 0.0 for No)

        Returns:
            Exit event if position was closed
        """
        return await self._exit_manager.handle_resolution(
            token_id=token_id,
            resolved_price=resolved_price,
        )

    def get_available_balance(self) -> Decimal:
        """Get available balance for trading."""
        return self._balance_manager.get_available_balance()

    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return self._position_tracker.get_open_positions()

    def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        return self._order_manager.get_open_orders()

    def get_position_by_token(self, token_id: str) -> Optional[Position]:
        """Get position for a token."""
        return self._position_tracker.get_position_by_token(token_id)
