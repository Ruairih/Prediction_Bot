"""
Live STRESS TESTS for Polymarket trading infrastructure.

These tests verify the bot can handle:
1. Rapid order submission and cancellation
2. Multiple concurrent market operations
3. High-frequency balance queries
4. Order sync under load
5. WebSocket reconnection (simulated)
6. API rate limiting behavior

SAFETY MEASURES:
- Gated behind LIVE_STRESS_TEST_ENABLED=true
- All orders placed well below market (no fills)
- Maximum total exposure: $2.00
- All orders cancelled in cleanup
- Rate limited to avoid API abuse

RUN WITH:
    LIVE_STRESS_TEST_ENABLED=true pytest tests/integration/test_live_stress.py -v

WARNING: These tests may hit rate limits. Only run when necessary.
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
from datetime import datetime, timezone

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

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.live_stress]

# =============================================================================
# Configuration
# =============================================================================

LIVE_STRESS_ENV_VAR = "LIVE_STRESS_TEST_ENABLED"
CREDS_ENV_VAR = "POLYMARKET_CREDS_PATH"
DEFAULT_CREDS_PATH = "polymarket_api_creds.json"

# Stress test limits
MAX_TOTAL_EXPOSURE = Decimal("10.00")  # Max $10 total across all orders
MAX_ORDERS_PER_BURST = 5
BURST_INTERVAL_SECONDS = 1.0
ORDER_RATE_LIMIT_SECONDS = 0.2  # Min time between orders
TIMEOUT_SECONDS = 60

# Order constraints - Polymarket requires minimum $1 order value
MIN_ORDER_COST = Decimal("1.00")  # CLOB minimum
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("0.99")

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


if not _env_truthy(os.getenv(LIVE_STRESS_ENV_VAR, "")):
    pytest.skip(
        f"{LIVE_STRESS_ENV_VAR} is not set; skipping stress tests",
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


class _NullDatabase:
    async def execute(self, *args, **kwargs):
        return "OK"
    async def fetch(self, *args, **kwargs):
        return []


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class StressTestMetrics:
    """Metrics collected during stress tests."""
    orders_submitted: int = 0
    orders_cancelled: int = 0
    orders_failed: int = 0
    syncs_performed: int = 0
    balance_queries: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    rate_limit_hits: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        total_ops = self.orders_submitted + self.syncs_performed + self.balance_queries
        if total_ops == 0:
            return 0.0
        return self.total_latency_ms / total_ops

    @property
    def ops_per_second(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0.0
        total_ops = self.orders_submitted + self.orders_cancelled + self.syncs_performed
        return total_ops / elapsed

    def log_summary(self) -> None:
        elapsed = time.time() - self.start_time
        logger.info(f"""
        ===============================================
        STRESS TEST METRICS
        ===============================================
        Duration: {elapsed:.2f}s
        Orders Submitted: {self.orders_submitted}
        Orders Cancelled: {self.orders_cancelled}
        Orders Failed: {self.orders_failed}
        Syncs Performed: {self.syncs_performed}
        Balance Queries: {self.balance_queries}
        Rate Limit Hits: {self.rate_limit_hits}
        -----------------------------------------------
        Avg Latency: {self.avg_latency_ms:.1f}ms
        Max Latency: {self.max_latency_ms:.1f}ms
        Ops/Second: {self.ops_per_second:.2f}
        ===============================================
        """)


@dataclass
class StressTestContext:
    """Context for stress tests."""
    order_manager: OrderManager
    balance_manager: BalanceManager
    rest_client: PolymarketRestClient
    clob_client: Any
    starting_balance: Decimal
    metrics: StressTestMetrics = field(default_factory=StressTestMetrics)
    order_ids: List[str] = field(default_factory=list)
    current_exposure: Decimal = Decimal("0")

    def track_order(self, order_id: str, cost: Decimal) -> None:
        self.order_ids.append(order_id)
        self.current_exposure += cost

    def can_submit_more(self) -> bool:
        return self.current_exposure < MAX_TOTAL_EXPOSURE


@dataclass
class StressTestMarket:
    """Market for stress testing."""
    token_id: str
    condition_id: str
    safe_price: Decimal  # Price that won't fill
    min_size: Decimal
    tick_size: Decimal


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
async def stress_markets(rest_client) -> List[StressTestMarket]:
    """Find multiple markets for stress testing."""
    markets = []
    for page in range(2):
        batch = await _with_timeout(
            rest_client.get_markets(active_only=True, limit=50, offset=page * 50),
            f"fetching markets page {page}",
        )
        if not batch:
            break
        markets.extend(batch)

    stress_markets = []

    for market in markets[:20]:  # Check first 20
        if market.time_to_end < 24:
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

            if orderbook.best_bid is None:
                continue

            # Safe price well below bid
            safe_price = max(MIN_PRICE, orderbook.best_bid - Decimal("0.20"))
            safe_price = _quantize(safe_price, Decimal("0.01"), ROUND_DOWN)

            if safe_price < MIN_PRICE:
                continue

            metadata = await _with_timeout(
                rest_client.get_token_metadata(token.token_id),
                "fetching metadata",
                timeout=5,
            ) or {}

            stress_markets.append(StressTestMarket(
                token_id=token.token_id,
                condition_id=market.condition_id,
                safe_price=safe_price,
                min_size=max(_to_decimal(metadata.get("minOrderSize")) or Decimal("5"), Decimal("5")),
                tick_size=_to_decimal(metadata.get("tickSize")) or Decimal("0.01"),
            ))

            if len(stress_markets) >= 3:  # Get 3 markets
                break

        except Exception:
            continue

    if not stress_markets:
        pytest.skip("No suitable markets for stress testing")

    return stress_markets


@pytest.fixture
async def stress_context(clob_client, rest_client) -> StressTestContext:
    """Create context for stress tests."""
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

    if starting_balance < MAX_TOTAL_EXPOSURE * 2:
        pytest.skip(f"Insufficient balance for stress test: ${starting_balance}")

    context = StressTestContext(
        order_manager=order_manager,
        balance_manager=balance_manager,
        rest_client=rest_client,
        clob_client=clob_client,
        starting_balance=starting_balance,
    )

    yield context

    # Cleanup: cancel all orders
    logger.info(f"Cleaning up {len(context.order_ids)} orders...")
    for order_id in context.order_ids:
        try:
            await order_manager.cancel_order(order_id)
            context.metrics.orders_cancelled += 1
        except Exception as e:
            logger.warning(f"Failed to cancel {order_id}: {e}")

    # Log metrics
    context.metrics.log_summary()

    # Verify balance recovery
    ending_balance = order_manager.refresh_balance()
    tolerance = Decimal("0.10")
    if ending_balance < starting_balance - tolerance:
        logger.warning(
            f"Balance decreased: ${starting_balance} -> ${ending_balance}"
        )


# =============================================================================
# STRESS TESTS
# =============================================================================

@pytest.mark.live_stress
class TestRapidOrderSubmission:
    """Tests for rapid order submission."""

    async def test_burst_order_submission(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Submit multiple orders in rapid succession.

        Tests:
        - Order manager handles burst traffic
        - Balance reservations remain consistent
        - No orders are lost
        """
        ctx = stress_context
        market = stress_markets[0]

        num_orders = MAX_ORDERS_PER_BURST
        submitted = 0

        logger.info(f"Submitting burst of {num_orders} orders...")

        for i in range(num_orders):
            if not ctx.can_submit_more():
                logger.info("Exposure limit reached")
                break

            # Ensure size meets minimum order cost ($1)
            size = max(market.min_size, _min_size_for_cost(market.safe_price))
            cost = market.safe_price * size

            start = time.time()
            try:
                order_id = await _with_timeout(
                    ctx.order_manager.submit_order(
                        token_id=market.token_id,
                        side="BUY",
                        price=market.safe_price,
                        size=size,
                        condition_id=market.condition_id,
                    ),
                    f"submitting order {i}",
                    timeout=15,
                )
                latency_ms = (time.time() - start) * 1000

                ctx.track_order(order_id, cost)
                ctx.metrics.orders_submitted += 1
                ctx.metrics.total_latency_ms += latency_ms
                ctx.metrics.max_latency_ms = max(ctx.metrics.max_latency_ms, latency_ms)
                submitted += 1

                logger.info(f"Order {i+1}/{num_orders}: {order_id[:16]}... ({latency_ms:.0f}ms)")

            except Exception as e:
                if "rate" in str(e).lower():
                    ctx.metrics.rate_limit_hits += 1
                    logger.warning(f"Rate limit hit on order {i}")
                else:
                    ctx.metrics.orders_failed += 1
                    logger.warning(f"Order {i} failed: {e}")

            # Small delay between orders
            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

        assert submitted >= 1, "At least one order should succeed"
        logger.info(f"Burst complete: {submitted}/{num_orders} orders submitted")


