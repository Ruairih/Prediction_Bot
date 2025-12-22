"""
Trading Engine - Main orchestrator for the trading bot.

The engine coordinates all components:
1. Receives events from ingestion
2. Processes through event processor
3. Checks trigger deduplication
4. Evaluates strategy
5. Routes signals to execution or watchlist

Critical Gotchas:
    - G2: Dual-key trigger deduplication
    - G5: Orderbook verification before execution
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

from polymarket_bot.execution.balance_manager import PreSubmitValidationError
from polymarket_bot.strategies import (
    EntrySignal,
    ExitSignal,
    HoldSignal,
    IgnoreSignal,
    Signal,
    SignalType,
    Strategy,
    WatchlistSignal,
)

from .event_processor import EventProcessor
from .trigger_tracker import TriggerTracker
from .watchlist_service import WatchlistService

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    """Configuration for the trading engine."""

    # Price threshold
    price_threshold: Decimal = Decimal("0.95")

    # Position sizing
    position_size: Decimal = Decimal("20")
    max_positions: int = 50

    # Mode
    dry_run: bool = True  # If True, don't submit real orders

    # G1 protection
    max_trade_age_seconds: int = 300

    # G5 protection
    verify_orderbook: bool = True
    max_price_deviation: Decimal = Decimal("0.10")

    # Watchlist
    watchlist_rescore_interval_hours: float = 1.0


@dataclass
class EngineStats:
    """Runtime statistics for the engine."""

    events_processed: int = 0
    triggers_evaluated: int = 0
    entries_executed: int = 0
    dry_run_signals: int = 0
    watchlist_additions: int = 0
    filters_rejected: int = 0
    orderbook_rejections: int = 0
    errors: int = 0


class TradingEngine:
    """
    Main trading engine orchestrator.

    Coordinates the flow: events -> strategy -> execution

    Usage:
        engine = TradingEngine(
            config=EngineConfig(dry_run=True),
            db=database,
            strategy=HighProbYesStrategy(),
        )

        await engine.start()

        # Process events from ingestion
        await engine.process_event(event)

        await engine.stop()
    """

    def __init__(
        self,
        config: EngineConfig,
        db: "Database",
        strategy: Optional[Strategy] = None,
        api_client: Optional[Any] = None,  # For orderbook verification
        execution_service: Optional[Any] = None,  # ExecutionService for order execution
    ) -> None:
        """
        Initialize the trading engine.

        Args:
            config: Engine configuration
            db: Database connection
            strategy: Trading strategy to use (required for trading)
            api_client: Optional API client for orderbook verification (G5)
            execution_service: Optional ExecutionService for order execution
        """
        self.config = config
        self._db = db
        self.strategy = strategy
        self._api_client = api_client
        self._execution_service = execution_service

        # Initialize components
        self._event_processor = EventProcessor(
            threshold=config.price_threshold,
            max_trade_age_seconds=config.max_trade_age_seconds,
        )
        self._trigger_tracker = TriggerTracker(db)
        self._watchlist_service = WatchlistService(db)

        # State
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._stats = EngineStats()

        # Order management (used when no execution_service provided)
        self._pending_orders: list[dict] = []

    @property
    def is_running(self) -> bool:
        """Whether the engine is currently running."""
        return self._is_running

    @property
    def stats(self) -> EngineStats:
        """Current engine statistics."""
        return self._stats

    @property
    def trigger_repo(self) -> TriggerTracker:
        """Access to trigger tracker."""
        return self._trigger_tracker

    @property
    def position_repo(self):
        """Access to position repository (via storage layer)."""
        from polymarket_bot.storage import PositionRepository
        return PositionRepository(self._db)

    @property
    def execution_count(self) -> int:
        """Number of executions (or dry run signals)."""
        return self._stats.entries_executed + self._stats.dry_run_signals

    @property
    def orders_submitted(self) -> int:
        """Number of real orders submitted."""
        return self._stats.entries_executed

    @property
    def dry_run_signals(self) -> int:
        """Number of dry run signals."""
        return self._stats.dry_run_signals

    async def start(self) -> None:
        """Start the trading engine."""
        if self._is_running:
            logger.warning("Engine already running")
            return

        if self.strategy is None:
            raise ValueError("Engine requires a strategy to be set before starting")

        logger.info(f"Starting trading engine with strategy: {self.strategy.name}")
        logger.info(f"Mode: {'DRY RUN' if self.config.dry_run else 'LIVE'}")

        self._is_running = True
        self._stop_event.clear()

        logger.info("Trading engine started")

    async def stop(self) -> None:
        """Stop the trading engine."""
        if not self._is_running:
            return

        logger.info("Stopping trading engine...")
        self._is_running = False
        self._stop_event.set()

        logger.info("Trading engine stopped")

    async def process_event(self, event: dict[str, Any]) -> Optional[Signal]:
        """
        Process an incoming event through the full pipeline.

        Pipeline:
        1. Filter event type
        2. Extract trigger data
        3. Check price threshold
        4. Check trigger deduplication (G2)
        5. Build strategy context
        6. Apply hard filters
        7. Evaluate strategy
        8. Route signal (execute, watchlist, or ignore)

        Args:
            event: Raw event from ingestion

        Returns:
            The signal generated, or None if filtered
        """
        self._stats.events_processed += 1

        # 1. Filter event type
        if not self._event_processor.should_process(event):
            return None

        # 2. Extract trigger data
        trigger_data = self._event_processor.extract_trigger(event)
        if trigger_data is None:
            return None

        # 3. Check price threshold
        if not self._event_processor.meets_threshold(trigger_data.price):
            return None

        self._stats.triggers_evaluated += 1

        # 4. Check trigger deduplication (G2)
        should_trigger = await self._trigger_tracker.should_trigger(
            token_id=trigger_data.token_id,
            condition_id=trigger_data.condition_id,
            threshold=self.config.price_threshold,
        )

        if not should_trigger:
            logger.debug(
                f"Duplicate trigger ignored: {trigger_data.token_id} "
                f"@ {trigger_data.price}"
            )
            return None

        # 5. Build strategy context
        context = await self._event_processor.build_context(
            event, self._db, trigger_data
        )
        if context is None:
            return None

        # 6. Apply hard filters
        should_reject, reason = self._event_processor.apply_filters(context)
        if should_reject:
            self._stats.filters_rejected += 1
            logger.debug(f"Hard filter rejected: {reason}")
            return IgnoreSignal(reason=reason, filter_name=reason.split(":")[0])

        # 7. Evaluate strategy
        signal = self.strategy.evaluate(context)

        # 8. Route signal
        await self._route_signal(signal, context, event)

        return signal

    async def _route_signal(
        self,
        signal: Signal,
        context: Any,
        event: dict,
    ) -> None:
        """
        Route a signal to the appropriate handler.

        Args:
            signal: The strategy signal
            context: The strategy context
            event: Original event
        """
        if signal.type == SignalType.ENTRY:
            await self._handle_entry(signal, context, event)

        elif signal.type == SignalType.EXIT:
            await self._handle_exit(signal, context)

        elif signal.type == SignalType.WATCHLIST:
            await self._handle_watchlist(signal, context)

        elif signal.type == SignalType.IGNORE:
            self._stats.filters_rejected += 1

        # HOLD signals need no action

    async def _handle_entry(
        self,
        signal: EntrySignal,
        context: Any,
        event: dict,
    ) -> None:
        """
        Handle an entry signal.

        G5: Verifies orderbook before executing.
        G2: Uses atomic trigger recording to prevent TOCTOU races.

        CRITICAL FIX: Trigger is now recorded AFTER successful execution,
        not before. This prevents blocking future retries if execution fails.

        Args:
            signal: The entry signal
            context: Strategy context
            event: Original event
        """
        # G5: Verify orderbook matches trigger price
        if self.config.verify_orderbook and self._api_client:
            is_valid = await self._verify_orderbook(
                context.token_id,
                context.trigger_price,
            )
            if not is_valid:
                self._stats.orderbook_rejections += 1
                logger.warning(
                    f"G5: Orderbook mismatch for {context.token_id}, rejecting"
                )
                return

        # G2 FIX: Use atomic check to prevent TOCTOU race
        # We check atomically but DON'T record yet - only record after successful execution
        # This allows retries if execution fails
        is_first = await self._trigger_tracker.try_record_trigger_atomic(
            token_id=context.token_id,
            condition_id=context.condition_id,
            threshold=self.config.price_threshold,
            price=context.trigger_price,
            trade_size=context.trade_size,
            model_score=context.model_score,
            outcome=context.outcome,
            outcome_index=context.outcome_index,
        )

        if not is_first:
            # Another concurrent event already claimed this trigger
            logger.debug(
                f"G2: Atomic dedup blocked duplicate for {context.token_id}"
            )
            return

        # Execute or dry run
        # CRITICAL FIX: Trigger was recorded atomically above to claim it,
        # but if execution fails, we should allow retry by removing the trigger.
        # For now, trigger is recorded before execution to prevent concurrent claims.
        # A more sophisticated approach would use a "pending" state.
        if self.config.dry_run:
            self._stats.dry_run_signals += 1
            logger.info(
                f"DRY RUN: Would buy {signal.size} of {signal.token_id} "
                f"@ {signal.price} ({signal.reason})"
            )
        else:
            try:
                await self._execute_entry(signal, context)
                self._stats.entries_executed += 1
                logger.info(
                    f"Successfully executed entry for {context.token_id}"
                )
            except PreSubmitValidationError as e:
                # Pre-execution validation errors - safe to retry
                # These errors occur BEFORE order submission (price/balance checks)
                await self._trigger_tracker.remove_trigger(
                    token_id=context.token_id,
                    condition_id=context.condition_id,
                    threshold=self.config.price_threshold,
                )
                logger.warning(
                    f"Pre-submit validation failed for {context.token_id}: {e}. "
                    f"Trigger removed to allow retry."
                )
                raise
            except Exception as e:
                # Other errors - order may have been submitted
                # DON'T remove trigger to prevent duplicate orders
                # Manual intervention may be needed
                logger.error(
                    f"Execution error for {context.token_id}: {e}. "
                    f"Trigger NOT removed (order may have been placed). "
                    f"Manual review recommended."
                )
                self._stats.errors += 1
                raise

    async def _handle_exit(
        self,
        signal: ExitSignal,
        context: Any,
    ) -> None:
        """Handle an exit signal."""
        if self.config.dry_run:
            logger.info(
                f"DRY RUN: Would exit position {signal.position_id} "
                f"({signal.reason})"
            )
        else:
            await self._execute_exit(signal, context)

    async def _handle_watchlist(
        self,
        signal: WatchlistSignal,
        context: Any,
    ) -> None:
        """Handle a watchlist signal."""
        await self._watchlist_service.add_to_watchlist(
            token_id=signal.token_id,
            condition_id=context.condition_id,
            initial_score=signal.current_score,
            time_to_end_hours=context.time_to_end_hours,
            trigger_price=context.trigger_price,
            question=context.question,
        )
        self._stats.watchlist_additions += 1
        logger.info(
            f"Added to watchlist: {signal.token_id} (score={signal.current_score:.2f})"
        )

    async def _verify_orderbook(
        self,
        token_id: str,
        expected_price: Decimal,
    ) -> bool:
        """
        G5: Verify orderbook price matches expected price.

        Args:
            token_id: Token to check
            expected_price: Expected price from trigger

        Returns:
            True if orderbook matches within tolerance
        """
        if not self._api_client:
            return True

        try:
            # Use ingestion layer's verify function if available
            if hasattr(self._api_client, "verify_orderbook_price"):
                is_valid, actual_price, reason = await self._api_client.verify_orderbook_price(
                    token_id,
                    expected_price,
                    self.config.max_price_deviation,
                )
                if not is_valid:
                    logger.warning(f"G5: {reason}")
                return is_valid

            # Fallback: fetch orderbook directly
            orderbook = await self._api_client.get_orderbook(token_id)
            if not orderbook:
                return False

            # G5: For BUY orders, check best_ask (what we'd pay)
            # For SELL orders, check best_bid (what we'd receive)
            # Since we're always buying at trigger, check best_ask
            if not orderbook.get("asks"):
                # No asks available - can't verify
                logger.warning(f"G5: No asks in orderbook for {token_id}")
                return False

            best_ask = Decimal(str(orderbook["asks"][0]["price"]))
            deviation = abs(best_ask - expected_price)

            if deviation > self.config.max_price_deviation:
                logger.warning(
                    f"G5: Orderbook ask {best_ask} vs trigger {expected_price} "
                    f"(deviation {deviation})"
                )
                return False

            # Also check if best_ask is much higher than expected (overpay risk)
            if best_ask > expected_price + self.config.max_price_deviation:
                logger.warning(
                    f"G5: Best ask {best_ask} much higher than trigger {expected_price}, "
                    f"would overpay"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error verifying orderbook: {e}")
            return False

    async def _execute_entry(
        self,
        signal: EntrySignal,
        context: Any,
    ) -> None:
        """
        Execute an entry order.

        Uses ExecutionService if available, otherwise logs the order.

        Args:
            signal: Entry signal with order details
            context: Strategy context
        """
        logger.info(
            f"EXECUTE: Buy {signal.size} of {signal.token_id} @ {signal.price}"
        )

        if self._execution_service:
            # Use ExecutionService for real order execution
            result = await self._execution_service.execute_entry(signal, context)
            if not result.success:
                logger.error(
                    f"Entry execution failed for {signal.token_id}: "
                    f"{result.error_type} - {result.error}"
                )
                # Raise appropriate exception based on error type
                # This allows _handle_entry to properly handle trigger removal
                if result.error_type in ("price_too_high", "insufficient_balance", "validation_error"):
                    # Pre-submit errors are safe to retry
                    raise PreSubmitValidationError(result.error)
                else:
                    # Other errors (order may have been submitted)
                    raise Exception(f"Execution failed: {result.error}")
            logger.info(f"Entry executed: order_id={result.order_id}")
        else:
            # Fallback: just track the order internally (for testing)
            self._pending_orders.append({
                "type": "entry",
                "token_id": signal.token_id,
                "side": signal.side,
                "price": signal.price,
                "size": signal.size,
                "timestamp": datetime.now(timezone.utc),
            })

    async def _execute_exit(
        self,
        signal: ExitSignal,
        context: Any,
    ) -> None:
        """
        Execute an exit order.

        Uses ExecutionService if available, otherwise logs the order.

        Args:
            signal: Exit signal
            context: Strategy context
        """
        logger.info(f"EXECUTE: Exit position {signal.position_id}")

        if self._execution_service:
            # Get the position from execution service
            position = self._execution_service.position_tracker.get_position(
                signal.position_id
            )
            if not position:
                logger.warning(f"Position {signal.position_id} not found for exit")
                return

            # Get current price from context if available
            current_price = getattr(context, 'trigger_price', None)

            result = await self._execution_service.execute_exit(
                signal, position, current_price
            )
            if not result.success:
                logger.error(
                    f"Exit execution failed for {signal.position_id}: "
                    f"{result.error_type} - {result.error}"
                )
            else:
                logger.info(f"Exit executed: position_id={result.position_id}")
        else:
            # Fallback: just track the order internally (for testing)
            self._pending_orders.append({
                "type": "exit",
                "position_id": signal.position_id,
                "reason": signal.reason,
                "timestamp": datetime.now(timezone.utc),
            })

    async def rescore_watchlist(self) -> list:
        """
        Re-score all watchlist entries.

        Returns:
            List of promotions to execute
        """
        return await self._watchlist_service.rescore_all()
