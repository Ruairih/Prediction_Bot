"""
Shared test fixtures for integration tests.

This file provides fixtures that span multiple components,
unlike component-specific fixtures in src/polymarket_bot/{component}/tests/conftest.py
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock

# Use test database by default
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://predict:predict@localhost:5433/predict")
)


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def database_url():
    """Get database URL from environment."""
    return os.environ.get("DATABASE_URL")


@pytest.fixture
async def db():
    """
    Fresh database connection for each test.

    This fixture:
    1. Creates a new database connection
    2. Yields it for the test
    3. Closes the connection after the test

    For isolation, consider wrapping in a transaction that rolls back.
    """
    from polymarket_bot.storage import Database, DatabaseConfig

    config = DatabaseConfig(url=os.environ.get("DATABASE_URL"))
    database = Database(config)
    await database.initialize()

    yield database

    await database.close()


@pytest.fixture
async def db_transaction(db):
    """
    Database connection wrapped in a transaction.

    All changes are rolled back after the test.
    Useful for tests that modify data.
    """
    async with db.transaction() as conn:
        yield conn
        # Transaction rolls back when context exits without commit


# =============================================================================
# Mock External Service Fixtures
# =============================================================================

@pytest.fixture
def mock_polymarket_rest_api():
    """
    Mock Polymarket REST API responses.

    Use this when testing components that call the Polymarket API.
    """
    api = AsyncMock()

    # Default market response
    api.fetch_market.return_value = {
        "condition_id": "0xtest123",
        "question": "Test Market Question?",
        "end_date": "2025-12-31T00:00:00Z",
        "tokens": [
            {"token_id": "tok_yes", "outcome": "Yes"},
            {"token_id": "tok_no", "outcome": "No"},
        ],
    }

    # Default orderbook
    api.fetch_orderbook.return_value = {
        "bids": [{"price": "0.94", "size": "100"}],
        "asks": [{"price": "0.96", "size": "100"}],
    }

    # Default trades (include stale trade for G1 testing)
    import time
    now = time.time()
    api.fetch_trades.return_value = [
        {"id": "fresh", "price": "0.95", "size": "75", "timestamp": int((now - 10) * 1000)},
        {"id": "stale", "price": "0.95", "size": "5", "timestamp": int((now - 86400 * 60) * 1000)},
    ]

    return api


@pytest.fixture
def mock_websocket():
    """
    Mock WebSocket connection.

    Simulates price updates from Polymarket.
    """
    ws = AsyncMock()
    ws.is_connected = True
    ws.recv = AsyncMock(return_value='{"type":"price_change","asset_id":"0x123","price":"0.95"}')
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_clob_client():
    """
    Mock Polymarket CLOB client for order submission.

    Use this when testing execution layer.
    """
    from decimal import Decimal

    client = MagicMock()

    # Order creation
    client.create_order.return_value = {
        "orderID": "order_123",
        "status": "LIVE",
    }

    # Balance check
    client.get_balance.return_value = {"USDC": "1000.00"}

    # Order status
    client.get_order.return_value = {
        "orderID": "order_123",
        "status": "MATCHED",
        "filledSize": "20",
        "avgPrice": "0.95",
    }

    return client


@pytest.fixture
def mock_telegram_api():
    """
    Mock Telegram Bot API for alerting tests.
    """
    api = MagicMock()
    api.send_message = MagicMock(return_value={"ok": True})
    return api


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "condition_id": "0xtest123",
        "market_id": "market_abc",
        "question": "Will BTC hit $100k by end of 2025?",
        "category": "Crypto",
        "end_date": "2025-12-31T00:00:00Z",
        "tokens": [
            {"token_id": "tok_yes_abc", "outcome": "Yes", "outcome_index": 0},
            {"token_id": "tok_no_abc", "outcome": "No", "outcome_index": 1},
        ],
    }


@pytest.fixture
def sample_trigger_context(sample_market_data):
    """Sample context for strategy evaluation."""
    from decimal import Decimal

    return {
        "condition_id": sample_market_data["condition_id"],
        "token_id": sample_market_data["tokens"][0]["token_id"],
        "question": sample_market_data["question"],
        "category": sample_market_data["category"],
        "trigger_price": Decimal("0.95"),
        "trade_size": Decimal("75"),
        "time_to_end_hours": 720,  # 30 days
        "trade_age_seconds": 10,
        "model_score": 0.98,
    }


# =============================================================================
# Gotcha Regression Test Data
# =============================================================================

@pytest.fixture
def g1_stale_trades():
    """
    G1 Belichick Bug: Stale trade data.

    Returns trades with mixed ages for testing timestamp filtering.
    """
    import time
    now = time.time()

    return [
        # Fresh trade (10 seconds ago) - SHOULD BE INCLUDED
        {
            "id": "trade_fresh",
            "price": "0.95",
            "size": "75",
            "side": "BUY",
            "timestamp": int((now - 10) * 1000),
        },
        # Stale trade (60 days ago) - MUST BE FILTERED OUT
        {
            "id": "trade_stale",
            "price": "0.95",
            "size": "4.2",
            "side": "BUY",
            "timestamp": int((now - 86400 * 60) * 1000),
        },
    ]


@pytest.fixture
def g5_divergent_orderbook():
    """
    G5: Orderbook vs Trade Price Divergence.

    Orderbook at 5c when trigger was 95c.
    """
    return {
        "bids": [{"price": "0.05", "size": "1000"}],
        "asks": [{"price": "0.06", "size": "1000"}],
    }


@pytest.fixture
def g6_rainbow_question():
    """
    G6 Rainbow Bug: "Rainbow Six Siege" should NOT be weather.

    Returns question that contains "rain" but is NOT weather-related.
    """
    return "Will Team A win the Rainbow Six Siege tournament?"


@pytest.fixture
def g6_weather_question():
    """
    G6: Actual weather market that SHOULD be filtered.
    """
    return "Will it rain in New York City tomorrow?"
