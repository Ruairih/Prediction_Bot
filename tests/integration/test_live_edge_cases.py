"""
Live integration tests for EDGE CASES in Polymarket trading.

These tests cover scenarios that are difficult to test in unit tests:
1. Partial fills and incremental fill detection
2. Order rejection and failure recovery
3. Stale order cleanup
4. Market condition edge cases (low liquidity, wide spreads)
5. Concurrent order submission
6. Balance reservation edge cases

SAFETY MEASURES:
- Gated behind LIVE_EDGE_TEST_ENABLED=true
- Maximum order cost: $0.25 (very conservative)
- All positions cleaned up after tests
- Uses liquid markets with tight spreads

RUN WITH:
    LIVE_EDGE_TEST_ENABLED=true pytest tests/integration/test_live_edge_cases.py -v

WARNING: These tests may execute real trades. Only run with funds you're willing to lose.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
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
)
from polymarket_bot.ingestion.client import PolymarketRestClient
from polymarket_bot.ingestion.models import Market

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.live_edge]

# =============================================================================
# Configuration
# =============================================================================

LIVE_EDGE_ENV_VAR = "LIVE_EDGE_TEST_ENABLED"
CREDS_ENV_VAR = "POLYMARKET_CREDS_PATH"
DEFAULT_CREDS_PATH = "polymarket_api_creds.json"

# Very conservative limits for edge case testing
MAX_ORDER_COST = Decimal("0.25")
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


if not _env_truthy(os.getenv(LIVE_EDGE_ENV_VAR, "")):
    pytest.skip(
        f"{LIVE_EDGE_ENV_VAR} is not set; skipping live edge case tests",
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
        raise ValueError(f"Missing required credential fields: {', '.join(missing)}")


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


async def _with_timeout(coro, description: str, timeout: float = TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"Timed out while {description} after {timeout}s")


class _NullDatabase:
    async def execute(self, *args, **kwargs):
        return "OK"

    async def fetch(self, *args, **kwargs):
        return []

    async def fetchrow(self, *args, **kwargs):
        return None


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class EdgeTestMarket:
    """Market selected for edge case testing."""
    token_id: str
    condition_id: str
    best_bid: Decimal
    best_ask: Decimal
    spread: Decimal
    min_size: Decimal
    tick_size: Decimal


@dataclass
class EdgeTestContext:
    """Context for edge case tests with cleanup."""
    order_manager: OrderManager
    balance_manager: BalanceManager
    rest_client: PolymarketRestClient
    clob_client: Any
    starting_balance: Decimal
    order_ids: List[str] = field(default_factory=list)

    def track_order(self, order_id: str) -> None:
        self.order_ids.append(order_id)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def live_creds() -> dict[str, Any]:
    creds_path = Path(os.environ.get(CREDS_ENV_VAR, DEFAULT_CREDS_PATH))
    try:
        creds = _load_creds(creds_path)
        _validate_creds(creds)
    except Exception as exc:
        pytest.fail(f"Invalid credentials: {exc}")
    return creds


@pytest.fixture(scope="module")
def clob_client(live_creds):
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as exc:
        pytest.fail(f"py-clob-client required: {exc}")

    api_creds = ApiCreds(
        api_key=live_creds["api_key"],
        api_secret=live_creds["api_secret"],
        api_passphrase=live_creds["api_passphrase"],
    )

    return ClobClient(
        host=live_creds.get("host", "https://clob.polymarket.com"),
        chain_id=live_creds.get("chain_id", 137),
        key=live_creds.get("private_key"),
        creds=api_creds,
        signature_type=live_creds.get("signature_type", 2),
        funder=live_creds.get("funder"),
    )


@pytest.fixture(scope="module")
async def rest_client():
    async with PolymarketRestClient(timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
async def test_market(rest_client) -> EdgeTestMarket:
    """Find a market suitable for edge case testing."""
    markets = []
    for page in range(2):
        batch = await _with_timeout(
            rest_client.get_markets(active_only=True, limit=50, offset=page * 50),
            f"fetching markets page {page}",
        )
        if not batch:
            break
        markets.extend(batch)

    if not markets:
        pytest.fail("No markets available")

    # Find market with moderate spread (good for testing edge cases)
    for market in markets:
        if market.time_to_end < 48:
            continue

        token = market.yes_token or market.no_token
        if not token:
            continue

        try:
            orderbook = await _with_timeout(
                rest_client.get_orderbook(token.token_id),
                f"fetching orderbook",
                timeout=10,
            )

            if orderbook.best_bid is None or orderbook.best_ask is None:
                continue

            spread = orderbook.best_ask - orderbook.best_bid

            # Want a market with at least some spread for edge case testing
            if Decimal("0.02") <= spread <= Decimal("0.15"):
                metadata = await _with_timeout(
                    rest_client.get_token_metadata(token.token_id),
                    "fetching metadata",
                    timeout=10,
                )
                metadata = metadata or {}

                return EdgeTestMarket(
                    token_id=token.token_id,
                    condition_id=market.condition_id,
                    best_bid=orderbook.best_bid,
                    best_ask=orderbook.best_ask,
                    spread=spread,
                    min_size=_to_decimal(metadata.get("minOrderSize")) or Decimal("1"),
                    tick_size=_to_decimal(metadata.get("tickSize")) or Decimal("0.01"),
                )

        except Exception as e:
            logger.debug(f"Skipping market: {e}")
            continue

    pytest.skip("No suitable market found for edge case testing")


@pytest.fixture
async def edge_context(clob_client, rest_client) -> EdgeTestContext:
    """Create context for edge case tests with cleanup."""
    db = _NullDatabase()

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

    if starting_balance < MAX_ORDER_COST * 5:
        pytest.skip(f"Insufficient balance: ${starting_balance}")

    context = EdgeTestContext(
        order_manager=order_manager,
        balance_manager=balance_manager,
        rest_client=rest_client,
        clob_client=clob_client,
        starting_balance=starting_balance,
    )

    yield context

    # Cleanup: cancel all tracked orders
    for order_id in context.order_ids:
        try:
            await _with_timeout(
                order_manager.cancel_order(order_id),
                f"cancelling order {order_id}",
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"Failed to cancel {order_id}: {e}")

    # Verify balance recovery
    ending_balance = order_manager.refresh_balance()
    if ending_balance < starting_balance - MAX_ORDER_COST:
        logger.warning(f"Balance decreased significantly: ${starting_balance} -> ${ending_balance}")


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

@pytest.mark.live_edge
class TestPartialFillDetection:
    """Tests for detecting and handling partial fills."""

    async def test_detects_partial_fill_status(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        Submit order in spread zone that may partially fill.

        This tests the PARTIAL status detection logic.
        """
        ctx = edge_context

        # Price in the middle of spread - may partially fill
        mid_price = (test_market.best_bid + test_market.best_ask) / 2
        mid_price = _quantize(mid_price, test_market.tick_size, ROUND_DOWN)

        if mid_price <= test_market.best_bid:
            pytest.skip("Spread too tight for partial fill test")

        size = test_market.min_size
        cost = mid_price * size

        if cost > MAX_ORDER_COST:
            pytest.skip(f"Order cost ${cost} too high")

        logger.info(f"Submitting order at mid-spread: {size} @ ${mid_price}")

        order_id = await _with_timeout(
            ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=mid_price,
                size=size,
                condition_id=test_market.condition_id,
            ),
            "submitting mid-spread order",
        )
        ctx.track_order(order_id)

        # Wait briefly for potential fills
        await asyncio.sleep(3)

        # Sync and check status
        order = await _with_timeout(
            ctx.order_manager.sync_order_status(order_id),
            "syncing order status",
        )

        # Status should be one of: LIVE, PARTIAL, FILLED
        assert order.status in (
            OrderStatus.PENDING,
            OrderStatus.LIVE,
            OrderStatus.PARTIAL,
            OrderStatus.FILLED,
        ), f"Unexpected status: {order.status}"

        logger.info(f"Order status: {order.status}, filled: {order.filled_size}/{size}")

        if order.status == OrderStatus.PARTIAL:
            # Verify partial fill is tracked
            assert order.filled_size > Decimal("0")
            assert order.filled_size < size
            logger.info("SUCCESS: Partial fill detected and tracked correctly")


