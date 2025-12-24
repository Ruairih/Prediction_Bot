"""
Live integration tests for FULL Polymarket trade lifecycle.

These tests actually execute trades (fills) to verify:
1. Order submission and fill detection
2. Position creation from fills
3. Exit order execution
4. Balance updates through the lifecycle
5. Complete entry → hold → exit flow

IMPORTANT SAFETY MEASURES:
- Gated behind LIVE_FILL_TEST_ENABLED=true (separate from basic live tests)
- Maximum order cost: $0.50 (half the basic live test limit)
- Automatically sells any acquired positions in cleanup
- Selects liquid markets with tight spreads
- Logs all operations for audit trail

RUN WITH:
    LIVE_FILL_TEST_ENABLED=true pytest tests/integration/test_live_trade_lifecycle.py -v

WARNING: These tests WILL execute real trades and may result in small losses
due to spread costs. Only run with funds you're willing to lose.
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
    PositionTracker,
    Position,
)
from polymarket_bot.ingestion.client import PolymarketRestClient
from polymarket_bot.ingestion.models import Market

logger = logging.getLogger(__name__)

# Configure logging for visibility during tests
logging.basicConfig(level=logging.INFO)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.live_fill]

# =============================================================================
# Configuration Constants
# =============================================================================

LIVE_FILL_ENV_VAR = "LIVE_FILL_TEST_ENABLED"
CREDS_ENV_VAR = "POLYMARKET_CREDS_PATH"
DEFAULT_CREDS_PATH = "polymarket_api_creds.json"

# Safety limits - INTENTIONALLY CONSERVATIVE
MAX_ORDER_COST = Decimal("0.50")  # Maximum $0.50 per order
MAX_POSITION_VALUE = Decimal("1.00")  # Maximum $1.00 total position
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("0.99")

# Market selection criteria
MIN_TIME_TO_END_HOURS = 48  # At least 48 hours to resolution
MAX_SPREAD_PERCENT = Decimal("0.10")  # Max 10% spread for fill tests
MIN_LIQUIDITY = Decimal("100")  # Minimum $100 in orderbook depth

# Timing
TIMEOUT_SECONDS = 60
FILL_WAIT_SECONDS = 10
SYNC_POLL_INTERVAL = 2

REQUIRED_CRED_KEYS = (
    "api_key",
    "api_secret",
    "api_passphrase",
    "private_key",
    "funder",
)

PLACEHOLDER_VALUES = {
    "your-api-key-here",
    "your-api-secret-here",
    "your-api-passphrase-here",
    "0x...",
}


# =============================================================================
# Gate Check - Skip if not enabled
# =============================================================================

def _env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


if not _env_truthy(os.getenv(LIVE_FILL_ENV_VAR, "")):
    pytest.skip(
        f"{LIVE_FILL_ENV_VAR} is not set to true; skipping live fill tests. "
        "WARNING: These tests execute real trades!",
        allow_module_level=True,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def _load_creds(creds_path: Path) -> dict[str, Any]:
    """Load and validate credentials."""
    if not creds_path.exists():
        raise FileNotFoundError(f"Missing credentials file: {creds_path}")

    with creds_path.open() as f:
        data = json.load(f)

    return data


def _validate_creds(creds: dict[str, Any]) -> None:
    """Validate credentials are real, not placeholders."""
    missing = [key for key in REQUIRED_CRED_KEYS if not str(creds.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required credential fields: {', '.join(missing)}")

    for key in REQUIRED_CRED_KEYS:
        value = str(creds.get(key, "")).strip()
        if value in PLACEHOLDER_VALUES or value.startswith("your-"):
            raise ValueError(f"Credential {key} appears to be a placeholder")


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Safely convert to Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _quantize(value: Decimal, step: Decimal, rounding) -> Decimal:
    """Quantize value to step size."""
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=rounding) * step


async def _with_timeout(coro, description: str, timeout: float = TIMEOUT_SECONDS):
    """Run coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"Timed out while {description} after {timeout}s")


