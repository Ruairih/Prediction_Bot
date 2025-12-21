"""
Monitoring layer test fixtures.

Tests health checks, alerting, and dashboard endpoints.
"""
import os
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from polymarket_bot.monitoring.health_checker import (
    HealthChecker,
    HealthStatus,
    ComponentHealth,
    AggregateHealth,
)
from polymarket_bot.monitoring.alerting import AlertManager
from polymarket_bot.monitoring.metrics import MetricsCollector
from polymarket_bot.monitoring.dashboard import create_app


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    return db


# =============================================================================
# Mock Component Fixtures
# =============================================================================

@pytest.fixture
def mock_websocket_healthy():
    """Mock healthy WebSocket client."""
    client = MagicMock()
    client.is_connected = True
    client.last_message_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    return client


@pytest.fixture
def mock_websocket_unhealthy():
    """Mock unhealthy WebSocket client (disconnected)."""
    client = MagicMock()
    client.is_connected = False
    client.last_message_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    return client


@pytest.fixture
def mock_websocket_stale():
    """Mock WebSocket that is connected but stale."""
    client = MagicMock()
    client.is_connected = True
    client.last_message_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    return client


@pytest.fixture
def mock_clob_client():
    """Mock CLOB client for balance checks."""
    client = MagicMock()
    client.get_balance.return_value = {"USDC": "500.00"}
    return client


@pytest.fixture
def mock_clob_low_balance():
    """Mock CLOB client with low balance."""
    client = MagicMock()
    client.get_balance.return_value = {"USDC": "50.00"}
    return client


# =============================================================================
# Health Checker Fixtures
# =============================================================================

@pytest.fixture
def health_checker(mock_db, mock_websocket_healthy, mock_clob_client):
    """HealthChecker with mock dependencies."""
    return HealthChecker(
        db=mock_db,
        websocket_client=mock_websocket_healthy,
        clob_client=mock_clob_client,
    )


@pytest.fixture
def health_checker_unhealthy_ws(mock_db, mock_websocket_unhealthy, mock_clob_client):
    """HealthChecker with unhealthy WebSocket."""
    return HealthChecker(
        db=mock_db,
        websocket_client=mock_websocket_unhealthy,
        clob_client=mock_clob_client,
    )


@pytest.fixture
def health_checker_stale_ws(mock_db, mock_websocket_stale, mock_clob_client):
    """HealthChecker with stale WebSocket."""
    return HealthChecker(
        db=mock_db,
        websocket_client=mock_websocket_stale,
        clob_client=mock_clob_client,
        message_staleness_threshold=60,  # 60 seconds
    )


# =============================================================================
# Alerting Fixtures
# =============================================================================

@pytest.fixture
def mock_telegram_api():
    """Mock Telegram Bot API."""
    api = MagicMock()
    api.send_message = MagicMock(return_value={"ok": True})
    return api


@pytest.fixture
def alert_manager(mock_telegram_api):
    """AlertManager with mocked Telegram."""
    return AlertManager(
        telegram_bot_token="test_token",
        telegram_chat_id="test_chat",
        _telegram_api=mock_telegram_api,
    )


# =============================================================================
# Metrics Fixtures
# =============================================================================

@pytest.fixture
def metrics_collector(mock_db, mock_clob_client):
    """MetricsCollector with mock dependencies."""
    return MetricsCollector(db=mock_db, clob_client=mock_clob_client)


# =============================================================================
# Dashboard Fixtures
# =============================================================================

@pytest.fixture
def app(mock_db, health_checker, metrics_collector):
    """Flask test app."""
    flask_app = create_app(
        db=mock_db,
        health_checker=health_checker,
        metrics_collector=metrics_collector,
        testing=True,
    )
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()