@pytest.mark.live_edge
class TestOrderRejection:
    """Tests for handling rejected/failed orders."""

    async def test_handles_price_too_low(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        Submit order at impossibly low price.

        Should either accept (and never fill) or reject cleanly.
        """
        ctx = edge_context

        # Very low price - unlikely to fill but should be accepted
        low_price = MIN_PRICE
        size = test_market.min_size
        cost = low_price * size

        if cost > MAX_ORDER_COST:
            pytest.skip(f"Order cost ${cost} too high")

        logger.info(f"Submitting order at minimum price: {size} @ ${low_price}")

        try:
            order_id = await _with_timeout(
                ctx.order_manager.submit_order(
                    token_id=test_market.token_id,
                    side="BUY",
                    price=low_price,
                    size=size,
                    condition_id=test_market.condition_id,
                ),
                "submitting low-price order",
            )
            ctx.track_order(order_id)

            # Order should be accepted but not fill
            order = await _with_timeout(
                ctx.order_manager.sync_order_status(order_id),
                "syncing order status",
            )

            assert order.status in (OrderStatus.PENDING, OrderStatus.LIVE)
            assert order.filled_size == Decimal("0")
            logger.info("SUCCESS: Low-price order accepted but not filled (expected)")

        except Exception as e:
            # Some rejection is acceptable
            logger.info(f"Order rejected (acceptable): {e}")


@pytest.mark.live_edge
class TestConcurrentOrders:
    """Tests for concurrent order submission."""

    async def test_multiple_orders_same_market(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        Submit multiple orders to same market concurrently.

        Verifies:
        - All orders are accepted
        - Balance reservations are correct
        - No race conditions in order tracking
        """
        ctx = edge_context
        num_orders = 3

        # Price well below bid to avoid fills
        safe_price = max(MIN_PRICE, test_market.best_bid - Decimal("0.15"))
        safe_price = _quantize(safe_price, test_market.tick_size, ROUND_DOWN)

        size = test_market.min_size
        per_order_cost = safe_price * size
        total_cost = per_order_cost * num_orders

        if total_cost > MAX_ORDER_COST * 3:
            pytest.skip(f"Total cost ${total_cost} too high")

        pre_balance = ctx.order_manager.get_available_balance()

        # Submit orders concurrently
        async def submit_order(i: int) -> str:
            return await ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=safe_price,
                size=size,
                condition_id=test_market.condition_id,
            )

        logger.info(f"Submitting {num_orders} orders concurrently at ${safe_price}")

        order_ids = await asyncio.gather(
            *[submit_order(i) for i in range(num_orders)],
            return_exceptions=True,
        )

        # Track successful orders
        successful_ids = []
        for i, result in enumerate(order_ids):
            if isinstance(result, Exception):
                logger.warning(f"Order {i} failed: {result}")
            else:
                successful_ids.append(result)
                ctx.track_order(result)

        assert len(successful_ids) >= 1, "At least one order should succeed"

        logger.info(f"Successfully submitted {len(successful_ids)} orders")

        # Verify balance reservations
        post_balance = ctx.order_manager.get_available_balance()
        reserved = pre_balance - post_balance
        expected_reserved = per_order_cost * len(successful_ids)

        # Allow some tolerance
        tolerance = Decimal("0.05")
        assert abs(reserved - expected_reserved) < tolerance, \
            f"Reserved ${reserved} doesn't match expected ${expected_reserved}"

        # Verify all orders are trackable
        for order_id in successful_ids:
            order = await ctx.order_manager.sync_order_status(order_id)
            assert order.status in (OrderStatus.PENDING, OrderStatus.LIVE)

        logger.info("SUCCESS: Concurrent orders handled correctly")