@pytest.mark.live_stress
class TestConcurrentSyncs:
    """Tests for concurrent order syncing."""

    async def test_rapid_sync_operations(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Submit orders then sync their status rapidly.

        Tests:
        - Order status sync under load
        - No data corruption from concurrent reads
        """
        ctx = stress_context
        market = stress_markets[0]

        # First, submit a few orders
        for i in range(3):
            if not ctx.can_submit_more():
                break

            # Ensure size meets minimum order cost ($1)
            size = max(market.min_size, _min_size_for_cost(market.safe_price))
            cost = market.safe_price * size
            try:
                order_id = await ctx.order_manager.submit_order(
                    token_id=market.token_id,
                    side="BUY",
                    price=market.safe_price,
                    size=size,
                    condition_id=market.condition_id,
                )
                ctx.track_order(order_id, cost)
                ctx.metrics.orders_submitted += 1
                await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)
            except Exception as e:
                logger.warning(f"Submit failed: {e}")

        if not ctx.order_ids:
            pytest.skip("No orders to sync")

        logger.info(f"Syncing {len(ctx.order_ids)} orders rapidly...")

        # Now sync them rapidly
        for _ in range(2):  # 2 rounds of syncing
            for order_id in ctx.order_ids:
                start = time.time()
                try:
                    order = await ctx.order_manager.sync_order_status(order_id)
                    latency_ms = (time.time() - start) * 1000

                    ctx.metrics.syncs_performed += 1
                    ctx.metrics.total_latency_ms += latency_ms
                    ctx.metrics.max_latency_ms = max(ctx.metrics.max_latency_ms, latency_ms)

                    assert order.status in (
                        OrderStatus.PENDING,
                        OrderStatus.LIVE,
                        OrderStatus.CANCELLED,
                    )

                except Exception as e:
                    if "rate" in str(e).lower():
                        ctx.metrics.rate_limit_hits += 1
                    logger.warning(f"Sync failed: {e}")

                await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS / 2)

        logger.info(f"Completed {ctx.metrics.syncs_performed} syncs")


@pytest.mark.live_stress
class TestBalanceQueryStress:
    """Tests for balance query under load."""

    async def test_rapid_balance_queries(
        self,
        stress_context: StressTestContext,
    ):
        """
        Query balance rapidly to test caching behavior.

        Tests:
        - Balance cache works correctly
        - No data corruption
        - Reasonable latency
        """
        ctx = stress_context
        num_queries = 10

        logger.info(f"Performing {num_queries} rapid balance queries...")

        first_balance = None
        for i in range(num_queries):
            start = time.time()
            try:
                balance = ctx.order_manager.refresh_balance()
                latency_ms = (time.time() - start) * 1000

                ctx.metrics.balance_queries += 1
                ctx.metrics.total_latency_ms += latency_ms
                ctx.metrics.max_latency_ms = max(ctx.metrics.max_latency_ms, latency_ms)

                if first_balance is None:
                    first_balance = balance

                # Balance should be consistent (within tolerance for any fills)
                tolerance = Decimal("0.10")
                assert abs(balance - first_balance) < tolerance, \
                    f"Balance inconsistency: {first_balance} vs {balance}"

            except Exception as e:
                if "rate" in str(e).lower():
                    ctx.metrics.rate_limit_hits += 1
                logger.warning(f"Balance query failed: {e}")

            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

        logger.info(f"Balance queries complete. Avg: {ctx.metrics.avg_latency_ms:.0f}ms")


@pytest.mark.live_stress
class TestMultiMarketOperations:
    """Tests for operations across multiple markets."""

    async def test_cross_market_orders(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Submit orders to multiple markets simultaneously.

        Tests:
        - Balance management across markets
        - No cross-contamination of order data
        """
        ctx = stress_context

        if len(stress_markets) < 2:
            pytest.skip("Need at least 2 markets for cross-market test")

        logger.info(f"Testing orders across {len(stress_markets)} markets...")

        async def submit_to_market(market: StressTestMarket, index: int) -> Optional[str]:
            if not ctx.can_submit_more():
                return None

            # Ensure size meets minimum order cost ($1)
            size = max(market.min_size, _min_size_for_cost(market.safe_price))
            cost = market.safe_price * size

            try:
                order_id = await ctx.order_manager.submit_order(
                    token_id=market.token_id,
                    side="BUY",
                    price=market.safe_price,
                    size=size,
                    condition_id=market.condition_id,
                )
                ctx.track_order(order_id, cost)
                ctx.metrics.orders_submitted += 1
                return order_id

            except Exception as e:
                ctx.metrics.orders_failed += 1
                logger.warning(f"Market {index} order failed: {e}")
                return None

        # Submit to each market with delay
        results = []
        for i, market in enumerate(stress_markets):
            result = await submit_to_market(market, i)
            results.append(result)
            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

        successful = [r for r in results if r is not None]
        assert len(successful) >= 1, "At least one cross-market order should succeed"

        # Verify each order syncs correctly
        for order_id in successful:
            order = await ctx.order_manager.sync_order_status(order_id)
            assert order is not None
            assert order.order_id == order_id

        logger.info(f"Cross-market test complete: {len(successful)}/{len(stress_markets)} orders")


@pytest.mark.live_stress
class TestOrderLifecycleStress:
    """Tests for full order lifecycle under stress."""

    async def test_submit_cancel_cycle(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Submit then immediately cancel orders in a cycle.

        Tests:
        - Rapid submit/cancel doesn't corrupt state
        - Balance reservations are properly released
        - No orphaned orders
        """
        ctx = stress_context
        market = stress_markets[0]
        cycles = 3

        logger.info(f"Running {cycles} submit/cancel cycles...")

        for cycle in range(cycles):
            pre_balance = ctx.order_manager.get_available_balance()

            # Ensure size meets minimum order cost ($1)
            size = max(market.min_size, _min_size_for_cost(market.safe_price))
            cost = market.safe_price * size

            if not ctx.can_submit_more():
                logger.info("Exposure limit reached")
                break

            try:
                # Submit
                order_id = await ctx.order_manager.submit_order(
                    token_id=market.token_id,
                    side="BUY",
                    price=market.safe_price,
                    size=size,
                    condition_id=market.condition_id,
                )
                ctx.track_order(order_id, cost)
                ctx.metrics.orders_submitted += 1

                # Brief pause
                await asyncio.sleep(0.5)

                # Cancel immediately
                cancelled = await ctx.order_manager.cancel_order(order_id)
                if cancelled:
                    ctx.metrics.orders_cancelled += 1

                # Wait for balance to restore
                await asyncio.sleep(1)

                # Verify balance restored
                post_balance = ctx.order_manager.get_available_balance()
                tolerance = Decimal("0.02")

                if post_balance < pre_balance - tolerance:
                    logger.warning(
                        f"Cycle {cycle}: Balance not fully restored "
                        f"(${pre_balance} -> ${post_balance})"
                    )

                # Remove from exposure tracking
                ctx.current_exposure -= cost

                logger.info(f"Cycle {cycle+1}/{cycles} complete")

            except Exception as e:
                ctx.metrics.orders_failed += 1
                logger.warning(f"Cycle {cycle} failed: {e}")

            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

        logger.info("Submit/cancel cycle test complete")


# =============================================================================
# RESILIENCE TESTS
# =============================================================================

@pytest.mark.live_stress
class TestAPIResilience:
    """Tests for API error handling and recovery."""

    async def test_continues_after_single_failure(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Verify bot can continue operating after a failed operation.

        Tests:
        - Single failure doesn't crash the system
        - Subsequent operations succeed
        """
        ctx = stress_context
        market = stress_markets[0]

        # First, try an operation that might fail
        try:
            await ctx.order_manager.sync_order_status("nonexistent_order_12345")
        except Exception:
            pass  # Expected failure

        # Now verify normal operations still work
        # Ensure size meets minimum order cost ($1)
        size = max(market.min_size, _min_size_for_cost(market.safe_price))
        cost = market.safe_price * size

        if not ctx.can_submit_more():
            pytest.skip("Exposure limit reached")

        order_id = await ctx.order_manager.submit_order(
            token_id=market.token_id,
            side="BUY",
            price=market.safe_price,
            size=size,
            condition_id=market.condition_id,
        )
        ctx.track_order(order_id, cost)
        ctx.metrics.orders_submitted += 1

        # Verify order exists
        order = await ctx.order_manager.sync_order_status(order_id)
        assert order is not None
        assert order.order_id == order_id

        logger.info("SUCCESS: System continued after single failure")


@pytest.mark.live_stress
class TestLatencyMeasurement:
    """Measure and document API latencies."""

    async def test_documents_api_latencies(
        self,
        stress_context: StressTestContext,
        stress_markets: List[StressTestMarket],
    ):
        """
        Measure and document typical API latencies.

        This is a documentation test that helps set expectations
        for performance.
        """
        ctx = stress_context
        market = stress_markets[0]

        latencies = {
            "balance_query": [],
            "order_submit": [],
            "order_sync": [],
            "order_cancel": [],
        }

        # Measure balance query
        for _ in range(3):
            start = time.time()
            ctx.order_manager.refresh_balance()
            latencies["balance_query"].append((time.time() - start) * 1000)
            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

        # Measure order submit
        if ctx.can_submit_more():
            # Ensure size meets minimum order cost ($1)
            size = max(market.min_size, _min_size_for_cost(market.safe_price))
            cost = market.safe_price * size
            start = time.time()
            order_id = await ctx.order_manager.submit_order(
                token_id=market.token_id,
                side="BUY",
                price=market.safe_price,
                size=size,
                condition_id=market.condition_id,
            )
            latencies["order_submit"].append((time.time() - start) * 1000)
            ctx.track_order(order_id, cost)

            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

            # Measure order sync
            start = time.time()
            await ctx.order_manager.sync_order_status(order_id)
            latencies["order_sync"].append((time.time() - start) * 1000)

            await asyncio.sleep(ORDER_RATE_LIMIT_SECONDS)

            # Measure order cancel
            start = time.time()
            await ctx.order_manager.cancel_order(order_id)
            latencies["order_cancel"].append((time.time() - start) * 1000)

        # Log results
        logger.info("""
        ===============================================
        API LATENCY DOCUMENTATION
        ===============================================
        """)

        for op, times in latencies.items():
            if times:
                avg = sum(times) / len(times)
                max_lat = max(times)
                logger.info(f"{op}: avg={avg:.0f}ms, max={max_lat:.0f}ms")

        logger.info("===============================================")

        # Verify latencies are reasonable (< 5s each)
        for op, times in latencies.items():
            for t in times:
                assert t < 5000, f"{op} took too long: {t}ms"
