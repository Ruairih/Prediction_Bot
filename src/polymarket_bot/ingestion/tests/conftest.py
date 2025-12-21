"""
Test fixtures for ingestion layer.

IMPORTANT: All external API calls must be mocked.
Never hit real Polymarket APIs in tests.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from polymarket_bot.ingestion.client import PolymarketRestClient
from polymarket_bot.ingestion.metrics import MetricsCollector
from polymarket_bot.ingestion.models import (
    Market,
    OrderbookLevel,
    OrderbookSnapshot,
    OutcomeType,
    PriceUpdate,
    TokenInfo,
    Trade,
    TradeSide,
)
from polymarket_bot.ingestion.processor import EventProcessor, ProcessorConfig


# =============================================================================
# Time Fixtures
# =============================================================================


@pytest.fixture
def now():
    """Current time in UTC."""
    return datetime.now(timezone.utc)


@pytest.fixture
def now_timestamp():
    """Current Unix timestamp."""
    return time.time()


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_price_update(now):
    """A valid price update."""
    return PriceUpdate(
        token_id="0x1234567890abcdef",
        price=Decimal("0.75"),
        timestamp=now,
        condition_id="condition_123",
        market_slug="will-btc-hit-100k",
    )


@pytest.fixture
def sample_trade(now):
    """A valid fresh trade."""
    return Trade(
        id="trade_001",
        token_id="0x1234567890abcdef",
        price=Decimal("0.75"),
        size=Decimal("100"),
        side=TradeSide.BUY,
        timestamp=now,
        condition_id="condition_123",
    )


@pytest.fixture
def stale_trade():
    """
    A stale trade (60 days old).

    G1 REGRESSION TEST: This should be filtered out.
    """
    stale_time = datetime.fromtimestamp(
        time.time() - 86400 * 60,  # 60 days ago
        tz=timezone.utc,
    )
    return Trade(
        id="trade_stale",
        token_id="0x1234567890abcdef",
        price=Decimal("0.95"),
        size=Decimal("4.2"),
        side=TradeSide.BUY,
        timestamp=stale_time,
        condition_id="condition_123",
    )


@pytest.fixture
def sample_market(now):
    """A sample market."""
    return Market(
        condition_id="condition_123",
        question="Will BTC hit $100k by end of 2024?",
        slug="will-btc-hit-100k",
        end_date=datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        tokens=[
            TokenInfo(
                token_id="0xyes123",
                outcome=OutcomeType.YES,
                price=Decimal("0.75"),
            ),
            TokenInfo(
                token_id="0xno456",
                outcome=OutcomeType.NO,
                price=Decimal("0.25"),
            ),
        ],
        active=True,
        category="Crypto",
        volume=Decimal("1000000"),
    )


@pytest.fixture
def sample_orderbook(now):
    """A normal orderbook."""
    return OrderbookSnapshot(
        token_id="0x1234567890abcdef",
        bids=[
            OrderbookLevel(price=Decimal("0.74"), size=Decimal("500")),
            OrderbookLevel(price=Decimal("0.73"), size=Decimal("1000")),
        ],
        asks=[
            OrderbookLevel(price=Decimal("0.76"), size=Decimal("400")),
            OrderbookLevel(price=Decimal("0.77"), size=Decimal("800")),
        ],
        timestamp=now,
    )


@pytest.fixture
def divergent_orderbook(now):
    """
    An orderbook with price far from expected.

    G5 REGRESSION TEST: Should detect divergence from 0.95 trigger.
    """
    return OrderbookSnapshot(
        token_id="0x1234567890abcdef",
        bids=[
            OrderbookLevel(price=Decimal("0.05"), size=Decimal("1000")),
        ],
        asks=[
            OrderbookLevel(price=Decimal("0.06"), size=Decimal("1000")),
        ],
        timestamp=now,
    )


# =============================================================================
# API Response Fixtures
# =============================================================================


@pytest.fixture
def sample_trades_response(now_timestamp):
    """
    Trades API response with both fresh and stale trades.

    G1 REGRESSION TEST: The stale trade should be filtered.
    """
    return [
        # Fresh trade (10 seconds ago)
        {
            "id": "trade_fresh",
            "price": "0.75",
            "size": "100",
            "side": "BUY",
            "timestamp": int((now_timestamp - 10) * 1000),
        },
        # Stale trade (60 days ago)
        {
            "id": "trade_stale",
            "price": "0.95",
            "size": "4.2",
            "side": "BUY",
            "timestamp": int((now_timestamp - 86400 * 60) * 1000),
        },
    ]


@pytest.fixture
def sample_orderbook_response():
    """Orderbook API response."""
    return {
        "bids": [
            {"price": "0.74", "size": "500"},
            {"price": "0.73", "size": "1000"},
        ],
        "asks": [
            {"price": "0.76", "size": "400"},
            {"price": "0.77", "size": "800"},
        ],
    }


@pytest.fixture
def divergent_orderbook_response():
    """
    Orderbook API response with low prices.

    G5 REGRESSION TEST: Orderbook at 5c when trigger is 95c.
    """
    return {
        "bids": [
            {"price": "0.05", "size": "1000"},
        ],
        "asks": [
            {"price": "0.06", "size": "1000"},
        ],
    }


@pytest.fixture
def sample_markets_response():
    """Markets API response."""
    return [
        {
            "condition_id": "condition_123",
            "question": "Will BTC hit $100k?",
            "slug": "will-btc-hit-100k",
            "end_date_iso": "2024-12-31T23:59:59Z",
            "tokens": [
                {"token_id": "0xyes123", "outcome": "Yes", "price": "0.75"},
                {"token_id": "0xno456", "outcome": "No", "price": "0.25"},
            ],
            "active": True,
            "category": "Crypto",
            "volume": "1000000",
        }
    ]


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_rest_client(
    sample_trades_response,
    sample_orderbook_response,
    sample_markets_response,
):
    """Mock REST client with canned responses."""
    client = AsyncMock(spec=PolymarketRestClient)

    # Mock get_trades - returns parsed Trade objects
    async def mock_get_trades(token_id, max_age_seconds=300, limit=100):
        now = time.time()
        cutoff = now - max_age_seconds
        trades = []
        for item in sample_trades_response:
            ts = item["timestamp"] / 1000
            if ts >= cutoff:
                trades.append(Trade(
                    id=item["id"],
                    token_id=token_id,
                    price=Decimal(item["price"]),
                    size=Decimal(item["size"]),
                    side=TradeSide.BUY,
                    timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                ))
        return trades

    client.get_trades = mock_get_trades

    # Mock get_orderbook
    async def mock_get_orderbook(token_id):
        return OrderbookSnapshot(
            token_id=token_id,
            bids=[
                OrderbookLevel(
                    price=Decimal(b["price"]),
                    size=Decimal(b["size"]),
                )
                for b in sample_orderbook_response["bids"]
            ],
            asks=[
                OrderbookLevel(
                    price=Decimal(a["price"]),
                    size=Decimal(a["size"]),
                )
                for a in sample_orderbook_response["asks"]
            ],
            timestamp=datetime.now(timezone.utc),
        )

    client.get_orderbook = mock_get_orderbook

    # Mock verify_price
    async def mock_verify_price(token_id, expected_price, max_deviation=Decimal("0.10")):
        orderbook = await mock_get_orderbook(token_id)
        if orderbook.best_bid is None:
            return False, None, "No bids"
        deviation = abs(orderbook.best_bid - expected_price)
        is_valid = deviation <= max_deviation
        reason = "" if is_valid else f"Deviation {deviation}"
        return is_valid, orderbook.best_bid, reason

    client.verify_price = mock_verify_price

    # Mock get_trade_size_at_price
    async def mock_get_trade_size_at_price(token_id, target_price, tolerance=Decimal("0.01"), max_age_seconds=60):
        return Decimal("100")

    client.get_trade_size_at_price = mock_get_trade_size_at_price

    return client


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.recv = AsyncMock(
        return_value='{"type":"price_change","asset_id":"0x123","price":"0.75"}'
    )
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


# =============================================================================
# Component Fixtures
# =============================================================================


@pytest.fixture
def metrics_collector():
    """Fresh metrics collector."""
    collector = MetricsCollector()
    collector.start()
    return collector


@pytest.fixture
def processor_config():
    """Default processor configuration."""
    return ProcessorConfig(
        max_trade_age_seconds=300,
        backfill_missing_size=True,
        check_price_divergence=True,
        max_price_deviation=Decimal("0.10"),
    )


@pytest.fixture
def event_processor(mock_rest_client, metrics_collector, processor_config):
    """Event processor with mocked dependencies."""
    return EventProcessor(
        rest_client=mock_rest_client,
        metrics=metrics_collector,
        config=processor_config,
    )
