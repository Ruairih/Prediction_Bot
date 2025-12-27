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
from .position_sync import PositionSyncService
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

    # Wallet address for position sync (G12 fix)
    wallet_address: Optional[str] = None

    # Startup position sync configuration
    # When enabled, reconciles local positions with Polymarket on startup
    sync_positions_on_startup: bool = True
    startup_sync_hold_policy: str = "new"  # "new", "mature", or "actual"

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
        self._event_sink: Optional[Any] = None

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
        # G12 FIX: Position sync service for size updates before exits
        self._position_sync = PositionSyncService(
            db=db,
            position_tracker=self._position_tracker,
        )

    def set_event_sink(self, sink: Optional[Any]) -> None:
        """Register a callback for execution events."""
        self._event_sink = sink

    def _emit_event(self, event: dict) -> None:
        """Send an event to the registered sink if available."""
        if not self._event_sink:
            return
        try:
            self._event_sink(event)
        except Exception as exc:
            logger.debug(f"Event sink error: {exc}")

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
        - Open positions (reconciled with Polymarket if wallet_address configured)
        - Open orders (with balance reservations)
        - Balance cache
        """
        # Refresh balance from CLOB first (before loading orders that reserve balance)
        self._balance_manager.refresh_balance()

        # Load open orders and restore reservations
        orders_loaded = await self._order_manager.load_orders()

        # CRITICAL FIX: Reconcile with CLOB immediately
        if self._clob_client:
            open_orders = self._order_manager.get_open_orders()
            if open_orders:
                logger.info(f"Reconciling {len(open_orders)} open orders with CLOB")
            for order in open_orders:
                try:
                    await self._order_manager.sync_order_status(order.order_id)
                except Exception as e:
                    logger.warning(f"Could not sync order {order.order_id}: {e}")

        # Load open positions from database first
        await self._position_tracker.load_positions()

        # STARTUP POSITION SYNC: Reconcile local positions with Polymarket
        # This detects: externally closed positions, new external positions,
        # size changes from partial sells, and resolved markets while offline
        await self._startup_position_sync()

        open_positions = len(self._position_tracker.get_open_positions())
        open_orders = len(self._order_manager.get_open_orders())
        logger.info(
            f"Loaded state: {open_positions} positions, {open_orders} orders"
        )

    async def _startup_position_sync(self) -> None:
        """
        Reconcile local positions with Polymarket on startup.

        This is critical because while offline:
        - Markets may have resolved (positions closed)
        - User may have manually sold positions
        - User may have created positions externally
        - Partial sells may have changed position sizes

        Without this sync, the bot would:
        - Try to exit positions that no longer exist (CLOB rejects)
        - Miss managing externally created positions
        - Use wrong position sizes for exits
        - Keep "ghost" positions from resolved markets

        Errors are handled gracefully - if Polymarket API is down,
        we log a warning and continue with database state.
        """
        wallet_address = self._config.wallet_address

        # Skip if not configured
        if not wallet_address:
            logger.debug("Startup position sync skipped: no wallet_address configured")
            return

        if not self._config.sync_positions_on_startup:
            logger.debug("Startup position sync disabled by config")
            return

        logger.info(f"Startup position sync: reconciling with Polymarket...")

        try:
            result = await self._position_sync.sync_positions(
                wallet_address=wallet_address,
                dry_run=False,
                hold_policy=self._config.startup_sync_hold_policy,
            )

            # Log results
            imported = result.positions_imported
            updated = result.positions_updated
            closed = result.positions_closed

            if imported > 0 or updated > 0 or closed > 0:
                logger.info(
                    f"Startup position sync complete: "
                    f"{imported} imported, {updated} updated, {closed} closed"
                )
            else:
                logger.info("Startup position sync: positions already in sync")

            # Log any partial failures (DB errors, etc.)
            if result.errors:
                for error in result.errors:
                    logger.warning(f"Startup position sync partial error: {error}")

            # Reload positions after sync to get updated state
            if imported > 0 or updated > 0 or closed > 0:
                await self._position_tracker.load_positions()

        except Exception as e:
            # Don't block startup on sync failure - log warning and continue
            # The bot can still operate with stale data, and background sync
            # will eventually reconcile
            logger.warning(
                f"Startup position sync failed (continuing with DB state): {e}"
            )
            logger.warning(
                "Positions may be out of sync with Polymarket. "
                "Run manual sync or wait for background reconciliation."
            )

    async def sync_position_sizes(self) -> int:
        """
        Sync position sizes from Polymarket API.

        G12 FIX: Call this before exit evaluation to ensure position sizes
        are accurate. Prevents "not enough balance / allowance" errors when
        positions were partially sold externally.

        Returns:
            Number of positions updated
        """
        wallet_address = self._config.wallet_address
        if not wallet_address:
            logger.info("sync_position_sizes: no wallet_address configured, skipping")
            return 0

        logger.info(f"sync_position_sizes: syncing for {wallet_address[:10]}...")
        result = await self._position_sync.quick_sync_sizes(wallet_address)
        return result.get("updated", 0)

    def update_config(
        self,
        *,
        max_price: Optional[Decimal] = None,
        default_position_size: Optional[Decimal] = None,
        min_balance_reserve: Optional[Decimal] = None,
        profit_target: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        min_hold_days: Optional[int] = None,
    ) -> None:
        """Update execution configuration in place."""
        if max_price is not None:
            self._config.max_price = max_price
            self._order_manager.config.max_price = max_price
        if default_position_size is not None:
            self._config.default_position_size = default_position_size
            self._order_manager.config.position_size = default_position_size
        if min_balance_reserve is not None:
            self._config.min_balance_reserve = min_balance_reserve
            self._order_manager.config.min_balance_reserve = min_balance_reserve
            self._balance_manager._config.min_reserve = min_balance_reserve
        if profit_target is not None:
            self._config.profit_target = profit_target
            self._exit_manager._config.profit_target = profit_target
        if stop_loss is not None:
            self._config.stop_loss = stop_loss
            self._exit_manager._config.stop_loss = stop_loss
        if min_hold_days is not None:
            self._config.min_hold_days = min_hold_days
            self._exit_manager._config.min_hold_days = min_hold_days

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
                    self._emit_event({
                        "type": "position",
                        "action": "opened",
                        "position_id": position.position_id,
                        "token_id": position.token_id,
                        "condition_id": position.condition_id,
                        "size": str(position.size),
                        "entry_price": str(position.entry_price),
                    })

            self._emit_event({
                "type": "order",
                "action": "submitted",
                "order_id": order_id,
                "token_id": signal.token_id,
                "condition_id": context.condition_id,
                "side": signal.side,
                "price": str(signal.price),
                "size": str(signal.size),
                "status": order.status.value if order else "pending",
                "position_id": position_id,
            })

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
        wait_for_fill: Optional[bool] = None,
    ) -> ExecutionResult:
        """
        Execute an exit signal.

        Handles:
        1. Exit order submission
        2. Fill confirmation (wait for fill, if enabled)
        3. Position closure
        4. Balance refresh (G4)

        Args:
            signal: Exit signal from strategy
            position: Position to close
            current_price: Current market price for exit
            wait_for_fill: Whether to wait for fill. None uses config default.

        Returns:
            ExecutionResult indicating success/failure
        """
        try:
            exit_price = current_price or position.entry_price  # Fallback

            # Use explicit wait_for_fill if provided, otherwise use config
            should_wait = wait_for_fill if wait_for_fill is not None else self._config.wait_for_fill

            success, order_id = await self._exit_manager.execute_exit(
                position=position,
                current_price=exit_price,
                reason=signal.reason,
                wait_for_fill=should_wait,
                fill_timeout_seconds=self._config.fill_timeout_seconds,
            )

            if success:
                # Different messaging for wait vs no-wait
                if should_wait:
                    logger.info(f"Exited position {position.position_id}: {signal.reason}")
                    self._emit_event({
                        "type": "position",
                        "action": "closed",
                        "position_id": position.position_id,
                        "token_id": position.token_id,
                        "condition_id": position.condition_id,
                        "reason": signal.reason,
                    })
                else:
                    logger.info(
                        f"Exit order {order_id} submitted for {position.position_id}: {signal.reason}"
                    )
                    self._emit_event({
                        "type": "position",
                        "action": "exit_submitted",
                        "position_id": position.position_id,
                        "token_id": position.token_id,
                        "condition_id": position.condition_id,
                        "order_id": order_id,
                        "reason": signal.reason,
                    })
                return ExecutionResult(
                    success=True,
                    position_id=position.position_id,
                    order_id=order_id,
                )
            else:
                return ExecutionResult(
                    success=False,
                    position_id=position.position_id,
                    order_id=order_id,
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

    async def close_position(
        self,
        position_id: str,
        reason: str = "manual_close",
        current_price: Optional[Decimal] = None,
        wait_for_fill: Optional[bool] = None,
    ) -> ExecutionResult:
        """
        Manually close a single position.

        Args:
            position_id: Position to close
            reason: Reason for closing
            current_price: Price to use for exit order
            wait_for_fill: Whether to wait for fill confirmation.
                          If None, uses config default.
                          For dashboard calls, pass False for quick response.

        Returns:
            ExecutionResult with success/error info and order_id if submitted
        """
        position = self._position_tracker.get_position(position_id)
        if not position:
            return ExecutionResult(
                success=False,
                position_id=position_id,
                error="Position not found",
                error_type="not_found",
            )

        from polymarket_bot.strategies import ExitSignal

        exit_signal = ExitSignal(position_id=position_id, reason=reason)
        price = current_price or position.entry_price
        return await self.execute_exit(
            exit_signal,
            position,
            current_price=price,
            wait_for_fill=wait_for_fill,
        )

    async def flatten_positions(self, reason: str = "manual_flatten") -> int:
        """Close all open positions."""
        positions = list(self._position_tracker.get_open_positions())
        closed_count = 0
        for position in positions:
            result = await self.close_position(position.position_id, reason=reason)
            if result.success:
                closed_count += 1
        return closed_count

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a single open order."""
        success = await self._order_manager.cancel_order(order_id)
        if success:
            self._emit_event({
                "type": "order",
                "action": "cancelled",
                "order_id": order_id,
            })
        return success

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders."""
        open_orders = list(self._order_manager.get_open_orders())
        cancelled = 0
        for order in open_orders:
            if await self.cancel_order(order.order_id):
                cancelled += 1
        return cancelled

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
                        self._emit_event({
                            "type": "fill",
                            "action": updated.status.value if updated.status else "partial",
                            "order_id": updated.order_id,
                            "token_id": updated.token_id,
                            "condition_id": updated.condition_id,
                            "delta_size": str(new_filled),
                            "filled_size": str(updated.filled_size),
                            "size": str(updated.size),
                            "avg_fill_price": str(updated.avg_fill_price) if updated.avg_fill_price else None,
                        })

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
            if self._exit_manager._has_pending_exit(position):
                pending_status = await self._exit_manager.reconcile_pending_exit(
                    position,
                    current_price=current_price,
                    reason=None,
                    stale_after_seconds=self._config.fill_timeout_seconds,
                )
                if pending_status in ("pending", "closed"):
                    continue

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
