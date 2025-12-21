"""
Exit Manager for exit strategy execution.

Manages when to exit positions based on:
- Hold duration (short vs long positions)
- Profit targets
- Stop losses
- Market resolution

Exit Strategy Logic:
    - Short positions (<7 days): Hold to resolution (99%+ win rate)
    - Long positions (>7 days): Apply profit target (99c) and stop-loss (90c)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, Tuple

from .balance_manager import BalanceManager
from .position_tracker import Position, PositionTracker

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


@dataclass
class ExitConfig:
    """Configuration for exit strategies."""

    profit_target: Decimal = Decimal("0.99")  # Exit at 99c
    stop_loss: Decimal = Decimal("0.90")  # Exit at 90c
    min_hold_days: int = 7  # Minimum days before conditional exit applies


class ExitManager:
    """
    Manages exit strategy evaluation and execution.

    Exit strategies:
    - "hold_to_resolution": For short positions, hold until market resolves
    - "conditional_exit": For long positions, apply profit target and stop loss

    Usage:
        manager = ExitManager(db, clob_client)

        # Check if should exit
        should_exit, reason = manager.evaluate_exit(position, current_price)

        if should_exit:
            await manager.execute_exit(position, current_price, reason)
    """

    def __init__(
        self,
        db: "Database",
        clob_client: Optional[Any] = None,
        position_tracker: Optional[PositionTracker] = None,
        balance_manager: Optional[BalanceManager] = None,
        profit_target: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        min_hold_days: Optional[int] = None,
        config: Optional[ExitConfig] = None,
    ) -> None:
        """
        Initialize the exit manager.

        Args:
            db: Database connection
            clob_client: Polymarket CLOB client for order submission
            position_tracker: Position tracker for closing positions
            balance_manager: Balance manager for G4 protection (balance refresh)
            profit_target: Override for profit target price
            stop_loss: Override for stop loss price
            min_hold_days: Override for minimum hold days
            config: Full configuration (overridden by individual params)
        """
        self._db = db
        self._clob_client = clob_client
        self._position_tracker = position_tracker or PositionTracker(db)
        self._balance_manager = balance_manager or BalanceManager(db, clob_client)

        # Configuration
        self._config = config or ExitConfig()
        if profit_target is not None:
            self._config.profit_target = profit_target
        if stop_loss is not None:
            self._config.stop_loss = stop_loss
        if min_hold_days is not None:
            self._config.min_hold_days = min_hold_days

    def get_strategy_for_position(self, position: Position) -> str:
        """
        Determine which exit strategy applies to a position.

        Args:
            position: The position to evaluate

        Returns:
            "hold_to_resolution" for short positions
            "conditional_exit" for long positions
        """
        hold_duration = self._calculate_hold_duration(position)

        if hold_duration.days < self._config.min_hold_days:
            return "hold_to_resolution"
        else:
            return "conditional_exit"

    def evaluate_exit(
        self,
        position: Position,
        current_price: Decimal,
    ) -> Tuple[bool, str]:
        """
        Evaluate whether a position should be exited.

        Args:
            position: Position to evaluate
            current_price: Current market price

        Returns:
            (should_exit, reason) tuple
        """
        strategy = self.get_strategy_for_position(position)

        if strategy == "hold_to_resolution":
            # Short positions hold until resolution
            return False, ""

        # Conditional exit for long positions
        return self._evaluate_conditional_exit(position, current_price)

    def _evaluate_conditional_exit(
        self,
        position: Position,
        current_price: Decimal,
    ) -> Tuple[bool, str]:
        """
        Evaluate conditional exit (profit target / stop loss).

        Args:
            position: Position to evaluate
            current_price: Current market price

        Returns:
            (should_exit, reason) tuple
        """
        # Check profit target
        if current_price >= self._config.profit_target:
            return True, "profit_target"

        # Check stop loss
        if current_price <= self._config.stop_loss:
            return True, "stop_loss"

        # Hold between target and stop
        return False, ""

    async def execute_exit(
        self,
        position: Position,
        current_price: Decimal,
        reason: str,
        wait_for_fill: bool = True,
        fill_timeout_seconds: float = 30.0,
    ) -> bool:
        """
        Execute an exit for a position.

        FIX: Now waits for order acceptance/fill before closing position.
        This prevents desync between order state and position state.

        G4 Protection: Refreshes balance after exit to ensure accurate
        available balance for subsequent trades.

        Args:
            position: Position to exit
            current_price: Current price for the exit
            reason: Reason for exiting
            wait_for_fill: Whether to wait for fill confirmation (default: True)
            fill_timeout_seconds: How long to wait for fill (default: 30s)

        Returns:
            True if exit was executed successfully
        """
        import asyncio

        order_id = None

        try:
            # Submit sell order if client available
            if self._clob_client:
                result = self._clob_client.create_order(
                    token_id=position.token_id,
                    side="SELL",
                    price=float(current_price),
                    size=float(position.size),
                )
                order_id = result.get("orderID") or result.get("order_id")

                # FIX: Wait for order fill (not just acceptance) before closing position
                if wait_for_fill and order_id:
                    order_confirmed = await self._wait_for_order_fill(
                        order_id,
                        timeout_seconds=fill_timeout_seconds,
                    )

                    if not order_confirmed:
                        logger.warning(
                            f"Exit order {order_id} for {position.position_id} "
                            f"not confirmed within {fill_timeout_seconds}s. "
                            f"Position NOT closed to avoid desync."
                        )
                        return False

            # Only close position after order confirmed (or no client)
            await self._position_tracker.close_position(
                position.position_id,
                exit_price=current_price,
                reason=reason,
            )

            # G4: Refresh balance after exit to get accurate available balance
            self._balance_manager.refresh_balance()

            logger.info(
                f"Executed exit for {position.position_id}: "
                f"price={current_price}, reason={reason}"
            )
            return True

        except asyncio.CancelledError:
            # FIX: Re-raise CancelledError to allow graceful shutdown
            logger.debug(f"Exit for {position.position_id} cancelled")
            raise

        except Exception as e:
            logger.error(
                f"Failed to execute exit for {position.position_id}: {e}. "
                f"Order ID: {order_id}"
            )
            return False

    async def _wait_for_order_fill(
        self,
        order_id: str,
        timeout_seconds: float = 30.0,
        poll_interval: float = 1.0,
    ) -> bool:
        """
        Wait for an order to be filled or reach a terminal state.

        FIX: Now requires actual FILL, not just LIVE status.
        LIVE means order is on the book but not filled - we must wait for fill
        before closing the position to avoid desync.

        Args:
            order_id: Order ID to monitor
            timeout_seconds: Maximum time to wait
            poll_interval: Time between status checks

        Returns:
            True if order filled, False if timeout or rejected
        """
        import asyncio

        if not self._clob_client:
            return True  # No client, assume success

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.warning(f"Order {order_id} fill timeout after {elapsed:.1f}s")
                return False

            try:
                # FIX: Use run_in_executor if client is sync, to avoid blocking event loop
                loop = asyncio.get_event_loop()
                if hasattr(self._clob_client, 'get_order_async'):
                    result = await self._clob_client.get_order_async(order_id)
                else:
                    # Wrap sync call to not block event loop
                    result = await loop.run_in_executor(
                        None, self._clob_client.get_order, order_id
                    )

                status = result.get("status", "").upper()
                filled_size = float(result.get("filledSize", 0))
                size = float(result.get("size", 0))

                # Order filled or fully matched
                if status == "MATCHED" or (size > 0 and filled_size >= size):
                    logger.debug(f"Order {order_id} filled")
                    return True

                # FIX: LIVE means order is on book but NOT filled
                # We should continue polling until filled, not return True
                if status == "LIVE":
                    # Check if partially filled - if fully filled, we're done
                    if size > 0 and filled_size >= size:
                        logger.debug(f"Order {order_id} fully filled while live")
                        return True
                    # Otherwise, keep waiting for fill
                    logger.debug(f"Order {order_id} is live, waiting for fill...")
                    await asyncio.sleep(poll_interval)
                    continue

                # Terminal failure states
                if status in ("CANCELLED", "FAILED", "REJECTED", "EXPIRED"):
                    logger.warning(f"Order {order_id} terminal status: {status}")
                    return False

                # Still pending, wait and retry
                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                # FIX: Re-raise CancelledError to allow graceful shutdown
                logger.debug(f"Order {order_id} fill wait cancelled")
                raise

            except Exception as e:
                logger.warning(f"Error checking order {order_id} status: {e}")
                await asyncio.sleep(poll_interval)

    async def evaluate_all_positions(
        self,
        current_prices: dict[str, Decimal],
    ) -> list[Tuple[Position, str]]:
        """
        Evaluate all open positions for exit.

        Args:
            current_prices: Dict of token_id -> current_price

        Returns:
            List of (position, reason) tuples for positions that should exit
        """
        exits = []

        for position in self._position_tracker.get_open_positions():
            price = current_prices.get(position.token_id)
            if price is None:
                continue

            should_exit, reason = self.evaluate_exit(position, price)
            if should_exit:
                exits.append((position, reason))

        return exits

    async def process_exits(
        self,
        current_prices: dict[str, Decimal],
    ) -> int:
        """
        Evaluate and execute all pending exits.

        Args:
            current_prices: Dict of token_id -> current_price

        Returns:
            Number of exits executed
        """
        exits = await self.evaluate_all_positions(current_prices)
        executed = 0

        for position, reason in exits:
            price = current_prices.get(position.token_id)
            if price and await self.execute_exit(position, price, reason):
                executed += 1

        return executed

    def _calculate_hold_duration(self, position: Position) -> timedelta:
        """Calculate how long a position has been held."""
        now = datetime.now(timezone.utc)
        return now - position.entry_time

    async def handle_resolution(
        self,
        token_id: str,
        resolved_price: Decimal,
    ) -> bool:
        """
        Handle market resolution for a token.

        FIX: Now refreshes balance after resolution to account for
        settlement proceeds (G4 protection).

        Args:
            token_id: Token that resolved
            resolved_price: Resolution price (1.0 for Yes, 0.0 for No)

        Returns:
            True if position was closed
        """
        position = self._position_tracker.get_position_by_token(token_id)
        if not position:
            return False

        reason = "resolution_yes" if resolved_price >= Decimal("0.5") else "resolution_no"

        await self._position_tracker.close_position(
            position.position_id,
            exit_price=resolved_price,
            reason=reason,
        )

        # FIX: G4 protection - refresh balance after resolution settlement
        self._balance_manager.refresh_balance()

        logger.info(f"Position {position.position_id} resolved: {reason}")
        return True
