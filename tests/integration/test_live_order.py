"""
Live integration tests for Polymarket order lifecycle.

These tests hit real Polymarket APIs and place a tiny live order.
They are gated behind LIVE_TEST_ENABLED=true to keep them safe for CI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any, Optional

import pytest

from polymarket_bot.execution import (
    BalanceConfig,
    BalanceManager,
    Order,
    OrderConfig,
    OrderManager,
    OrderStatus,
)
from polymarket_bot.ingestion.client import PolymarketRestClient, verify_orderbook_price
from polymarket_bot.ingestion.models import Market

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.live]

LIVE_ENV_VAR = "LIVE_TEST_ENABLED"
CREDS_ENV_VAR = "POLYMARKET_CREDS_PATH"
DEFAULT_CREDS_PATH = "polymarket_api_creds.json"

MIN_ORDER_COST = Decimal("1.00")
MAX_ORDER_COST = Decimal("5.00")  # Allow higher since min cost is $1
MIN_PRICE = Decimal("0.01")
PRICE_OFFSET = Decimal("0.15")  # Larger offset to avoid accidental fills
BALANCE_TOLERANCE = Decimal("0.10")

MIN_TIME_TO_END_HOURS = 72
MARKET_PAGE_LIMIT = 100
MARKET_MAX_PAGES = 3

TIMEOUT_SECONDS = 30

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


def _env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


if not _env_truthy(os.getenv(LIVE_ENV_VAR, "")):
    pytest.skip(
        "LIVE_TEST_ENABLED is not set to true; skipping live tests",
        allow_module_level=True,
    )


def _load_creds(creds_path: Path) -> dict[str, Any]:
    if not creds_path.exists():
        raise FileNotFoundError(f"Missing credentials file: {creds_path}")

    with creds_path.open() as f:
        data = json.load(f)

    return data


def _validate_creds(creds: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_CRED_KEYS if not str(creds.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing required credential fields: {', '.join(missing)}")

    for key in REQUIRED_CRED_KEYS:
        value = str(creds.get(key, "")).strip()
        if value in PLACEHOLDER_VALUES or value.startswith("your-"):
            raise ValueError(f"Credential {key} appears to be a placeholder")


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _extract_decimal(metadata: dict[str, Any], keys: tuple[str, ...]) -> Optional[Decimal]:
    for key in keys:
        if key in metadata:
            value = _to_decimal(metadata.get(key))
            if value and value > 0:
                return value
    return None


def _quantize(value: Decimal, step: Decimal, rounding) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=rounding) * step


async def _with_timeout(coro, description: str):
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        pytest.fail(f"Timed out while {description} after {TIMEOUT_SECONDS}s")


async def _select_liquid_market(rest_client: PolymarketRestClient) -> Market:
    """Select a liquid market with high enough best_bid to place safe orders."""
    markets: list[Market] = []

    for page in range(MARKET_MAX_PAGES):
        batch = await _with_timeout(
            rest_client.get_markets(
                active_only=True,
                limit=MARKET_PAGE_LIMIT,
                offset=page * MARKET_PAGE_LIMIT,
            ),
            f"fetching markets page {page + 1}",
        )
        if not batch:
            break
        markets.extend(batch)

    if not markets:
        pytest.fail("No markets returned from Gamma API")

    # Filter by time to end and tokens
    for min_hours in (MIN_TIME_TO_END_HOURS, 24, 1):
        candidates = [
            market
            for market in markets
            if market.time_to_end >= min_hours
            and (market.yes_token or market.no_token)
        ]
        if candidates:
            # Sort by volume (most liquid first)
            sorted_candidates = sorted(
                candidates,
                key=lambda m: m.volume or Decimal("0"),
                reverse=True,
            )
            # Return first market with high enough best_bid
            # Need best_bid > PRICE_OFFSET + MIN_PRICE to place safe orders
            min_best_bid = PRICE_OFFSET + MIN_PRICE + Decimal("0.02")
            for market in sorted_candidates[:50]:  # Check top 50 by volume
                token = market.yes_token or market.no_token
                if token:
                    try:
                        orderbook = await _with_timeout(
                            rest_client.get_orderbook(token.token_id),
                            "checking orderbook",
                        )
                        if (orderbook.best_bid is not None
                            and orderbook.best_bid > min_best_bid):
                            logger.info(
                                f"Selected market {market.condition_id} "
                                f"with best_bid={orderbook.best_bid}"
                            )
                            return market
                    except Exception:
                        continue
            # If no suitable market found, skip
            pytest.skip(
                f"No market found with best_bid > {min_best_bid} for safe testing"
            )

    pytest.skip("No liquid market found with sufficient time to expiry")


def _select_token(market: Market) -> str:
    token = market.yes_token or market.no_token
    if not token:
        pytest.skip("Selected market has no tradeable tokens")
    return token.token_id


class _NullDatabase:
    async def execute(self, *args, **kwargs):
        return "OK"

    async def fetch(self, *args, **kwargs):
        return []


@dataclass
class LiveOrderParams:
    token_id: str
    condition_id: str
    price: Decimal
    size: Decimal
    order_cost: Decimal
    best_bid: Decimal
    best_ask: Optional[Decimal]


@dataclass
class LiveOrderSetup:
    order_manager: OrderManager
    balance_manager: BalanceManager
    params: LiveOrderParams
    starting_total: Decimal
    starting_available: Decimal
    order_ids: list[str] = field(default_factory=list)

    def track(self, order_id: str) -> None:
        self.order_ids.append(order_id)


@pytest.fixture
def live_creds() -> dict[str, Any]:
    creds_path = Path(os.environ.get(CREDS_ENV_VAR, DEFAULT_CREDS_PATH))
    try:
        creds = _load_creds(creds_path)
        _validate_creds(creds)
    except Exception as exc:
        pytest.fail(f"Invalid live credentials: {exc}")
    return creds


@pytest.fixture
def clob_client(live_creds):
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
    async with PolymarketRestClient(timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture
async def liquid_market(rest_client) -> Market:
    return await _select_liquid_market(rest_client)


@pytest.fixture
def live_managers(clob_client):
    db = _NullDatabase()
    balance_manager = BalanceManager(
        db=db,
        clob_client=clob_client,
        config=BalanceConfig(min_reserve=Decimal("0")),
    )
    order_manager = OrderManager(
        db=db,
        clob_client=clob_client,
        config=OrderConfig(max_price=Decimal("0.99")),
        balance_manager=balance_manager,
    )
    return order_manager, balance_manager


@pytest.fixture
async def order_params(rest_client, liquid_market) -> LiveOrderParams:
    token_id = _select_token(liquid_market)

    metadata = await _with_timeout(
        rest_client.get_token_metadata(token_id),
        "fetching token metadata",
    )
    metadata = metadata or {}

    min_size = max(
        _extract_decimal(
            metadata,
            ("minOrderSize", "min_order_size", "minSize", "min_size", "minimum_size"),
        ) or Decimal("5"),
        Decimal("5"),
    )

    tick_size = _extract_decimal(
        metadata,
        ("tickSize", "tick_size", "minPriceIncrement", "min_price_increment"),
    ) or Decimal("0.01")

    orderbook = await _with_timeout(
        rest_client.get_orderbook(token_id),
        "fetching orderbook",
    )

    if orderbook.best_bid is None:
        pytest.skip("No bids in orderbook for selected token")

    # Compute safe price well below best bid to avoid fills
    safe_price = orderbook.best_bid - PRICE_OFFSET
    if safe_price <= MIN_PRICE:
        # If we'd have to use MIN_PRICE, the order might fill immediately
        pytest.skip(
            f"Best bid {orderbook.best_bid} too low to place safe order "
            f"(need best_bid > {MIN_PRICE + PRICE_OFFSET})"
        )

    price = _quantize(safe_price, tick_size, ROUND_DOWN)
    if price <= Decimal("0"):
        pytest.skip("Computed non-positive price for selected token")

    desired_size = _quantize(MIN_ORDER_COST / price, Decimal("0.01"), ROUND_UP)
    size = _quantize(max(min_size, desired_size), Decimal("0.01"), ROUND_UP)

    order_cost = price * size
    if order_cost > MAX_ORDER_COST:
        pytest.skip(
            f"Computed order cost {order_cost} exceeds max {MAX_ORDER_COST}"
        )

    return LiveOrderParams(
        token_id=token_id,
        condition_id=liquid_market.condition_id,
        price=price,
        size=size,
        order_cost=order_cost,
        best_bid=orderbook.best_bid,
        best_ask=orderbook.best_ask,
    )


@pytest.fixture
async def live_order_setup(live_managers, order_params, rest_client) -> LiveOrderSetup:
    order_manager, balance_manager = live_managers

    starting_total = order_manager.refresh_balance()
    starting_available = order_manager.get_available_balance()

    if starting_available < order_params.order_cost:
        pytest.skip(
            f"Insufficient balance for live test: "
            f"available {starting_available}, required {order_params.order_cost}"
        )

    setup = LiveOrderSetup(
        order_manager=order_manager,
        balance_manager=balance_manager,
        params=order_params,
        starting_total=starting_total,
        starting_available=starting_available,
    )

    yield setup

    filled_orders: list[Order] = []
    open_orders: list[str] = []
    for order_id in setup.order_ids:
        order: Optional[Order] = None
        try:
            await _with_timeout(
                setup.order_manager.cancel_order(order_id),
                f"cancelling order {order_id}",
            )
        except Exception as exc:
            logger.warning("Failed to cancel order %s: %s", order_id, exc)

        # Wait for cancel to propagate
        await asyncio.sleep(2)

        # Retry sync multiple times to confirm final state
        final_status = None
        for attempt in range(3):
            try:
                order = await _with_timeout(
                    setup.order_manager.sync_order_status(order_id),
                    f"syncing order {order_id} (attempt {attempt + 1})",
                )
                final_status = order.status
                if order.status == OrderStatus.CANCELLED:
                    break
                await asyncio.sleep(1)
            except Exception as exc:
                logger.warning("Failed to sync order %s: %s", order_id, exc)
                break

        if final_status in (OrderStatus.FILLED, OrderStatus.PARTIAL):
            order = order or setup.order_manager.get_order(order_id)
            if order:
                filled_orders.append(order)
            else:
                logger.warning(
                    "Order %s filled but no order details available for cleanup",
                    order_id,
                )
        elif final_status in (OrderStatus.PENDING, OrderStatus.LIVE):
            open_orders.append(order_id)

    closed_positions: list[str] = []
    failed_position_closures: list[str] = []
    if filled_orders:
        closed_positions, failed_position_closures = await _close_filled_positions(
            setup,
            rest_client,
            filled_orders,
        )
        logger.info(
            "Position cleanup summary: closed=%s failed=%s",
            closed_positions,
            failed_position_closures,
        )

    if filled_orders:
        filled_order_ids = [order.order_id for order in filled_orders]
        if failed_position_closures:
            pytest.fail(
                "Live test orders filled unexpectedly and position cleanup failed: "
                f"filled={filled_order_ids}, failed_closures={failed_position_closures}"
            )
        pytest.fail(
            "Live test orders filled unexpectedly: "
            f"{filled_order_ids} (positions closed: {closed_positions})"
        )
    if open_orders:
        pytest.fail(f"Live test orders left open after cleanup: {open_orders}")

    if setup.balance_manager.get_active_reservations():
        pytest.fail("Balance reservations leaked after live test cleanup")

    ending_total = setup.order_manager.refresh_balance()
    ending_available = setup.order_manager.get_available_balance()

    if abs(ending_total - setup.starting_total) > BALANCE_TOLERANCE:
        pytest.fail(
            "Total balance changed after live test: "
            f"start {setup.starting_total} -> end {ending_total}"
        )

    if ending_available + BALANCE_TOLERANCE < setup.starting_available:
        pytest.fail(
            "Available balance did not recover after cleanup: "
            f"start {setup.starting_available} -> end {ending_available}"
        )


async def _submit_order(setup: LiveOrderSetup) -> str:
    params = setup.params
    order_id = await _with_timeout(
        setup.order_manager.submit_order(
            token_id=params.token_id,
            side="BUY",
            price=params.price,
            size=params.size,
            condition_id=params.condition_id,
        ),
        "submitting order",
    )
    assert order_id and str(order_id).strip()
    setup.track(order_id)
    return order_id


async def _sync_order(setup: LiveOrderSetup, order_id: str):
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            return await _with_timeout(
                setup.order_manager.sync_order_status(order_id),
                f"syncing order {order_id} (attempt {attempt + 1})",
            )
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1)
    raise last_exc if last_exc else RuntimeError("Order sync failed unexpectedly")


async def _close_filled_positions(
    setup: LiveOrderSetup,
    rest_client: PolymarketRestClient,
    filled_orders: list[Order],
) -> tuple[list[str], list[str]]:
    closed_positions: list[str] = []
    failed_positions: list[str] = []

    for filled_order in filled_orders:
        side = filled_order.side.upper()
        if side != "BUY":
            logger.warning(
                "Skipping position close for order %s with side %s",
                filled_order.order_id,
                filled_order.side,
            )
            failed_positions.append(filled_order.order_id)
            continue

        if filled_order.filled_size > 0:
            close_size = filled_order.filled_size
        else:
            close_size = filled_order.size
        if close_size <= 0:
            logger.warning(
                "Filled order %s has no size available to close",
                filled_order.order_id,
            )
            failed_positions.append(filled_order.order_id)
            continue

        token_id = filled_order.token_id or setup.params.token_id
        condition_id = filled_order.condition_id or setup.params.condition_id

        try:
            orderbook = await _with_timeout(
                rest_client.get_orderbook(token_id),
                f"fetching orderbook for close of {filled_order.order_id}",
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch orderbook for close of %s: %s",
                filled_order.order_id,
                exc,
            )
            failed_positions.append(filled_order.order_id)
            continue

        if orderbook.best_bid is None:
            logger.warning(
                "No best bid available to close filled order %s",
                filled_order.order_id,
            )
            failed_positions.append(filled_order.order_id)
            continue

        close_price = orderbook.best_bid
        try:
            close_order_id = await _with_timeout(
                setup.order_manager.submit_order(
                    token_id=token_id,
                    side="SELL",
                    price=close_price,
                    size=close_size,
                    condition_id=condition_id,
                ),
                f"submitting close order for {filled_order.order_id}",
            )
        except Exception as exc:
            logger.warning(
                "Failed to submit close SELL for %s: %s",
                filled_order.order_id,
                exc,
            )
            failed_positions.append(filled_order.order_id)
            continue

        logger.info(
            "Submitted close SELL order %s for filled order %s (size=%s price=%s)",
            close_order_id,
            filled_order.order_id,
            close_size,
            close_price,
        )

        await asyncio.sleep(2)

        close_order = None
        close_status = None
        for attempt in range(3):
            try:
                close_order = await _sync_order(setup, close_order_id)
                close_status = close_order.status
                if close_status in (
                    OrderStatus.FILLED,
                    OrderStatus.PARTIAL,
                    OrderStatus.CANCELLED,
                    OrderStatus.FAILED,
                ):
                    break
                await asyncio.sleep(1)
            except Exception as exc:
                logger.warning(
                    "Failed to sync close order %s: %s",
                    close_order_id,
                    exc,
                )
                break

        status_label = close_status.value if close_status else "unknown"
        if close_status == OrderStatus.FILLED:
            logger.info(
                "Closed position for order %s with close order %s",
                filled_order.order_id,
                close_order_id,
            )
            closed_positions.append(filled_order.order_id)
        elif close_status == OrderStatus.PARTIAL:
            logger.warning(
                "Close order %s for %s partially filled (filled_size=%s)",
                close_order_id,
                filled_order.order_id,
                close_order.filled_size if close_order else "unknown",
            )
            failed_positions.append(filled_order.order_id)
        else:
            logger.warning(
                "Close order %s for %s not filled (status=%s)",
                close_order_id,
                filled_order.order_id,
                status_label,
            )
            failed_positions.append(filled_order.order_id)

    return closed_positions, failed_positions


@pytest.mark.live
async def test_live_balance_fetch(live_managers):
    order_manager, _balance_manager = live_managers
    total = order_manager.refresh_balance()
    assert isinstance(total, Decimal)
    assert total >= Decimal("0")


@pytest.mark.live
async def test_live_order_submission(live_order_setup: LiveOrderSetup):
    params = live_order_setup.params
    pre_available = live_order_setup.order_manager.get_available_balance()

    order_id = await _submit_order(live_order_setup)

    post_available = live_order_setup.order_manager.get_available_balance()
    reserved = pre_available - post_available

    assert reserved + BALANCE_TOLERANCE >= params.order_cost
    assert live_order_setup.balance_manager.has_reservation(order_id)


@pytest.mark.live
async def test_live_order_sync(live_order_setup: LiveOrderSetup):
    order_id = await _submit_order(live_order_setup)
    order = await _sync_order(live_order_setup, order_id)

    assert order.order_id == order_id
    assert order.status in (
        OrderStatus.PENDING,
        OrderStatus.LIVE,
        OrderStatus.PARTIAL,
    )


@pytest.mark.live
async def test_live_order_cancellation(live_order_setup: LiveOrderSetup):
    pre_available = live_order_setup.order_manager.get_available_balance()
    order_id = await _submit_order(live_order_setup)

    cancelled = await _with_timeout(
        live_order_setup.order_manager.cancel_order(order_id),
        f"cancelling order {order_id}",
    )

    # Wait for cancel to propagate to CLOB
    await asyncio.sleep(2)

    # Retry sync to confirm cancellation
    order = None
    for attempt in range(5):
        order = await _sync_order(live_order_setup, order_id)
        if order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED):
            break
        logger.info(f"Cancel attempt {attempt + 1}: status={order.status}, waiting...")
        await asyncio.sleep(1)

    assert cancelled or order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED), \
        f"Cancel returned {cancelled}, but status is {order.status}"
    assert order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED), \
        f"Order still {order.status} after cancel"
    assert not live_order_setup.balance_manager.has_reservation(order_id)

    post_available = live_order_setup.order_manager.get_available_balance()
    assert post_available + BALANCE_TOLERANCE >= pre_available


@pytest.mark.live
async def test_live_orderbook_verification(rest_client, liquid_market):
    token_id = _select_token(liquid_market)

    orderbook = await _with_timeout(
        rest_client.get_orderbook(token_id),
        "fetching orderbook for verification",
    )
    if orderbook.best_bid is None:
        pytest.skip("No bids in orderbook for verification test")

    is_valid, best_bid, _reason = await _with_timeout(
        verify_orderbook_price(
            rest_client,
            token_id,
            expected_price=orderbook.best_bid,
            max_deviation=Decimal("0.05"),
        ),
        "verifying orderbook price",
    )
    assert is_valid
    assert best_bid is not None

    if orderbook.best_bid <= Decimal("0.50"):
        far_price = min(orderbook.best_bid + Decimal("0.25"), Decimal("0.99"))
    else:
        far_price = max(orderbook.best_bid - Decimal("0.25"), Decimal("0.01"))

    is_valid_far, _best_bid_far, _reason_far = await _with_timeout(
        verify_orderbook_price(
            rest_client,
            token_id,
            expected_price=far_price,
            max_deviation=Decimal("0.10"),
        ),
        "verifying divergent orderbook price",
    )
    assert not is_valid_far


@pytest.mark.live
async def test_full_order_lifecycle(live_order_setup: LiveOrderSetup):
    pre_available = live_order_setup.order_manager.get_available_balance()

    order_id = await _submit_order(live_order_setup)
    order = await _sync_order(live_order_setup, order_id)
    assert order.status in (
        OrderStatus.PENDING,
        OrderStatus.LIVE,
        OrderStatus.PARTIAL,
    )

    cancelled = await _with_timeout(
        live_order_setup.order_manager.cancel_order(order_id),
        f"cancelling order {order_id}",
    )
    order = await _sync_order(live_order_setup, order_id)
    assert cancelled or order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED)
    assert order.status in (OrderStatus.CANCELLED, OrderStatus.FAILED)

    post_available = live_order_setup.order_manager.get_available_balance()
    assert post_available + BALANCE_TOLERANCE >= pre_available
