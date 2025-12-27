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
            "hold_to_resolution" for short positions with KNOWN age
            "conditional_exit" for long positions OR unknown age positions

        CRITICAL FIX: Unknown age positions are ELIGIBLE for exit.

        The 7-day hold only applies to positions where we KNOW the age is
        accurate (bot_created or actual timestamps). If age_source is
        "unknown" (e.g., synced with hold_policy="new"), we default to
        conditional_exit to avoid blocking profitable exits forever.

        This prevents the recurring bug where synced positions at 99.8¢
        never exit because hold_start_at was set to NOW during sync.
        """
        # CRITICAL: Unknown age = eligible for exit (not blocked)
        # This is the permanent fix for the recurring hold_start_at bug
        if not position.has_known_age:
            logger.debug(
                f"Position {position.position_id} has unknown age "
                f"(age_source={position.age_source}), eligible for exit"
            )
            return "conditional_exit"

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
    ) -> tuple[bool, str | None]:
        """
        Execute an exit for a position.

        FIX: Now waits for order acceptance/fill before closing position.
        This prevents desync between order state and position state.

        G4 Protection: Refreshes balance after exit to ensure accurate
        available balance for subsequent trades.

        ATOMICITY FIX: Uses atomic database update to prevent duplicate
        exit orders from concurrent calls. The pending flag is set BEFORE
        order submission and uses a WHERE clause to ensure only one caller
        succeeds.

        Args:
            position: Position to exit
            current_price: Current price for the exit
            reason: Reason for exiting
            wait_for_fill: Whether to wait for fill confirmation (default: True)
                          If False, order is submitted but position is NOT closed.
                          Background sync should close when order fills.
            fill_timeout_seconds: How long to wait for fill (default: 30s)

        Returns:
            Tuple of (success, order_id). When wait_for_fill=False, success=True
            means order was submitted (not necessarily filled).
        """
        import asyncio

        order_id = None

        try:
            # Check for existing pending exit and try to reconcile
            if self._has_pending_exit(position):
                pending_status = await self.reconcile_pending_exit(
                    position,
                    current_price=current_price,
                    reason=reason,
                    stale_after_seconds=fill_timeout_seconds,
                )
                if pending_status == "pending":
                    logger.info(
                        f"Exit already pending for {position.position_id} "
                        f"(order_id={position.exit_order_id}); skipping new order"
                    )
                    return False, position.exit_order_id
                if pending_status == "closed":
                    return True, position.exit_order_id

            # ATOMICITY FIX: Atomically claim the exit slot BEFORE submitting order
            # This prevents race conditions where two concurrent calls both pass
            # the _has_pending_exit check and submit duplicate orders.
            claimed = await self._position_tracker.try_claim_exit_atomic(
                position.position_id
            )
            if not claimed:
                logger.info(
                    f"Exit already claimed by another process for {position.position_id}"
                )
                return False, None

            # Submit sell order if client available
            if self._clob_client:
                # py-clob-client requires OrderArgs object
                from py_clob_client.clob_types import OrderArgs

                order_args = OrderArgs(
                    token_id=position.token_id,
                    side="SELL",
                    price=float(current_price),
                    size=float(position.size),
                )

                result = self._clob_client.create_and_post_order(order_args)

                if isinstance(result, dict):
                    order_id = result.get("orderID") or result.get("order_id") or result.get("id")
                else:
                    order_id = str(result) if result else None

                if not order_id:
                    logger.warning(
                        f"Exit order for {position.position_id} returned no order_id. "
                        f"Position NOT closed to avoid desync."
                    )
                    # Clear the claimed state since order failed
                    await self._position_tracker.clear_exit_pending(
                        position.position_id,
                        exit_status="failed",
                    )
                    return False, None

                # Update pending state with actual order_id
                await self._position_tracker.mark_exit_pending(
                    position.position_id,
                    order_id,
                )

                # If not waiting for fill, return immediately after order submission
                # Background sync will close the position when order fills
                if not wait_for_fill:
                    logger.info(
                        f"Exit order {order_id} submitted for {position.position_id}; "
                        f"not waiting for fill (background sync will close position)"
                    )
                    return True, order_id

                # FIX: Wait for order fill (not just acceptance) before closing position
                if order_id:
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
                        await self._position_tracker.set_exit_status(
                            position.position_id,
                            "timeout",
                        )
                        return False, order_id

            # Only close position after order confirmed (or no client)
            await self._position_tracker.close_position(
                position.position_id,
                exit_price=current_price,
                reason=reason,
                exit_order_id=order_id,
            )

            # G4: Refresh balance after exit to get accurate available balance
            self._balance_manager.refresh_balance()

            logger.info(
                f"Executed exit for {position.position_id}: "
                f"price={current_price}, reason={reason}"
            )
            return True, order_id

        except asyncio.CancelledError:
            # FIX: Re-raise CancelledError to allow graceful shutdown
            # Only clear pending state if order wasn't submitted yet
            # If order_id is set, the order is live on CLOB - don't orphan it
            logger.debug(f"Exit for {position.position_id} cancelled, order_id={order_id}")
            if order_id is None:
                # No order submitted yet - safe to clear pending
                try:
                    await self._position_tracker.clear_exit_pending(
                        position.position_id,
                        exit_status="cancelled",
                    )
                except Exception:
                    pass  # Best effort cleanup on cancellation
            else:
                # Order is live - keep pending state so reconcile can handle it
                logger.warning(
                    f"Exit cancelled after order {order_id} submitted for {position.position_id}; "
                    f"keeping pending state for reconciliation"
                )
            raise

        except Exception as e:
            logger.error(
                f"Failed to execute exit for {position.position_id}: {e}. "
                f"Order ID: {order_id}"
            )
            # Clear pending state on unexpected failure to allow retry
            try:
                await self._position_tracker.clear_exit_pending(
                    position.position_id,
                    exit_status="failed",
                )
            except Exception as clear_err:
                logger.warning(f"Failed to clear exit pending: {clear_err}")
            return False, order_id

    async def reconcile_pending_exit(
        self,
        position: Position,
        current_price: Optional[Decimal] = None,
        reason: Optional[str] = None,
        *,
        stale_after_seconds: Optional[float] = None,
    ) -> str:
        """
        Reconcile a pending exit order for a position.

        Returns:
            "pending" if the exit order is still live,
            "closed" if the position was closed from a filled order,
            "cleared" if the pending state was cleared (terminal/cancelled),
            "none" if no pending exit exists.
        """
        if not self._has_pending_exit(position):
            return "none"

        if not position.exit_order_id:
            # ATOMICITY FIX: "claiming" status means order submission is in-flight
            # Don't clear it - that would create a race where another caller
            # could claim while the first is still submitting
            # BUT: if claiming has been stuck for too long (crash during submission),
            # clear it to allow retry
            if position.exit_status == "claiming":
                # Check if claiming is stale (stuck for > 60 seconds)
                claiming_timeout_seconds = 60.0
                if stale_after_seconds:
                    # Fetch position updated_at from DB to check staleness
                    try:
                        result = await self._db.fetchrow(
                            "SELECT updated_at FROM positions WHERE token_id = $1 AND status = 'open'",
                            position.token_id,
                        )
                        if result and result.get("updated_at"):
                            updated_at = result["updated_at"]
                            if isinstance(updated_at, str):
                                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                            if updated_at.tzinfo is None:
                                updated_at = updated_at.replace(tzinfo=timezone.utc)
                            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
                            if age_seconds > claiming_timeout_seconds:
                                logger.warning(
                                    f"Position {position.position_id} stuck in claiming state "
                                    f"for {age_seconds:.0f}s; clearing for retry"
                                )
                                await self._position_tracker.clear_exit_pending(
                                    position.position_id,
                                    exit_status="stale_claim",
                                )
                                return "cleared"
                    except Exception as e:
                        logger.warning(f"Error checking claiming staleness: {e}")

                logger.debug(
                    f"Position {position.position_id} in claiming state, "
                    f"order submission in progress"
                )
                return "pending"

            logger.warning(
                f"Position {position.position_id} marked exit_pending without order_id; clearing"
            )
            await self._position_tracker.clear_exit_pending(
                position.position_id,
                exit_status="cleared",
            )
            return "cleared"

        if not self._clob_client:
            logger.warning(
                f"Cannot reconcile exit order {position.exit_order_id} "
                f"for {position.position_id} without CLOB client"
            )
            return "pending"

        order = await self._fetch_order(position.exit_order_id)
        if not order:
            logger.warning(
                f"Exit order {position.exit_order_id} "
                f"for {position.position_id} not found; keeping pending"
            )
            return "pending"

        status = str(order.get("status", "")).upper()
        filled_size = self._coerce_float(order.get("filledSize", 0))
        size = self._coerce_float(order.get("size", 0))

        if status == "MATCHED" or (size > 0 and filled_size >= size):
            exit_price = self._extract_exit_price(
                order,
                fallback=current_price or position.entry_price,
            )
            await self._position_tracker.close_position(
                position.position_id,
                exit_price=exit_price,
                reason=reason or "exit_reconcile",
                exit_order_id=position.exit_order_id,
            )
            return "closed"

        if status in ("CANCELLED", "FAILED", "REJECTED", "EXPIRED"):
            logger.warning(
                f"Exit order {position.exit_order_id} terminal status {status}; clearing pending"
            )
            exit_status = "cancelled" if status == "CANCELLED" else "failed"
            await self._position_tracker.clear_exit_pending(
                position.position_id,
                exit_status=exit_status,
            )
            return "cleared"

        if stale_after_seconds:
            created_at = self._extract_order_timestamp(order)
            if created_at:
                age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
                if age_seconds > stale_after_seconds:
                    if self._cancel_exit_order(position.exit_order_id):
                        logger.warning(
                            f"Cancelled stale exit order {position.exit_order_id} "
                            f"for {position.position_id} after {age_seconds:.0f}s"
                        )
                        await self._position_tracker.clear_exit_pending(
                            position.position_id,
                            exit_status="cancelled",
                        )
                        return "cleared"

        return "pending"

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
                result = await self._fetch_order(order_id)
                if not result:
                    await asyncio.sleep(poll_interval)
                    continue

                status = str(result.get("status", "")).upper()
                filled_size = self._coerce_float(result.get("filledSize", 0))
                size = self._coerce_float(result.get("size", 0))

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

    async def _fetch_order(self, order_id: str) -> Optional[dict[str, Any]]:
        """Fetch order details from CLOB, handling sync/async clients."""
        if not self._clob_client:
            return None
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if hasattr(self._clob_client, "get_order_async"):
                return await self._clob_client.get_order_async(order_id)
            return await loop.run_in_executor(None, self._clob_client.get_order, order_id)
        except Exception as e:
            logger.warning(f"Error fetching order {order_id}: {e}")
            return None

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_decimal(value: Any) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _extract_exit_price(self, order: dict[str, Any], *, fallback: Decimal) -> Decimal:
        for key in ("avgPrice", "avgFillPrice", "avg_price", "price"):
            value = self._coerce_decimal(order.get(key))
            if value is not None:
                return value
        return fallback

    def _extract_order_timestamp(self, order: dict[str, Any]) -> Optional[datetime]:
        for key in (
            "createdAt",
            "created_at",
            "created",
            "timestamp",
            "createdTime",
            "createdTimestamp",
        ):
            parsed = self._parse_timestamp(order.get(key))
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _has_pending_exit(position: Position) -> bool:
        if position.exit_pending:
            return True
        if position.exit_status in ("pending", "timeout"):
            return True
        if position.exit_order_id and not position.exit_status:
            return True
        return False

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str):
            val = value.strip()
            if not val:
                return None
            if val.isdigit():
                ts = float(val)
                if ts > 1e12:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _cancel_exit_order(self, order_id: str) -> bool:
        if not self._clob_client:
            return False
        for method_name in ("cancel", "cancel_order"):
            cancel = getattr(self._clob_client, method_name, None)
            if cancel:
                try:
                    cancel(order_id)
                    return True
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order_id}: {e}")
                    return False
        return False

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
        """
        Calculate how long a position has been held for exit logic.

        Uses position.hold_start which returns hold_start_at if set,
        otherwise falls back to entry_time. This allows imported positions
        to have different hold periods than bot-created positions.
        """
        now = datetime.now(timezone.utc)
        return now - position.hold_start

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
            exit_order_id=None,
        )

        # FIX: G4 protection - refresh balance after resolution settlement
        self._balance_manager.refresh_balance()

        logger.info(f"Position {position.position_id} resolved: {reason}")
        return True
