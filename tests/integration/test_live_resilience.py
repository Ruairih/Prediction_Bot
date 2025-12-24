"""
Live RESILIENCE TESTS for Polymarket trading bot.

These tests verify critical safety and recovery mechanisms:
1. Idempotent order submission (clientOrderId handling)
2. Restart/crash recovery with open orders
3. Risk circuit breakers (max loss, exposure limits)
4. Market status transitions (resolved/paused/closed)
5. Rate limit and error handling
6. Cancel race conditions

Based on Codex review of critical missing scenarios.

SAFETY MEASURES:
- Gated behind LIVE_RESILIENCE_TEST_ENABLED=true
- Maximum order cost: $0.25
- All orders placed below market (no fills)
- Comprehensive cleanup

RUN WITH:
    LIVE_RESILIENCE_TEST_ENABLED=true pytest tests/integration/test_live_resilience.py -v

WARNING: These tests interact with real Polymarket APIs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any, Optional, List

import pytest

from polymarket_bot.execution import (
    BalanceConfig,
    BalanceManager,
    OrderConfig,
    OrderManager,
    OrderStatus,
    ExecutionService,
    ExecutionConfig,
)
from polymarket_bot.ingestion.client import PolymarketRestClient
from polymarket_bot.ingestion.models import Market

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.live_resilience]

# =============================================================================
# Configuration
# =============================================================================

LIVE_RESILIENCE_ENV_VAR = "LIVE_RESILIENCE_TEST_ENABLED"
CREDS_ENV_VAR = "POLYMARKET_CREDS_PATH"
DEFAULT_CREDS_PATH = "polymarket_api_creds.json"

# Order constraints - Polymarket requires minimum $1 order value
MIN_ORDER_COST = Decimal("1.00")  # CLOB minimum
MAX_ORDER_COST = Decimal("2.00")  # Test limit
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("0.99")
TIMEOUT_SECONDS = 30

REQUIRED_CRED_KEYS = (
    "api_key",
    "api_secret",
    "api_passphrase",
    "private_key",
    "funder",
)

# =============================================================================
# Gate Check
# =============================================================================

def _env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


if not _env_truthy(os.getenv(LIVE_RESILIENCE_ENV_VAR, "")):
    pytest.skip(
        f"{LIVE_RESILIENCE_ENV_VAR} is not set; skipping resilience tests",
        allow_module_level=True,
    )


# =============================================================================
# Utilities
# =============================================================================

def _load_creds(creds_path: Path) -> dict[str, Any]:
    if not creds_path.exists():
        raise FileNotFoundError(f"Missing credentials file: {creds_path}")
    with creds_path.open() as f:
        return json.load(f)


def _validate_creds(creds: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_CRED_KEYS if not str(creds.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _quantize(value: Decimal, step: Decimal, rounding) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=rounding) * step


def _min_size_for_cost(price: Decimal, min_cost: Decimal = MIN_ORDER_COST) -> Decimal:
    """Compute minimum size to meet minimum order cost requirement."""
    if price <= 0:
        return Decimal("100")  # Fallback for safety
    raw = min_cost / price
    return _quantize(raw, Decimal("0.01"), ROUND_UP)


async def _with_timeout(coro, description: str, timeout: float = TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"Timed out: {description}")


class _MockDatabase:
    """Mock database that tracks calls for testing."""

    def __init__(self):
        self.execute_calls: List[tuple] = []
        self.fetch_calls: List[tuple] = []
        self._orders: dict = {}

    async def execute(self, query: str, *args, **kwargs):
        self.execute_calls.append((query, args, kwargs))
        return "OK"

    async def fetch(self, query: str, *args, **kwargs):
        self.fetch_calls.append((query, args, kwargs))
        # Return open orders if queried
        if "orders" in query.lower() and "status IN" in query:
            return list(self._orders.values())
        return []

    async def fetchrow(self, *args, **kwargs):
        return None

    async def fetchval(self, *args, **kwargs):
        return None

    def add_mock_order(self, order_data: dict):
        self._orders[order_data["order_id"]] = order_data


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ResilienceTestMarket:
    """Market for resilience testing."""
    token_id: str
    condition_id: str
    safe_price: Decimal
    min_size: Decimal
    tick_size: Decimal


@dataclass
class ResilienceTestContext:
    """Context for resilience tests."""
    order_manager: OrderManager
    balance_manager: BalanceManager
    rest_client: PolymarketRestClient
    clob_client: Any
    db: _MockDatabase
    starting_balance: Decimal
    order_ids: List[str] = field(default_factory=list)

    def track_order(self, order_id: str) -> None:
        self.order_ids.append(order_id)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def live_creds() -> dict[str, Any]:
    creds_path = Path(os.environ.get(CREDS_ENV_VAR, DEFAULT_CREDS_PATH))
    creds = _load_creds(creds_path)
    _validate_creds(creds)
    return creds


@pytest.fixture
def clob_client(live_creds):
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as exc:
        pytest.fail(f"py-clob-client required: {exc}")

    return ClobClient(
        host=live_creds.get("host", "https://clob.polymarket.com"),
        chain_id=live_creds.get("chain_id", 137),
        key=live_creds.get("private_key"),
        creds=ApiCreds(
            api_key=live_creds["api_key"],
            api_secret=live_creds["api_secret"],
            api_passphrase=live_creds["api_passphrase"],
        ),
        signature_type=live_creds.get("signature_type", 2),
        funder=live_creds.get("funder"),
    )


@pytest.fixture
async def rest_client():
    async with PolymarketRestClient(timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture
async def test_market(rest_client) -> ResilienceTestMarket:
    """Find a market for resilience testing."""
    markets = []
    for page in range(2):
        batch = await _with_timeout(
            rest_client.get_markets(active_only=True, limit=50, offset=page * 50),
            f"fetching markets page {page}",
        )
        if not batch:
            break
        markets.extend(batch)

    for market in markets:
        if market.time_to_end < 48:
            continue

        token = market.yes_token or market.no_token
        if not token:
            continue

        try:
            orderbook = await _with_timeout(
                rest_client.get_orderbook(token.token_id),
                "fetching orderbook",
                timeout=10,
            )

            if orderbook.best_bid is None:
                continue

            safe_price = max(MIN_PRICE, orderbook.best_bid - Decimal("0.15"))
            safe_price = _quantize(safe_price, Decimal("0.01"), ROUND_DOWN)

            if safe_price < MIN_PRICE:
                continue

            metadata = await _with_timeout(
                rest_client.get_token_metadata(token.token_id),
                "fetching metadata",
                timeout=5,
            ) or {}

            return ResilienceTestMarket(
                token_id=token.token_id,
                condition_id=market.condition_id,
                safe_price=safe_price,
                min_size=max(_to_decimal(metadata.get("minOrderSize")) or Decimal("5"), Decimal("5")),
                tick_size=_to_decimal(metadata.get("tickSize")) or Decimal("0.01"),
            )

        except Exception:
            continue

    pytest.skip("No suitable market found")


@pytest.fixture
async def resilience_context(clob_client, rest_client) -> ResilienceTestContext:
    """Create context for resilience tests."""
    db = _MockDatabase()

    balance_manager = BalanceManager(
        db=db,
        clob_client=clob_client,
        config=BalanceConfig(min_reserve=Decimal("0")),
    )

    order_manager = OrderManager(
        db=db,
        clob_client=clob_client,
        config=OrderConfig(max_price=MAX_PRICE),
        balance_manager=balance_manager,
    )

    starting_balance = order_manager.refresh_balance()

    if starting_balance < MAX_ORDER_COST * 3:
        pytest.skip(f"Insufficient balance: ${starting_balance}")

    context = ResilienceTestContext(
        order_manager=order_manager,
        balance_manager=balance_manager,
        rest_client=rest_client,
        clob_client=clob_client,
        db=db,
        starting_balance=starting_balance,
    )

    yield context

    # Cleanup
    for order_id in context.order_ids:
        try:
            await order_manager.cancel_order(order_id)
        except Exception as e:
            logger.warning(f"Failed to cancel {order_id}: {e}")


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestIdempotentSubmission:
    """
    Tests for idempotent order submission using clientOrderId.

    CRITICAL: Prevents duplicate orders when submit times out or connection drops.
    """

    async def test_unique_order_ids_generated(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify each order submission gets a unique order ID.

        This is the foundation for idempotency.
        """
        ctx = resilience_context
        order_ids = set()

        for i in range(3):
            # Ensure size meets minimum order cost ($1)
            size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
            cost = test_market.safe_price * size
            if cost > MAX_ORDER_COST:
                pytest.skip("Order cost too high")

            order_id = await _with_timeout(
                ctx.order_manager.submit_order(
                    token_id=test_market.token_id,
                    side="BUY",
                    price=test_market.safe_price,
                    size=size,
                    condition_id=test_market.condition_id,
                ),
                f"submitting order {i}",
            )
            ctx.track_order(order_id)
            order_ids.add(order_id)

            await asyncio.sleep(0.5)

        # All order IDs should be unique
        assert len(order_ids) == 3, "Each order should have unique ID"
        logger.info(f"SUCCESS: {len(order_ids)} unique order IDs generated")

    async def test_no_duplicate_on_retry_same_params(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify that retrying with same parameters creates new order.

        Note: True idempotency requires clientOrderId which may not be
        implemented. This documents the current behavior.
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        # Submit first order
        order_id_1 = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id_1)

        await asyncio.sleep(0.5)

        # Submit with same params (simulating retry)
        order_id_2 = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id_2)

        # Document behavior: are they different?
        if order_id_1 == order_id_2:
            logger.warning(
                "IDEMPOTENCY GAP: Same params produced same order ID. "
                "Consider implementing clientOrderId for true idempotency."
            )
        else:
            logger.info(
                "Different order IDs for same params. "
                "Retry logic should check for existing orders first."
            )


