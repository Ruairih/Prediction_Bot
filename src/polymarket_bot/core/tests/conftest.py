"""
Core layer test fixtures.

Core tests verify orchestration logic, so we mock
the storage, ingestion, and strategy layers.
"""
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from polymarket_bot.core import (
    TradingEngine,
    EngineConfig,
    EventProcessor,
    TriggerTracker,
    WatchlistService,
)
from polymarket_bot.strategies import (
    Strategy,
    StrategyContext,
    Signal,
    SignalType,
    EntrySignal,
    ExitSignal,
    HoldSignal,
    WatchlistSignal,
    IgnoreSignal,
)


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value="DELETE 0")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)

    # Mock transaction() as async context manager
    # The transaction returns a connection-like object with execute/fetchval
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="INSERT 0")
    # For atomic trigger recording:
    # 1st call (condition check) returns None (no existing)
    # 2nd call (INSERT RETURNING) returns token_id (success)
    mock_conn.fetchval = AsyncMock(side_effect=[None, "tok_test"])

    # Create async context manager
    class MockTransaction:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    db.transaction = MagicMock(return_value=MockTransaction())
    # Store mock_conn on db for tests that need to customize it
    db._mock_conn = mock_conn

    return db


# =============================================================================
# Mock Strategy Fixtures
# =============================================================================


@pytest.fixture
def mock_strategy():
    """Mock strategy that can be configured."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "test_strategy"
    strategy.evaluate.return_value = HoldSignal(reason="Default hold")
    return strategy


@pytest.fixture
def always_enter_strategy():
    """Strategy that always generates ENTRY signal."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "always_enter"
    strategy.evaluate.return_value = EntrySignal(
        token_id="tok_test",
        side="BUY",
        price=Decimal("0.95"),
        size=Decimal("20"),
        reason="Test entry",
    )
    return strategy


@pytest.fixture
def watchlist_strategy():
    """Strategy that generates WATCHLIST signal."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "watchlist_test"
    strategy.evaluate.return_value = WatchlistSignal(
        token_id="tok_test",
        current_score=0.92,
        reason="Score below threshold",
    )
    return strategy


# =============================================================================
# Mock API Client Fixtures
# =============================================================================


@pytest.fixture
def mock_api_client():
    """Mock REST API client with orderbook verification."""
    client = AsyncMock()
    client.get_orderbook = AsyncMock(return_value={
        "bids": [{"price": "0.94", "size": "100"}],
        "asks": [{"price": "0.96", "size": "100"}],
    })
    client.verify_orderbook_price = AsyncMock(return_value=(True, Decimal("0.94"), "OK"))
    return client


@pytest.fixture
def divergent_orderbook_client():
    """Mock API client where orderbook doesn't match trigger (G5 test)."""
    client = AsyncMock()
    client.get_orderbook = AsyncMock(return_value={
        "bids": [{"price": "0.05", "size": "100"}],  # Way off from trigger
        "asks": [{"price": "0.06", "size": "100"}],
    })
    client.verify_orderbook_price = AsyncMock(return_value=(False, Decimal("0.05"), "Orderbook mismatch"))
    return client


# =============================================================================
# Event Fixtures
# =============================================================================


@pytest.fixture
def price_trigger_event():
    """Price crossing 0.95 threshold."""
    return {
        "type": "price_change",
        "token_id": "tok_yes_abc",
        "condition_id": "0xtest123",
        "price": "0.95",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


@pytest.fixture
def below_threshold_event():
    """Price below threshold (should not trigger)."""
    return {
        "type": "price_change",
        "token_id": "tok_yes_abc",
        "condition_id": "0xtest123",
        "price": "0.90",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


@pytest.fixture
def stale_trade_event():
    """Trade from 10 minutes ago (G1 - should be rejected)."""
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    return {
        "type": "trade",
        "token_id": "tok_yes_abc",
        "condition_id": "0xtest123",
        "price": "0.95",
        "timestamp": old_time.timestamp(),
    }


@pytest.fixture
def weather_market_event():
    """Weather market event (G6 - should be blocked)."""
    return {
        "type": "price_change",
        "token_id": "tok_weather",
        "condition_id": "0xweather123",
        "price": "0.95",
        "question": "Will it rain in NYC tomorrow?",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


@pytest.fixture
def rainbow_event():
    """Rainbow Six event (G6 regression - should NOT be blocked)."""
    return {
        "type": "price_change",
        "token_id": "tok_esports",
        "condition_id": "0xesports123",
        "price": "0.95",
        "question": "Will Team A win Rainbow Six Siege tournament?",
        "category": "Esports",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }


# =============================================================================
# Engine Fixtures
# =============================================================================


@pytest.fixture
def engine_config():
    """Standard engine configuration."""
    return EngineConfig(
        price_threshold=Decimal("0.95"),
        position_size=Decimal("20"),
        max_positions=50,
        dry_run=True,  # Always dry run in tests
        max_trade_age_seconds=300,
        verify_orderbook=True,
    )


@pytest.fixture
def trading_engine(mock_db, engine_config, mock_strategy, mock_api_client):
    """Configured TradingEngine for tests."""
    return TradingEngine(
        config=engine_config,
        db=mock_db,
        strategy=mock_strategy,
        api_client=mock_api_client,
    )


# =============================================================================
# Strategy Context Fixtures
# =============================================================================


@pytest.fixture
def base_context():
    """Standard context for testing."""
    return StrategyContext(
        condition_id="0xtest123",
        token_id="tok_yes_abc",
        question="Will BTC hit $100k by end of 2025?",
        category="Crypto",
        trigger_price=Decimal("0.95"),
        trade_size=Decimal("75"),
        time_to_end_hours=720,
        trade_age_seconds=10,
        model_score=0.98,
    )