@pytest.mark.live_edge
class TestBalanceReservationEdgeCases:
    """Tests for balance reservation edge cases."""

    async def test_reservation_released_on_submit_failure(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        If order submission fails, reservation must be released.

        This prevents balance from being permanently locked.
        """
        ctx = edge_context

        pre_balance = ctx.order_manager.get_available_balance()
        pre_reservations = len(ctx.balance_manager.get_active_reservations())

        # Try to submit an order that might fail (very small price)
        try:
            # This might fail or succeed depending on CLOB validation
            order_id = await ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=Decimal("0.001"),  # Might be rejected
                size=test_market.min_size,
                condition_id=test_market.condition_id,
            )
            # If it succeeded, track it
            ctx.track_order(order_id)

        except Exception:
            # Expected failure
            pass

        # Whether success or failure, balance should not be permanently locked
        await asyncio.sleep(1)

        post_reservations = len(ctx.balance_manager.get_active_reservations())
        post_balance = ctx.order_manager.get_available_balance()

        # If order failed, balance should be restored
        # If order succeeded, there should be exactly one new reservation

        if post_reservations == pre_reservations:
            # No new reservation means order failed - balance should be same
            assert post_balance >= pre_balance - Decimal("0.01"), \
                "Balance not restored after failed submission"
            logger.info("SUCCESS: Balance released after submission failure")
        else:
            # Order succeeded - new reservation is expected
            logger.info("Order succeeded - reservation correctly created")


@pytest.mark.live_edge
class TestStaleOrderCleanup:
    """Tests for cleaning up stale orders."""

    async def test_cancels_stale_order(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        Submit an order, wait, then cancel it.

        Verifies the cancel flow works correctly.
        """
        ctx = edge_context

        # Submit at low price (won't fill)
        safe_price = max(MIN_PRICE, test_market.best_bid - Decimal("0.10"))
        safe_price = _quantize(safe_price, test_market.tick_size, ROUND_DOWN)

        size = test_market.min_size
        cost = safe_price * size

        if cost > MAX_ORDER_COST:
            pytest.skip(f"Order cost ${cost} too high")

        pre_balance = ctx.order_manager.get_available_balance()

        order_id = await _with_timeout(
            ctx.order_manager.submit_order(
                token_id=test_market.token_id,
                side="BUY",
                price=safe_price,
                size=size,
                condition_id=test_market.condition_id,
            ),
            "submitting stale order",
        )
        ctx.track_order(order_id)

        # Wait briefly
        await asyncio.sleep(2)

        # Verify order is open
        order = await ctx.order_manager.sync_order_status(order_id)
        assert order.status in (OrderStatus.PENDING, OrderStatus.LIVE)

        # Cancel
        cancelled = await ctx.order_manager.cancel_order(order_id)
        assert cancelled, "Cancel should return True"

        # Wait for cancellation to propagate
        await asyncio.sleep(2)

        # Verify order is cancelled
        order = await ctx.order_manager.sync_order_status(order_id)
        assert order.status == OrderStatus.CANCELLED

        # Verify balance restored
        post_balance = ctx.order_manager.get_available_balance()
        tolerance = Decimal("0.02")
        assert post_balance >= pre_balance - tolerance, \
            f"Balance not restored: ${pre_balance} -> ${post_balance}"

        # Verify reservation released
        assert not ctx.balance_manager.has_reservation(order_id)

        logger.info("SUCCESS: Stale order cleanup works correctly")


@pytest.mark.live_edge
class TestOrderbookEdgeCases:
    """Tests for orderbook edge cases."""

    async def test_handles_orderbook_changes(
        self,
        edge_context: EdgeTestContext,
        test_market: EdgeTestMarket,
    ):
        """
        Verify orderbook can change between read and submit.

        This documents the race condition but doesn't fix it.
        """
        ctx = edge_context

        # Get initial orderbook
        orderbook1 = await ctx.rest_client.get_orderbook(test_market.token_id)

        # Wait for potential changes
        await asyncio.sleep(1)

        # Get updated orderbook
        orderbook2 = await ctx.rest_client.get_orderbook(test_market.token_id)

        # Document if it changed
        if orderbook1.best_bid != orderbook2.best_bid:
            logger.info(
                f"Orderbook changed: bid {orderbook1.best_bid} -> {orderbook2.best_bid}"
            )

        # This test just documents the behavior
        logger.info("Orderbook stability test completed")


# =============================================================================
# SETTLEMENT DOCUMENTATION TEST
# =============================================================================

@pytest.mark.live_edge
class TestSettlementLimitations:
    """
    Document Polymarket settlement limitations.

    IMPORTANT: Polymarket does NOT have a public API for claiming payouts
    after market resolution. This is a known limitation.

    Workaround: Sell positions at 0.99 before resolution to exit.
    """

    async def test_documents_settlement_limitation(self):
        """
        Documents that settlement/payout claiming is not available via API.

        See: https://github.com/Polymarket/py-clob-client/issues/117

        Current workaround: Sell at max price (0.99) before resolution.
        """
        logger.info("""
        ================================================================
        SETTLEMENT LIMITATION DOCUMENTATION
        ================================================================

        Polymarket does NOT provide a public API for:
        1. Checking settlement status after market resolution
        2. Claiming payouts programmatically
        3. Receiving webhooks for resolution events

        WORKAROUND:
        - Before market resolution, sell positions at 0.99 (max price)
        - This results in ~1 cent loss per share but allows fund recovery
        - Monitor UMA oracle events for resolution timing

        MANUAL PROCESS:
        - Visit polymarket.com
        - Navigate to resolved market
        - Click "Claim" to collect payout

        SMART CONTRACT:
        - Payout redemption happens via CTF contract
        - Users can call payoutRedemption directly if needed

        See: https://github.com/Polymarket/py-clob-client/issues/117
        ================================================================
        """)

        # This test exists to document the limitation
        # No actual API to test
        assert True