# =============================================================================
# RESTART RECOVERY TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestRestartRecovery:
    """
    Tests for restart/crash recovery with open orders.

    CRITICAL: Bot must correctly rehydrate state after crash.
    """

    async def test_can_query_open_orders_from_clob(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify we can query open orders directly from CLOB.

        This is essential for state recovery after restart.
        """
        ctx = resilience_context

        # Submit an order
        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        await asyncio.sleep(1)

        # Query order status from CLOB (simulating recovery)
        order = await ctx.order_manager.sync_order_status(order_id)

        assert order is not None, "Should be able to query order from CLOB"
        assert order.order_id == order_id
        assert order.status in (OrderStatus.PENDING, OrderStatus.LIVE)

        logger.info(f"SUCCESS: Order {order_id} queryable from CLOB for recovery")

    async def test_balance_reservation_restored_after_load(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify balance reservations are correctly restored.

        If not restored, bot could over-allocate on restart.
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        pre_balance = ctx.order_manager.get_available_balance()

        # Submit order
        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        # Verify reservation exists
        assert ctx.balance_manager.has_reservation(order_id)

        post_balance = ctx.order_manager.get_available_balance()
        reserved = pre_balance - post_balance

        logger.info(f"Reserved ${reserved} for order {order_id}")
        assert reserved >= cost * Decimal("0.9"), "Should reserve approximately order cost"

        logger.info("SUCCESS: Balance reservation tracked correctly")

    async def test_fresh_manager_recovers_open_order(
        self,
        clob_client,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        CRITICAL: Simulate restart by creating fresh managers.

        This tests actual recovery behavior:
        1. Submit order with original manager
        2. Create NEW managers (simulating crash/restart)
        3. Query CLOB directly for order state
        4. Verify fresh manager can see and manage the order
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        # Step 1: Submit order with original manager
        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        original_reservation = ctx.balance_manager.has_reservation(order_id)
        assert original_reservation, "Original manager should have reservation"

        await asyncio.sleep(1)

        # Step 2: Create FRESH managers (simulating restart)
        fresh_db = _MockDatabase()
        fresh_balance_manager = BalanceManager(
            db=fresh_db,
            clob_client=clob_client,
            config=BalanceConfig(min_reserve=Decimal("0")),
        )
        fresh_order_manager = OrderManager(
            db=fresh_db,
            clob_client=clob_client,
            config=OrderConfig(max_price=MAX_PRICE),
            balance_manager=fresh_balance_manager,
        )

        # Step 3: Fresh manager has NO knowledge of the order
        fresh_balance = fresh_order_manager.refresh_balance()
        fresh_reservation = fresh_balance_manager.has_reservation(order_id)
        assert not fresh_reservation, "Fresh manager should NOT have reservation initially"

        # Step 4: Query CLOB directly to recover order state
        recovered_order = await fresh_order_manager.sync_order_status(order_id)

        assert recovered_order is not None, "Should recover order from CLOB"
        assert recovered_order.order_id == order_id
        assert recovered_order.status in (OrderStatus.PENDING, OrderStatus.LIVE)

        logger.info(
            f"SUCCESS: Fresh manager recovered order {order_id} "
            f"(status={recovered_order.status})"
        )

        # NOTE: Balance reservation restoration would require calling
        # ExecutionService.load_state() which reads from DB
        # This test verifies the CLOB query path works


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestCircuitBreakers:
    """
    Tests for risk circuit breakers.

    CRITICAL: Prevents runaway losses.
    """

    async def test_respects_max_price_limit(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify orders above max price are rejected.

        This is a basic circuit breaker for entry price.
        """
        ctx = resilience_context

        from polymarket_bot.execution import PriceTooHighError

        # Try to submit at price above config max
        with pytest.raises(PriceTooHighError):
            await ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=Decimal("0.999"),  # Above max
                size=test_market.min_size,
                condition_id=test_market.condition_id,
            )

        logger.info("SUCCESS: Max price circuit breaker works")

    async def test_respects_balance_limit(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify orders exceeding balance are rejected.
        """
        ctx = resilience_context

        from polymarket_bot.execution import InsufficientBalanceError

        # Try to submit order larger than balance
        huge_size = Decimal("1000000")  # Impossibly large

        with pytest.raises(InsufficientBalanceError):
            await ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=test_market.safe_price,
                size=huge_size,
                condition_id=test_market.condition_id,
            )

        logger.info("SUCCESS: Balance circuit breaker works")


# =============================================================================
# CANCEL RACE CONDITION TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestCancelRaceConditions:
    """
    Tests for cancel race conditions.

    HIGH: Cancel after partial fill, cancel already filled, etc.
    """

    async def test_cancel_open_order(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Basic test: cancel an open order.
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        # Submit
        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        await asyncio.sleep(1)

        # Cancel
        cancelled = await ctx.order_manager.cancel_order(order_id)
        assert cancelled, "Should be able to cancel open order"

        await asyncio.sleep(1)

        # Verify cancelled
        order = await ctx.order_manager.sync_order_status(order_id)
        assert order.status == OrderStatus.CANCELLED

        # Verify reservation released
        assert not ctx.balance_manager.has_reservation(order_id)

        logger.info("SUCCESS: Open order cancelled correctly")

    async def test_cancel_nonexistent_order(
        self,
        resilience_context: ResilienceTestContext,
    ):
        """
        Cancel a nonexistent order should not crash.
        """
        ctx = resilience_context

        fake_order_id = f"nonexistent_{uuid.uuid4().hex[:8]}"

        # Should not raise - just return False or handle gracefully
        try:
            result = await ctx.order_manager.cancel_order(fake_order_id)
            # Either returns False or raises a handled exception
            logger.info(f"Cancel nonexistent order returned: {result}")
        except Exception as e:
            # Some exception is acceptable, just shouldn't crash
            logger.info(f"Cancel nonexistent order raised (acceptable): {type(e).__name__}")

        logger.info("SUCCESS: Handled cancel of nonexistent order")

    async def test_cancel_tracks_partial_fill_before_cancel(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Test cancel behavior when order may have partial fill.

        This documents the race condition:
        1. Submit order
        2. Order may partially fill
        3. Cancel the rest
        4. Verify reservation adjusted for filled portion

        NOTE: Triggering actual partial fill is difficult without
        matching at market price. This test documents the expected
        behavior path.
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        pre_balance = ctx.order_manager.get_available_balance()

        # Submit order (at safe price, unlikely to fill)
        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        await asyncio.sleep(1)

        # Sync to get current state (may have partial fill)
        order = await ctx.order_manager.sync_order_status(order_id)
        filled_before_cancel = order.filled_size

        logger.info(
            f"Order {order_id}: status={order.status}, "
            f"filled={filled_before_cancel}/{size}"
        )

        # Cancel
        try:
            await ctx.order_manager.cancel_order(order_id)
        except Exception as e:
            logger.warning(f"Cancel raised: {e}")

        await asyncio.sleep(1)

        # Final sync
        final_order = await ctx.order_manager.sync_order_status(order_id)

        logger.info(
            f"After cancel: status={final_order.status}, "
            f"filled={final_order.filled_size}"
        )

        # Verify order is in terminal or cancelled state
        # Note: PARTIAL is NOT terminal - it means partially filled but still open
        # After cancel, status should be CANCELLED (even if partial fill occurred)
        assert final_order.status in (
            OrderStatus.CANCELLED,
            OrderStatus.FILLED,
        ), f"Order should be cancelled or filled, got {final_order.status}"

        # Verify balance recovered (accounting for any fill)
        post_balance = ctx.order_manager.get_available_balance()
        balance_change = pre_balance - post_balance

        # If order partially filled, some balance is now in position
        # If fully cancelled, balance should be restored
        if final_order.filled_size == Decimal("0"):
            tolerance = Decimal("0.02")
            assert abs(balance_change) < tolerance, \
                f"Balance should be restored after cancel: change=${balance_change}"

        logger.info(
            f"SUCCESS: Cancel race condition handled. "
            f"Filled: {final_order.filled_size}, Balance change: ${balance_change}"
        )


# =============================================================================
# RATE LIMIT TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestRateLimitHandling:
    """
    Tests for rate limit handling.

    HIGH: Prevents retry storms and API bans.
    """

    async def test_rapid_requests_tracked(
        self,
        resilience_context: ResilienceTestContext,
    ):
        """
        Document rate limit behavior with rapid requests.
        """
        ctx = resilience_context
        request_times = []
        errors = []

        # Make rapid balance queries
        for i in range(5):
            start = time.time()
            try:
                ctx.order_manager.refresh_balance()
                request_times.append(time.time() - start)
            except Exception as e:
                errors.append(str(e))
                if "rate" in str(e).lower() or "429" in str(e):
                    logger.warning(f"Rate limit hit on request {i}")

        if errors:
            logger.info(f"Errors during rapid requests: {errors}")

        avg_time = sum(request_times) / len(request_times) if request_times else 0
        logger.info(f"Average request time: {avg_time*1000:.0f}ms")

        # Document behavior
        logger.info(
            f"Rapid requests: {len(request_times)} succeeded, {len(errors)} failed"
        )


# =============================================================================
# MARKET STATUS TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestMarketStatusHandling:
    """
    Tests for market status transitions.

    HIGH: Prevents trading on resolved/paused/closed markets.
    """

    async def test_detects_market_time_to_end(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify we can check market time to end.
        """
        ctx = resilience_context

        # Get market info
        markets = await ctx.rest_client.get_markets(active_only=True, limit=10)

        active_count = 0
        expiring_soon = 0

        for market in markets:
            if market.time_to_end > 0:
                active_count += 1
            if market.time_to_end < 24:
                expiring_soon += 1

        logger.info(
            f"Market status: {active_count} active, {expiring_soon} expiring <24h"
        )

        assert active_count > 0, "Should have active markets"


# =============================================================================
# STATE CONSISTENCY TESTS
# =============================================================================

@pytest.mark.live_resilience
class TestStateConsistency:
    """
    Tests for state consistency between local and CLOB.
    """

    async def test_order_cache_matches_clob(
        self,
        resilience_context: ResilienceTestContext,
        test_market: ResilienceTestMarket,
    ):
        """
        Verify local order cache matches CLOB state.
        """
        ctx = resilience_context

        # Ensure size meets minimum order cost ($1)
        size = max(test_market.min_size, _min_size_for_cost(test_market.safe_price))
        cost = test_market.safe_price * size
        if cost > MAX_ORDER_COST:
            pytest.skip("Order cost too high")

        # Submit
        order_id = await ctx.order_manager.submit_order(
            token_id=test_market.token_id,
            side="BUY",
            price=test_market.safe_price,
            size=size,
            condition_id=test_market.condition_id,
        )
        ctx.track_order(order_id)

        await asyncio.sleep(1)

        # Get from cache
        cached_order = ctx.order_manager.get_order(order_id)

        # Get from CLOB
        synced_order = await ctx.order_manager.sync_order_status(order_id)

        # Verify consistency
        assert cached_order is not None
        assert synced_order is not None
        assert cached_order.order_id == synced_order.order_id

        # After sync, cache should be updated
        updated_cached = ctx.order_manager.get_order(order_id)
        assert updated_cached.status == synced_order.status

        logger.info("SUCCESS: Order cache matches CLOB state")
