"""
BackgroundTasksManager - Manages async background tasks.

Handles periodic tasks like:
- Watchlist rescoring
- Order status sync
- Exit evaluation
- Position monitoring
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional, List, Any

if TYPE_CHECKING:
    from polymarket_bot.core.engine import TradingEngine
    from polymarket_bot.execution import ExecutionService

logger = logging.getLogger(__name__)


@dataclass
class BackgroundTaskConfig:
    """Configuration for background tasks."""

    # Watchlist rescoring
    watchlist_rescore_interval_seconds: float = 3600  # 1 hour
    watchlist_enabled: bool = True

    # Order sync
    order_sync_interval_seconds: float = 30
    order_sync_enabled: bool = True

    # Exit evaluation
    exit_eval_interval_seconds: float = 60
    exit_eval_enabled: bool = True


class BackgroundTasksManager:
    """
    Manages background async tasks for the trading bot.

    Tasks run in the background and are automatically restarted
    on failure. The manager handles graceful shutdown.

    Usage:
        manager = BackgroundTasksManager(
            engine=trading_engine,
            execution_service=execution_service,
            config=BackgroundTaskConfig(),
        )
        await manager.start()
        # ... bot runs ...
        await manager.stop()
    """

    def __init__(
        self,
        engine: Optional["TradingEngine"] = None,
        execution_service: Optional["ExecutionService"] = None,
        config: Optional[BackgroundTaskConfig] = None,
        price_fetcher: Optional[Callable[[List[str]], Any]] = None,
    ) -> None:
        """
        Initialize the background tasks manager.

        Args:
            engine: TradingEngine for watchlist promotion
            execution_service: ExecutionService for order sync and exits
            config: Task configuration
            price_fetcher: Optional async callback to get prices for token_ids.
                           Should accept list of token_ids and return dict of {token_id: Decimal}
        """
        self._engine = engine
        self._execution_service = execution_service
        self._config = config or BackgroundTaskConfig()
        self._price_fetcher = price_fetcher

        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Whether the manager is running."""
        return self._running

    async def start(self) -> None:
        """Start all background tasks."""
        if self._running:
            logger.warning("BackgroundTasksManager already running")
            return

        logger.info("Starting background tasks...")
        self._running = True
        self._stop_event.clear()

        # Start enabled tasks
        if self._config.watchlist_enabled and self._engine:
            task = asyncio.create_task(
                self._watchlist_rescore_loop(),
                name="watchlist_rescore",
            )
            self._tasks.append(task)
            logger.info(
                f"Started watchlist rescore task "
                f"(interval={self._config.watchlist_rescore_interval_seconds}s)"
            )

        if self._config.order_sync_enabled and self._execution_service:
            task = asyncio.create_task(
                self._order_sync_loop(),
                name="order_sync",
            )
            self._tasks.append(task)
            logger.info(
                f"Started order sync task "
                f"(interval={self._config.order_sync_interval_seconds}s)"
            )

        if self._config.exit_eval_enabled and self._execution_service:
            task = asyncio.create_task(
                self._exit_evaluation_loop(),
                name="exit_eval",
            )
            self._tasks.append(task)
            logger.info(
                f"Started exit evaluation task "
                f"(interval={self._config.exit_eval_interval_seconds}s)"
            )

        logger.info(f"Background tasks started: {len(self._tasks)} tasks")

    async def stop(self) -> None:
        """Stop all background tasks gracefully."""
        if not self._running:
            return

        logger.info("Stopping background tasks...")
        self._running = False
        self._stop_event.set()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("Background tasks stopped")

    async def _watchlist_rescore_loop(self) -> None:
        """
        Periodically rescore watchlist entries.

        Entries that score above threshold are promoted to execution.
        """
        interval = self._config.watchlist_rescore_interval_seconds

        while self._running:
            try:
                # Wait for interval or stop
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval,
                    )
                    break  # Stop requested
                except asyncio.TimeoutError:
                    pass  # Continue with rescore

                if not self._running:
                    break

                # Perform rescore
                logger.debug("Running watchlist rescore...")
                promotions = await self._engine.rescore_watchlist()

                if promotions:
                    logger.info(f"Watchlist: {len(promotions)} entries promoted")

                    # Execute promotions
                    for promotion in promotions:
                        await self._execute_promotion(promotion)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in watchlist rescore: {e}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def _execute_promotion(self, promotion: Any) -> None:
        """Execute a promoted watchlist entry."""
        if not self._engine:
            return

        try:
            await self._engine.execute_watchlist_promotion(promotion)

        except Exception as e:
            logger.error(f"Error executing promotion: {e}")

    async def _order_sync_loop(self) -> None:
        """
        Periodically sync order status with CLOB.

        Detects fills and updates positions.
        """
        interval = self._config.order_sync_interval_seconds

        while self._running:
            try:
                # Wait for interval or stop
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval,
                    )
                    break  # Stop requested
                except asyncio.TimeoutError:
                    pass  # Continue with sync

                if not self._running:
                    break

                # Sync orders
                logger.debug("Syncing open orders...")
                synced = await self._execution_service.sync_open_orders()

                if synced > 0:
                    logger.info(f"Order sync: {synced} orders updated")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in order sync: {e}")
                await asyncio.sleep(5)

    async def _exit_evaluation_loop(self) -> None:
        """
        Periodically evaluate positions for exit conditions.

        Uses exit strategy logic (profit target, stop loss for long positions).
        """
        interval = self._config.exit_eval_interval_seconds

        while self._running:
            try:
                # Wait for interval or stop
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval,
                    )
                    break  # Stop requested
                except asyncio.TimeoutError:
                    pass  # Continue with evaluation

                if not self._running:
                    break

                # Get current prices for open positions
                if not self._price_fetcher:
                    # No price fetcher - skip this round
                    continue

                # Get token IDs from open positions
                open_positions = self._execution_service.get_open_positions()
                if not open_positions:
                    continue

                token_ids = [p.token_id for p in open_positions]

                # Fetch prices (may be async)
                try:
                    current_prices = await self._price_fetcher(token_ids)
                except Exception as e:
                    logger.error(f"Error fetching prices for exit evaluation: {e}")
                    continue

                # Evaluate exits
                logger.debug("Evaluating exit conditions...")
                exits = await self._execution_service.evaluate_exits(current_prices)

                if exits:
                    logger.info(f"Exit evaluation: {len(exits)} positions to exit")

                    for position, reason in exits:
                        try:
                            from polymarket_bot.strategies import ExitSignal

                            signal = ExitSignal(
                                reason=reason,
                                position_id=position.position_id,
                            )

                            current_price = current_prices.get(position.token_id)
                            result = await self._execution_service.execute_exit(
                                signal, position, current_price
                            )

                            if result.success:
                                logger.info(
                                    f"Exited position {position.position_id}: {reason}"
                                )
                            else:
                                logger.warning(
                                    f"Exit failed for {position.position_id}: "
                                    f"{result.error}"
                                )

                        except Exception as e:
                            logger.error(
                                f"Error executing exit for {position.position_id}: {e}"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in exit evaluation: {e}")
                await asyncio.sleep(5)