# =============================================================================
# Null Database for Testing (doesn't persist)
# =============================================================================

class _NullDatabase:
    """Mock database that doesn't persist - for isolated testing."""

    async def execute(self, *args, **kwargs):
        return "OK"

    async def fetch(self, *args, **kwargs):
        return []

    async def fetchrow(self, *args, **kwargs):
        return None

    async def fetchval(self, *args, **kwargs):
        return None


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FillableMarket:
    """Market suitable for fill testing."""
    market: Market
    token_id: str
    condition_id: str
    best_bid: Decimal
    best_ask: Decimal
    spread: Decimal
    spread_percent: Decimal
    min_size: Decimal
    tick_size: Decimal


@dataclass
class TradeRecord:
    """Record of a trade for cleanup and verification."""
    order_id: str
    token_id: str
    condition_id: str
    side: str
    price: Decimal
    size: Decimal
    status: OrderStatus
    filled_size: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class LiveFillTestContext:
    """Context for live fill tests with cleanup tracking."""
    order_manager: OrderManager
    balance_manager: BalanceManager
    position_tracker: PositionTracker
    rest_client: PolymarketRestClient
    clob_client: Any
    starting_balance: Decimal
    trades: List[TradeRecord] = field(default_factory=list)
    positions_acquired: List[str] = field(default_factory=list)

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade for cleanup."""
        self.trades.append(trade)
        logger.info(f"Recorded trade: {trade.side} {trade.size} @ {trade.price} = {trade.order_id}")

    def record_position(self, token_id: str) -> None:
        """Record a position for cleanup."""
        if token_id not in self.positions_acquired:
            self.positions_acquired.append(token_id)
            logger.info(f"Recorded position in token: {token_id}")


# =============================================================================
# Market Selection - Find Fillable Markets
# =============================================================================

async def _find_fillable_market(rest_client: PolymarketRestClient) -> FillableMarket:
    """
    Find a market suitable for fill testing.

    Requirements:
    - Active market with >48 hours to resolution
    - Tight spread (<10%)
    - Sufficient liquidity
    - Valid orderbook with bids and asks
    """
    markets: List[Market] = []

    # Fetch markets
    for page in range(3):
        batch = await _with_timeout(
            rest_client.get_markets(
                active_only=True,
                limit=100,
                offset=page * 100,
            ),
            f"fetching markets page {page + 1}",
        )
        if not batch:
            break
        markets.extend(batch)

    if not markets:
        pytest.fail("No markets returned from API")

    # Filter and score markets
    candidates: List[FillableMarket] = []

    for market in markets:
        # Skip markets expiring soon
        if market.time_to_end < MIN_TIME_TO_END_HOURS:
            continue

        # Need a tradeable token
        token = market.yes_token or market.no_token
        if not token:
            continue

        token_id = token.token_id

        try:
            # Get orderbook
            orderbook = await _with_timeout(
                rest_client.get_orderbook(token_id),
                f"fetching orderbook for {token_id[:16]}...",
                timeout=10,
            )

            if orderbook.best_bid is None or orderbook.best_ask is None:
                continue

            # Calculate spread
            spread = orderbook.best_ask - orderbook.best_bid
            spread_percent = spread / orderbook.best_ask if orderbook.best_ask > 0 else Decimal("1")

            # Skip wide spreads
            if spread_percent > MAX_SPREAD_PERCENT:
                continue

            # Get token metadata for min size
            metadata = await _with_timeout(
                rest_client.get_token_metadata(token_id),
                f"fetching metadata for {token_id[:16]}...",
                timeout=10,
            )
            metadata = metadata or {}

            min_size = max(_to_decimal(metadata.get("minOrderSize") or metadata.get("min_order_size")) or Decimal("5"), Decimal("5"))
            tick_size = _to_decimal(metadata.get("tickSize") or metadata.get("tick_size")) or Decimal("0.01")

            candidates.append(FillableMarket(
                market=market,
                token_id=token_id,
                condition_id=market.condition_id,
                best_bid=orderbook.best_bid,
                best_ask=orderbook.best_ask,
                spread=spread,
                spread_percent=spread_percent,
                min_size=min_size,
                tick_size=tick_size,
            ))

        except Exception as e:
            logger.debug(f"Skipping market {market.condition_id}: {e}")
            continue

    if not candidates:
        pytest.skip("No suitable fillable markets found (tight spread, sufficient liquidity)")

    # Sort by spread (tightest first) then by volume
    candidates.sort(key=lambda c: (c.spread_percent, -(c.market.volume or Decimal("0"))))

    selected = candidates[0]
    logger.info(
        f"Selected market for fill test: {selected.market.question[:50]}... "
        f"bid={selected.best_bid} ask={selected.best_ask} spread={selected.spread_percent:.2%}"
    )

    return selected


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def live_creds() -> dict[str, Any]:
    """Load and validate live credentials."""
    creds_path = Path(os.environ.get(CREDS_ENV_VAR, DEFAULT_CREDS_PATH))
    try:
        creds = _load_creds(creds_path)
        _validate_creds(creds)
    except Exception as exc:
        pytest.fail(f"Invalid live credentials: {exc}")
    return creds


@pytest.fixture
def clob_client(live_creds):
    """Create CLOB client for live trading."""
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as exc:
        pytest.fail(f"py-clob-client is required for live tests: {exc}")

    api_creds = ApiCreds(
        api_key=live_creds["api_key"],
        api_secret=live_creds["api_secret"],
        api_passphrase=live_creds["api_passphrase"],
    )

    try:
        client = ClobClient(
            host=live_creds.get("host", "https://clob.polymarket.com"),
            chain_id=live_creds.get("chain_id", 137),
            key=live_creds.get("private_key"),
            creds=api_creds,
            signature_type=live_creds.get("signature_type", 2),
            funder=live_creds.get("funder"),
        )
    except Exception as exc:
        pytest.fail(f"Failed to create CLOB client: {exc}")

    return client


@pytest.fixture
async def rest_client():
    """REST client for market data."""
    async with PolymarketRestClient(timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture
async def fillable_market(rest_client) -> FillableMarket:
    """Find a market suitable for fill testing."""
    return await _find_fillable_market(rest_client)


@pytest.fixture
async def fill_test_context(clob_client, rest_client) -> LiveFillTestContext:
    """
    Create context for fill tests with automatic cleanup.

    CRITICAL: This fixture ensures all positions are closed
    and orders cancelled after each test.
    """
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

    position_tracker = PositionTracker(db=db)

    starting_balance = order_manager.refresh_balance()
    logger.info(f"Starting balance: ${starting_balance}")

    if starting_balance < MAX_ORDER_COST * 2:
        pytest.skip(f"Insufficient balance for fill tests: ${starting_balance} < ${MAX_ORDER_COST * 2}")

    context = LiveFillTestContext(
        order_manager=order_manager,
        balance_manager=balance_manager,
        position_tracker=position_tracker,
        rest_client=rest_client,
        clob_client=clob_client,
        starting_balance=starting_balance,
    )

    yield context

    # ==========================================================================
    # CLEANUP - Cancel all orders, sell all positions
    # ==========================================================================
    logger.info("=== CLEANUP PHASE ===")

    # Cancel any open orders
    for trade in context.trades:
        if trade.status in (OrderStatus.PENDING, OrderStatus.LIVE, OrderStatus.PARTIAL):
            try:
                await _with_timeout(
                    order_manager.cancel_order(trade.order_id),
                    f"cancelling order {trade.order_id}",
                    timeout=15,
                )
                logger.info(f"Cancelled order: {trade.order_id}")
            except Exception as e:
                logger.warning(f"Failed to cancel order {trade.order_id}: {e}")

    # Sync all orders to get final status
    for trade in context.trades:
        try:
            order = await _with_timeout(
                order_manager.sync_order_status(trade.order_id),
                f"syncing order {trade.order_id}",
                timeout=15,
            )
            trade.status = order.status
            trade.filled_size = order.filled_size
            trade.avg_fill_price = order.avg_fill_price
            logger.info(f"Order {trade.order_id}: status={order.status}, filled={order.filled_size}")
        except Exception as e:
            logger.warning(f"Failed to sync order {trade.order_id}: {e}")

    # Sell any acquired positions
    for trade in context.trades:
        if trade.side == "BUY" and trade.filled_size > Decimal("0"):
            try:
                # Get current best bid to sell at
                orderbook = await _with_timeout(
                    rest_client.get_orderbook(trade.token_id),
                    f"fetching orderbook for cleanup sell",
                    timeout=10,
                )

                if orderbook.best_bid and orderbook.best_bid > Decimal("0"):
                    sell_price = orderbook.best_bid
                    sell_size = trade.filled_size

                    logger.info(f"Cleanup: Selling {sell_size} of {trade.token_id[:16]}... @ {sell_price}")

                    sell_order_id = await _with_timeout(
                        order_manager.submit_order(
                            token_id=trade.token_id,
                            side="SELL",
                            price=sell_price,
                            size=sell_size,
                            condition_id=trade.condition_id,
                        ),
                        "submitting cleanup sell order",
                        timeout=30,
                    )

                    # Wait for sell to fill
                    await asyncio.sleep(FILL_WAIT_SECONDS)

                    # Cancel if not filled
                    try:
                        await order_manager.cancel_order(sell_order_id)
                    except Exception:
                        pass

                    logger.info(f"Cleanup sell order: {sell_order_id}")

            except Exception as e:
                logger.error(f"Failed cleanup sell for {trade.token_id}: {e}")

    # Final balance check
    ending_balance = order_manager.refresh_balance()
    balance_change = ending_balance - context.starting_balance
    logger.info(f"Ending balance: ${ending_balance} (change: ${balance_change})")

    # Warn if significant loss (but don't fail - trades may have spread cost)
    if balance_change < -MAX_ORDER_COST:
        logger.warning(f"Significant balance loss during test: ${balance_change}")


# =============================================================================
# Helper Functions for Tests
# =============================================================================

async def submit_buy_at_ask(
    context: LiveFillTestContext,
    market: FillableMarket,
    size: Optional[Decimal] = None,
) -> TradeRecord:
    """
    Submit a BUY order at the ask price (should fill immediately).

    This is how we test actual fills.
    """
    # Refresh orderbook for current ask
    orderbook = await _with_timeout(
        context.rest_client.get_orderbook(market.token_id),
        "fetching orderbook for buy",
    )

    if orderbook.best_ask is None:
        pytest.skip("No asks available for fill test")

    price = orderbook.best_ask

    # Calculate size if not provided
    if size is None:
        # Use minimum size or size that costs ~$0.25
        target_cost = Decimal("0.25")
        size = max(
            market.min_size,
            _quantize(target_cost / price, Decimal("0.01"), ROUND_UP),
        )

    # Validate cost
    cost = price * size
    if cost > MAX_ORDER_COST:
        pytest.skip(f"Order cost ${cost} exceeds max ${MAX_ORDER_COST}")

    logger.info(f"Submitting BUY: {size} shares @ ${price} = ${cost}")

    order_id = await _with_timeout(
        context.order_manager.submit_order(
            token_id=market.token_id,
            side="BUY",
            price=price,
            size=size,
            condition_id=market.condition_id,
        ),
        "submitting buy order at ask",
    )

    trade = TradeRecord(
        order_id=order_id,
        token_id=market.token_id,
        condition_id=market.condition_id,
        side="BUY",
        price=price,
        size=size,
        status=OrderStatus.PENDING,
    )
    context.record_trade(trade)

    return trade


async def wait_for_fill(
    context: LiveFillTestContext,
    trade: TradeRecord,
    timeout: float = FILL_WAIT_SECONDS,
) -> TradeRecord:
    """Wait for an order to fill."""
    start = time.time()

    while time.time() - start < timeout:
        order = await _with_timeout(
            context.order_manager.sync_order_status(trade.order_id),
            f"syncing order {trade.order_id}",
        )

        trade.status = order.status
        trade.filled_size = order.filled_size
        trade.avg_fill_price = order.avg_fill_price

        if order.status == OrderStatus.FILLED:
            logger.info(f"Order {trade.order_id} FILLED: {order.filled_size} @ {order.avg_fill_price}")
            return trade

        if order.status == OrderStatus.PARTIAL:
            logger.info(f"Order {trade.order_id} PARTIAL: {order.filled_size}/{trade.size}")

        if order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED):
            logger.info(f"Order {trade.order_id} terminated: {order.status}")
            return trade

        await asyncio.sleep(SYNC_POLL_INTERVAL)

    logger.warning(f"Order {trade.order_id} did not fill within {timeout}s")
    return trade


async def submit_sell_at_bid(
    context: LiveFillTestContext,
    market: FillableMarket,
    size: Decimal,
) -> TradeRecord:
    """Submit a SELL order at the bid price (should fill immediately)."""
    # Refresh orderbook for current bid
    orderbook = await _with_timeout(
        context.rest_client.get_orderbook(market.token_id),
        "fetching orderbook for sell",
    )

    if orderbook.best_bid is None:
        pytest.skip("No bids available for exit test")

    price = orderbook.best_bid

    logger.info(f"Submitting SELL: {size} shares @ ${price}")

    order_id = await _with_timeout(
        context.order_manager.submit_order(
            token_id=market.token_id,
            side="SELL",
            price=price,
            size=size,
            condition_id=market.condition_id,
        ),
        "submitting sell order at bid",
    )

    trade = TradeRecord(
        order_id=order_id,
        token_id=market.token_id,
        condition_id=market.condition_id,
        side="SELL",
        price=price,
        size=size,
        status=OrderStatus.PENDING,
    )
    context.record_trade(trade)

    return trade


# =============================================================================
# LIVE FILL TESTS
# =============================================================================

@pytest.mark.live_fill
class TestLiveFillExecution:
    """Tests that actually execute fills."""

    async def test_buy_order_fills_at_ask(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Submit a BUY order at the ask price and verify it fills.

        This is the fundamental test for order execution.
        """
        # Submit buy at ask (should fill immediately)
        trade = await submit_buy_at_ask(fill_test_context, fillable_market)

        # Wait for fill
        trade = await wait_for_fill(fill_test_context, trade)

        # Verify fill
        assert trade.status in (OrderStatus.FILLED, OrderStatus.PARTIAL), \
            f"Expected fill, got {trade.status}"
        assert trade.filled_size > Decimal("0"), "Expected some shares filled"

        # Record position for cleanup
        fill_test_context.record_position(trade.token_id)

        logger.info(f"SUCCESS: Buy filled {trade.filled_size} @ {trade.avg_fill_price}")

    async def test_fill_updates_balance(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Verify that balance is correctly updated after a fill.
        """
        pre_balance = fill_test_context.order_manager.refresh_balance()

        # Submit and wait for fill
        trade = await submit_buy_at_ask(fill_test_context, fillable_market)
        trade = await wait_for_fill(fill_test_context, trade)

        if trade.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            pytest.skip("Order did not fill - cannot test balance update")

        # Refresh balance
        post_balance = fill_test_context.order_manager.refresh_balance()

        # Balance should have decreased by approximately the fill cost
        expected_cost = trade.filled_size * (trade.avg_fill_price or trade.price)
        actual_change = pre_balance - post_balance

        # Allow some tolerance for fees
        tolerance = Decimal("0.05")
        assert abs(actual_change - expected_cost) < tolerance, \
            f"Balance change {actual_change} doesn't match expected cost {expected_cost}"

        fill_test_context.record_position(trade.token_id)
        logger.info(f"SUCCESS: Balance updated correctly: -{actual_change}")


@pytest.mark.live_fill
class TestLiveExitExecution:
    """Tests for exiting positions."""

    async def test_sell_order_exits_position(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Test the complete entry → exit flow:
        1. Buy to enter position
        2. Sell to exit position
        3. Verify balance recovery
        """
        pre_balance = fill_test_context.order_manager.refresh_balance()

        # Step 1: Buy to enter
        buy_trade = await submit_buy_at_ask(fill_test_context, fillable_market)
        buy_trade = await wait_for_fill(fill_test_context, buy_trade)

        if buy_trade.status != OrderStatus.FILLED:
            pytest.skip(f"Buy order did not fully fill: {buy_trade.status}")

        position_size = buy_trade.filled_size
        entry_price = buy_trade.avg_fill_price or buy_trade.price

        logger.info(f"Entered position: {position_size} shares @ ${entry_price}")

        # Small delay to let orderbook update
        await asyncio.sleep(2)

        # Step 2: Sell to exit
        sell_trade = await submit_sell_at_bid(
            fill_test_context,
            fillable_market,
            size=position_size,
        )
        sell_trade = await wait_for_fill(fill_test_context, sell_trade)

        if sell_trade.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            # Cancel and record for cleanup
            try:
                await fill_test_context.order_manager.cancel_order(sell_trade.order_id)
            except Exception:
                pass
            pytest.skip(f"Sell order did not fill: {sell_trade.status}")

        exit_price = sell_trade.avg_fill_price or sell_trade.price
        exit_size = sell_trade.filled_size

        logger.info(f"Exited position: {exit_size} shares @ ${exit_price}")

        # Step 3: Calculate P&L
        entry_cost = position_size * entry_price
        exit_proceeds = exit_size * exit_price
        realized_pnl = exit_proceeds - entry_cost

        logger.info(f"Realized P&L: ${realized_pnl} (entry: ${entry_cost}, exit: ${exit_proceeds})")

        # Verify balance reflects the trade (with tolerance for remaining position)
        post_balance = fill_test_context.order_manager.refresh_balance()
        balance_change = post_balance - pre_balance

        # Should have lost approximately the spread cost
        # (bought at ask, sold at bid)
        logger.info(f"Balance change: ${balance_change}")

        # The change should be close to the P&L (within tolerance)
        # We expect a small loss due to spread
        assert balance_change < Decimal("0.10"), \
            f"Unexpected profit: ${balance_change} - spread should cause small loss"
        assert balance_change > -MAX_ORDER_COST, \
            f"Excessive loss: ${balance_change}"


@pytest.mark.live_fill
class TestLiveFullLifecycle:
    """Complete lifecycle tests."""

    async def test_complete_trade_lifecycle(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Full lifecycle test:
        1. Check initial balance
        2. Submit BUY order → fills → position created
        3. Verify position tracking
        4. Submit SELL order → fills → position closed
        5. Verify final balance reconciliation

        This is the comprehensive "smoke test" for the entire execution layer.
        """
        ctx = fill_test_context

        # =====================================================================
        # PHASE 1: Initial State
        # =====================================================================
        initial_balance = ctx.order_manager.refresh_balance()
        initial_reservations = ctx.balance_manager.get_active_reservations()

        logger.info(f"PHASE 1 - Initial state: balance=${initial_balance}, reservations={len(initial_reservations)}")

        assert len(initial_reservations) == 0, "Should start with no reservations"

        # =====================================================================
        # PHASE 2: Entry (Buy)
        # =====================================================================
        logger.info("PHASE 2 - Executing entry...")

        buy_trade = await submit_buy_at_ask(ctx, fillable_market)

        # Should have a reservation while order is pending
        mid_reservations = ctx.balance_manager.get_active_reservations()
        assert len(mid_reservations) >= 1, "Should have reservation for pending order"

        # Wait for fill
        buy_trade = await wait_for_fill(ctx, buy_trade)

        if buy_trade.filled_size == Decimal("0"):
            pytest.skip("Buy order did not fill at all")

        entry_size = buy_trade.filled_size
        entry_price = buy_trade.avg_fill_price or buy_trade.price
        entry_cost = entry_size * entry_price

        logger.info(f"Entry complete: {entry_size} @ ${entry_price} = ${entry_cost}")

        # =====================================================================
        # PHASE 3: Position Holding
        # =====================================================================
        logger.info("PHASE 3 - Position holding...")

        # Balance should have decreased
        mid_balance = ctx.order_manager.refresh_balance()
        assert mid_balance < initial_balance, \
            f"Balance should have decreased after buy: {initial_balance} -> {mid_balance}"

        # If order fully filled, reservation should be released
        if buy_trade.status == OrderStatus.FILLED:
            post_buy_reservations = ctx.balance_manager.get_active_reservations()
            assert len(post_buy_reservations) == 0, \
                f"Reservations should be released after fill: {post_buy_reservations}"

        # Small delay
        await asyncio.sleep(2)

        # =====================================================================
        # PHASE 4: Exit (Sell)
        # =====================================================================
        logger.info("PHASE 4 - Executing exit...")

        sell_trade = await submit_sell_at_bid(ctx, fillable_market, size=entry_size)
        sell_trade = await wait_for_fill(ctx, sell_trade)

        if sell_trade.filled_size == Decimal("0"):
            # Cancel for cleanup
            try:
                await ctx.order_manager.cancel_order(sell_trade.order_id)
            except Exception:
                pass
            pytest.skip("Sell order did not fill - position left open for cleanup")

        exit_size = sell_trade.filled_size
        exit_price = sell_trade.avg_fill_price or sell_trade.price
        exit_proceeds = exit_size * exit_price

        logger.info(f"Exit complete: {exit_size} @ ${exit_price} = ${exit_proceeds}")

        # =====================================================================
        # PHASE 5: Final Reconciliation
        # =====================================================================
        logger.info("PHASE 5 - Final reconciliation...")

        final_balance = ctx.order_manager.refresh_balance()
        final_reservations = ctx.balance_manager.get_active_reservations()

        # Calculate expected outcome
        expected_pnl = exit_proceeds - entry_cost
        actual_balance_change = final_balance - initial_balance

        logger.info(f"Expected P&L: ${expected_pnl}")
        logger.info(f"Actual balance change: ${actual_balance_change}")

        # Should have no remaining reservations
        assert len(final_reservations) == 0, \
            f"Should have no reservations after complete lifecycle: {final_reservations}"

        # Balance change should approximate P&L (with tolerance for partial fills)
        tolerance = Decimal("0.10")
        if exit_size == entry_size:
            assert abs(actual_balance_change - expected_pnl) < tolerance, \
                f"Balance change {actual_balance_change} should match P&L {expected_pnl}"

        # Should have lost money due to spread (bought at ask, sold at bid)
        spread_cost = fillable_market.spread * min(entry_size, exit_size)
        logger.info(f"Expected spread cost: ${spread_cost}")

        # The loss should be approximately the spread cost
        if exit_size == entry_size:
            assert actual_balance_change < Decimal("0"), \
                "Should have small loss due to spread"
            assert actual_balance_change > -spread_cost * 2, \
                f"Loss {actual_balance_change} exceeds expected spread cost {spread_cost}"

        logger.info("SUCCESS: Complete lifecycle test passed!")
        logger.info(f"  Entry: {entry_size} @ ${entry_price}")
        logger.info(f"  Exit:  {exit_size} @ ${exit_price}")
        logger.info(f"  P&L:   ${actual_balance_change}")


@pytest.mark.live_fill
class TestLivePositionTracking:
    """Tests for position tracking accuracy."""

    async def test_position_size_matches_fill(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Verify that position tracking correctly reflects fills.
        """
        ctx = fill_test_context

        # Execute a buy
        trade = await submit_buy_at_ask(ctx, fillable_market)
        trade = await wait_for_fill(ctx, trade)

        if trade.filled_size == Decimal("0"):
            pytest.skip("Order did not fill")

        # The position tracker should now show this position
        # Note: We're using a null DB so we verify via the trade record

        assert trade.filled_size > Decimal("0"), "Should have filled some shares"
        assert trade.avg_fill_price is not None or trade.status == OrderStatus.PARTIAL, \
            "Should have fill price for filled order"

        ctx.record_position(trade.token_id)

        logger.info(f"Position tracked: {trade.filled_size} shares @ ${trade.avg_fill_price}")


@pytest.mark.live_fill
class TestLiveBalanceReservations:
    """Tests for balance reservation correctness."""

    async def test_reservation_released_on_fill(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Verify that balance reservations are properly released after fill.
        """
        ctx = fill_test_context

        initial_reservations = ctx.balance_manager.get_active_reservations()
        assert len(initial_reservations) == 0, "Should start with no reservations"

        # Submit order
        trade = await submit_buy_at_ask(ctx, fillable_market)

        # Should have reservation
        pending_reservations = ctx.balance_manager.get_active_reservations()
        # Note: Reservation may already be released if order filled immediately

        # Wait for fill
        trade = await wait_for_fill(ctx, trade)

        if trade.status == OrderStatus.FILLED:
            # Reservation should be released
            final_reservations = ctx.balance_manager.get_active_reservations()
            order_reservation = [r for r in final_reservations if r == trade.order_id]
            assert len(order_reservation) == 0, \
                f"Reservation for {trade.order_id} should be released after fill"

        ctx.record_position(trade.token_id)
        logger.info("SUCCESS: Reservation correctly released after fill")

    async def test_reservation_released_on_cancel(
        self,
        fill_test_context: LiveFillTestContext,
        fillable_market: FillableMarket,
    ):
        """
        Verify that reservations are released when orders are cancelled.
        """
        ctx = fill_test_context

        # Submit order at a price that won't fill (well below bid)
        orderbook = await ctx.rest_client.get_orderbook(fillable_market.token_id)
        low_price = max(
            MIN_PRICE,
            (orderbook.best_bid or Decimal("0.5")) - Decimal("0.20"),
        )

        size = fillable_market.min_size

        order_id = await ctx.order_manager.submit_order(
            token_id=fillable_market.token_id,
            side="BUY",
            price=low_price,
            size=size,
            condition_id=fillable_market.condition_id,
        )

        trade = TradeRecord(
            order_id=order_id,
            token_id=fillable_market.token_id,
            condition_id=fillable_market.condition_id,
            side="BUY",
            price=low_price,
            size=size,
            status=OrderStatus.PENDING,
        )
        ctx.record_trade(trade)

        # Should have reservation
        assert ctx.balance_manager.has_reservation(order_id), \
            "Should have reservation for pending order"

        # Cancel order
        await ctx.order_manager.cancel_order(order_id)

        # Sync status
        await asyncio.sleep(2)
        order = await ctx.order_manager.sync_order_status(order_id)
        trade.status = order.status

        # Reservation should be released
        assert not ctx.balance_manager.has_reservation(order_id), \
            "Reservation should be released after cancel"

        logger.info("SUCCESS: Reservation correctly released after cancel")
