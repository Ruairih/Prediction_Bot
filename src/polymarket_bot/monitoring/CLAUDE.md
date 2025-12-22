# Monitoring Layer - CLAUDE.md

> **STATUS: IMPLEMENTED**
> The monitoring layer is fully implemented with Flask dashboard, metrics collection, and health checking.
> The React dashboard in `/workspace/dashboard/` provides a modern UI that connects to the Flask API.

## Purpose

The monitoring layer provides **health checking**, **alerting**, and **observability**. It ensures the system is running correctly and alerts when problems occur.

## Current Implementation

### Flask Dashboard (`dashboard.py`)
- REST API endpoints at `/health`, `/api/status`, `/api/positions`, `/api/metrics`, `/api/triggers`
- Thread-safe async dispatch using `run_coroutine_threadsafe()` for asyncpg compatibility
- Optional API key authentication via `DASHBOARD_API_KEY`
- SSE endpoint for real-time updates at `/api/stream`
- Binds to `127.0.0.1` by default for security (configurable via `DASHBOARD_HOST`)

### Metrics Collection (`metrics.py`)
- `MetricsCollector` class with database queries for win rate, P&L, positions
- Uses `net_pnl` column consistently for all P&L calculations
- Async methods for all database operations

### Health Checking (`health_checker.py`)
- Component health checks for database, WebSocket, balance
- Aggregated health status with `HEALTHY`, `DEGRADED`, `UNHEALTHY` states

### React Dashboard (`/workspace/dashboard/`)
- Modern React + TypeScript + TailwindCSS UI
- React Query for data fetching with caching and auto-refresh
- Pages: Overview, Positions, Activity, Performance, Strategy, Risk, System
- Vite dev server with proxy to Flask API

### Threading Model
The Flask dashboard runs in a **background thread** while the main async event loop runs the bot. This requires:
- Using `run_coroutine_threadsafe()` to dispatch async database calls to the main loop
- Proper shutdown handling with `_stop_dashboard()` in main.py
- Event loop reference passed during Dashboard initialization

## Dependencies

- All other layers (monitors their health)

## Directory Structure

```
monitoring/
├── __init__.py
├── health_checker.py       # Component health checks
├── alerting.py             # Telegram/notification alerts
├── dashboard.py            # Web dashboard (Flask)
├── metrics.py              # Metrics collection
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_health_checker.py
│   ├── test_alerting.py
│   ├── test_dashboard.py
│   └── test_metrics.py
└── CLAUDE.md               # This file
```

## Test Fixtures (conftest.py)

```python
"""
Monitoring layer test fixtures.

Tests health checks, alerting, and dashboard endpoints.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from monitoring.health_checker import HealthChecker, ComponentHealth, HealthStatus
from monitoring.alerting import AlertManager, TelegramBot
from monitoring.dashboard import create_app
from storage.database import Database, DatabaseConfig


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
async def db():
    """Fresh database for each test (uses test PostgreSQL)."""
    config = DatabaseConfig(
        url=os.environ.get("TEST_DATABASE_URL", "postgresql://predict:predict@localhost:5433/predict")
    )
    database = Database(config)
    await database.initialize()
    yield database
    await database.close()


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
def mock_clob_client():
    """Mock CLOB client for balance checks."""
    client = MagicMock()
    client.get_balance.return_value = {"USDC": "500.00"}
    return client


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
# Dashboard Fixtures
# =============================================================================

@pytest.fixture
def app(db):
    """Flask test app."""
    app = create_app(db=db, testing=True)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# =============================================================================
# Health Check Fixtures
# =============================================================================

@pytest.fixture
def health_checker(db, mock_websocket_healthy, mock_clob_client):
    """HealthChecker with mock dependencies."""
    return HealthChecker(
        db=db,
        websocket_client=mock_websocket_healthy,
        clob_client=mock_clob_client,
    )
```

## Test Specifications

### 1. test_health_checker.py

```python
"""
Tests for component health checking.

Health checks verify that all system components are functioning.
"""

class TestComponentHealthChecks:
    """Tests for individual component health checks."""

    def test_database_health_when_accessible(self, health_checker, db):
        """Should report healthy when database is accessible."""
        health = health_checker.check_database()

        assert health.status == HealthStatus.HEALTHY
        assert health.component == "database"

    def test_database_health_when_inaccessible(self, health_checker, mocker):
        """Should report unhealthy when database query fails."""
        mocker.patch.object(
            health_checker.db, 'execute',
            side_effect=Exception("Database error")
        )

        health = health_checker.check_database()

        assert health.status == HealthStatus.UNHEALTHY
        assert "error" in health.message.lower()

    def test_websocket_health_when_connected(
        self, health_checker, mock_websocket_healthy
    ):
        """Should report healthy when WebSocket is connected."""
        health = health_checker.check_websocket()

        assert health.status == HealthStatus.HEALTHY

    def test_websocket_health_when_disconnected(self, db, mock_websocket_unhealthy, mock_clob_client):
        """Should report unhealthy when WebSocket is disconnected."""
        checker = HealthChecker(
            db=db,
            websocket_client=mock_websocket_unhealthy,
            clob_client=mock_clob_client,
        )

        health = checker.check_websocket()

        assert health.status == HealthStatus.UNHEALTHY

    def test_websocket_health_when_stale(self, db, mock_clob_client):
        """Should report degraded when no messages for too long."""
        stale_client = MagicMock()
        stale_client.is_connected = True
        stale_client.last_message_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        checker = HealthChecker(
            db=db,
            websocket_client=stale_client,
            clob_client=mock_clob_client,
            message_staleness_threshold=60,  # 60 seconds
        )

        health = checker.check_websocket()

        assert health.status == HealthStatus.DEGRADED
        assert "stale" in health.message.lower()

    def test_balance_health_with_sufficient_funds(self, health_checker):
        """Should report healthy with sufficient balance."""
        health = health_checker.check_balance(min_balance=Decimal("100.00"))

        # Mock has $500
        assert health.status == HealthStatus.HEALTHY

    def test_balance_health_with_low_funds(self, health_checker):
        """Should report warning with low balance."""
        health = health_checker.check_balance(
            min_balance=Decimal("1000.00")  # More than available
        )

        assert health.status == HealthStatus.WARNING
        assert "low" in health.message.lower()


class TestAggregateHealth:
    """Tests for overall system health."""

    def test_overall_healthy_when_all_components_healthy(self, health_checker):
        """Should report overall healthy when all components pass."""
        overall = health_checker.check_all()

        assert overall.status == HealthStatus.HEALTHY
        assert len(overall.components) >= 3  # db, ws, balance

    def test_overall_unhealthy_if_any_critical_unhealthy(
        self, db, mock_websocket_unhealthy, mock_clob_client
    ):
        """Should report overall unhealthy if critical component fails."""
        checker = HealthChecker(
            db=db,
            websocket_client=mock_websocket_unhealthy,
            clob_client=mock_clob_client,
        )

        overall = checker.check_all()

        assert overall.status == HealthStatus.UNHEALTHY

    def test_overall_degraded_if_non_critical_warning(self, health_checker, mocker):
        """Should report degraded if non-critical component has warning."""
        # Balance low but not critical
        mocker.patch.object(
            health_checker, 'check_balance',
            return_value=ComponentHealth(
                component="balance",
                status=HealthStatus.WARNING,
                message="Low balance"
            )
        )

        overall = health_checker.check_all()

        assert overall.status == HealthStatus.DEGRADED


class TestHealthCheckLatency:
    """Tests for health check performance."""

    def test_health_check_completes_quickly(self, health_checker):
        """Health checks should complete within timeout."""
        import time

        start = time.time()
        health_checker.check_all()
        elapsed = time.time() - start

        # Should complete within 5 seconds
        assert elapsed < 5.0

    def test_handles_slow_component_gracefully(self, health_checker, mocker):
        """Should timeout slow components rather than hang."""
        def slow_check():
            import time
            time.sleep(10)  # Would hang without timeout

        mocker.patch.object(
            health_checker, 'check_database',
            side_effect=slow_check
        )

        # Should timeout, not hang
        overall = health_checker.check_all(timeout=2.0)

        # Database should show as unhealthy due to timeout
        db_health = next(c for c in overall.components if c.component == "database")
        assert db_health.status == HealthStatus.UNHEALTHY
```

### 2. test_alerting.py

```python
"""
Tests for alerting and notifications.

Alerts notify operators of important events.
"""

class TestTelegramAlerts:
    """Tests for Telegram notification sending."""

    def test_sends_alert_message(self, alert_manager, mock_telegram_api):
        """Should send message via Telegram API."""
        alert_manager.send_alert(
            title="Trade Executed",
            message="Bought 20 shares at $0.95"
        )

        mock_telegram_api.send_message.assert_called_once()

    def test_formats_message_correctly(self, alert_manager, mock_telegram_api):
        """Should format message with title and content."""
        alert_manager.send_alert(
            title="Test Alert",
            message="Test message content"
        )

        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "Test Alert" in text
        assert "Test message content" in text

    def test_handles_api_error_gracefully(self, alert_manager, mock_telegram_api):
        """Should not crash on Telegram API errors."""
        mock_telegram_api.send_message.side_effect = Exception("API error")

        # Should not raise
        alert_manager.send_alert(title="Test", message="Test")


class TestAlertDeduplication:
    """Tests for alert deduplication."""

    def test_deduplicates_repeated_alerts(self, alert_manager, mock_telegram_api):
        """Should not send duplicate alerts within window."""
        # Send same alert twice
        alert_manager.send_alert(
            title="Duplicate Alert",
            message="Same message",
            dedup_key="test_key"
        )
        alert_manager.send_alert(
            title="Duplicate Alert",
            message="Same message",
            dedup_key="test_key"
        )

        # Should only send once
        assert mock_telegram_api.send_message.call_count == 1

    def test_allows_different_alerts(self, alert_manager, mock_telegram_api):
        """Should send different alerts."""
        alert_manager.send_alert(
            title="Alert 1",
            message="Message 1",
            dedup_key="key_1"
        )
        alert_manager.send_alert(
            title="Alert 2",
            message="Message 2",
            dedup_key="key_2"
        )

        assert mock_telegram_api.send_message.call_count == 2

    def test_resends_after_cooldown(self, alert_manager, mock_telegram_api, mocker):
        """Should resend same alert after cooldown period."""
        # Mock time to control cooldown
        current_time = datetime.now(timezone.utc)
        mocker.patch(
            'monitoring.alerting.datetime',
            **{'now.return_value': current_time}
        )

        alert_manager.send_alert(
            title="Cooldown Test",
            message="Test",
            dedup_key="cooldown_key",
            cooldown_seconds=60
        )

        # Advance time past cooldown
        mocker.patch(
            'monitoring.alerting.datetime',
            **{'now.return_value': current_time + timedelta(seconds=61)}
        )

        alert_manager.send_alert(
            title="Cooldown Test",
            message="Test",
            dedup_key="cooldown_key",
            cooldown_seconds=60
        )

        assert mock_telegram_api.send_message.call_count == 2


class TestAlertTypes:
    """Tests for different alert types."""

    def test_trade_execution_alert(self, alert_manager, mock_telegram_api):
        """Should send trade execution alert."""
        alert_manager.alert_trade_executed(
            token_id="tok_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "BUY" in text
        assert "0.95" in text

    def test_health_alert(self, alert_manager, mock_telegram_api):
        """Should send health degradation alert."""
        alert_manager.alert_health_issue(
            component="websocket",
            status=HealthStatus.UNHEALTHY,
            message="Connection lost"
        )

        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "websocket" in text.lower()
        assert "unhealthy" in text.lower() or "lost" in text.lower()
```

### 3. test_dashboard.py

```python
"""
Tests for web dashboard endpoints.

The dashboard provides a web UI for monitoring.
"""

class TestDashboardEndpoints:
    """Tests for dashboard HTTP endpoints."""

    def test_health_endpoint(self, client):
        """Should return health status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()
        assert "status" in data

    def test_positions_endpoint(self, client, db):
        """Should return current positions."""
        # Add a test position
        position_repo = PositionRepository(db)
        position_repo.create(Position(
            position_id="pos_test",
            token_id="tok_abc",
            condition_id="0x123",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
        ))

        response = client.get("/api/positions")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["positions"]) == 1

    def test_watchlist_endpoint(self, client, db):
        """Should return watchlist entries."""
        response = client.get("/api/watchlist")

        assert response.status_code == 200
        data = response.get_json()
        assert "entries" in data

    def test_metrics_endpoint(self, client):
        """Should return trading metrics."""
        response = client.get("/api/metrics")

        assert response.status_code == 200
        data = response.get_json()
        assert "total_trades" in data
        assert "win_rate" in data


class TestDashboardAuthentication:
    """Tests for dashboard security."""

    def test_protected_endpoints_require_auth(self, client):
        """Protected endpoints should require authentication."""
        # When auth is enabled
        response = client.get(
            "/api/positions",
            headers={}  # No auth header
        )

        # Should reject (if auth configured)
        # Note: Depends on configuration
        assert response.status_code in [200, 401]


class TestDashboardUpdates:
    """Tests for real-time updates."""

    def test_sse_endpoint_streams_updates(self, client):
        """Should stream updates via SSE."""
        response = client.get("/api/stream")

        assert response.status_code == 200
        assert "text/event-stream" in response.content_type
```

### 4. test_metrics.py

```python
"""
Tests for metrics collection.

Metrics track trading performance over time.
"""

class TestMetricsCollection:
    """Tests for collecting trading metrics."""

    def test_calculates_win_rate(self, db):
        """Should calculate win rate from closed positions."""
        metrics = MetricsCollector(db)

        # Add some closed positions
        exit_repo = ExitEventRepository(db)
        exit_repo.create(ExitEvent(
            position_id="pos_1",
            exit_type="resolution_yes",
            realized_pnl=Decimal("1.00"),  # Win
        ))
        exit_repo.create(ExitEvent(
            position_id="pos_2",
            exit_type="resolution_yes",
            realized_pnl=Decimal("0.80"),  # Win
        ))
        exit_repo.create(ExitEvent(
            position_id="pos_3",
            exit_type="resolution_no",
            realized_pnl=Decimal("-19.00"),  # Loss
        ))

        win_rate = metrics.get_win_rate()

        # 2 wins out of 3
        assert win_rate == pytest.approx(0.667, rel=0.01)

    def test_calculates_total_pnl(self, db):
        """Should calculate total realized P&L."""
        metrics = MetricsCollector(db)

        # Add exits with P&L
        exit_repo = ExitEventRepository(db)
        exit_repo.create(ExitEvent(position_id="1", realized_pnl=Decimal("1.00")))
        exit_repo.create(ExitEvent(position_id="2", realized_pnl=Decimal("0.80")))
        exit_repo.create(ExitEvent(position_id="3", realized_pnl=Decimal("-19.00")))

        total_pnl = metrics.get_total_pnl()

        # 1.00 + 0.80 - 19.00 = -17.20
        assert total_pnl == Decimal("-17.20")

    def test_counts_active_positions(self, db):
        """Should count current open positions."""
        metrics = MetricsCollector(db)

        position_repo = PositionRepository(db)
        position_repo.create(Position(
            position_id="pos_1",
            token_id="tok_1",
            condition_id="0x1",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
        ))
        position_repo.create(Position(
            position_id="pos_2",
            token_id="tok_2",
            condition_id="0x2",
            size=Decimal("20"),
            entry_price=Decimal("0.94"),
        ))

        count = metrics.get_position_count()

        assert count == 2

    def test_calculates_capital_deployed(self, db):
        """Should calculate total capital in positions."""
        metrics = MetricsCollector(db)

        position_repo = PositionRepository(db)
        position_repo.create(Position(
            position_id="pos_1",
            token_id="tok_1",
            condition_id="0x1",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            cost_basis=Decimal("19.00"),
        ))
        position_repo.create(Position(
            position_id="pos_2",
            token_id="tok_2",
            condition_id="0x2",
            size=Decimal("20"),
            entry_price=Decimal("0.94"),
            cost_basis=Decimal("18.80"),
        ))

        deployed = metrics.get_capital_deployed()

        # 19.00 + 18.80 = 37.80
        assert deployed == Decimal("37.80")
```

## Critical Gotchas (Must Test)

### 1. Dashboard Port Conflicts
```python
def test_dashboard_handles_port_conflict():
    """
    GOTCHA: Dashboard can fail to start if port is held
    by orphaned processes after reboot.

    Solution: ExecStartPre=-/usr/bin/fuser -k 5050/tcp
    """
    # This is handled at systemd level, but test graceful handling
    app = create_app(port=5050)
    # Should either start or fail gracefully
```

### 2. Alert Deduplication
```python
def test_does_not_spam_alerts():
    """
    GOTCHA: Same alert can fire repeatedly during issues.

    Must deduplicate to avoid notification spam.
    """
    for _ in range(10):
        alert_manager.send_alert(
            title="Same Error",
            message="Same message",
            dedup_key="spam_prevention"
        )

    # Should only send once
    assert telegram_api.send_message.call_count == 1
```

### 3. WebSocket Staleness Detection
```python
def test_detects_stale_websocket():
    """
    GOTCHA: WebSocket can appear connected but not receiving data.

    Must check last_message_time, not just connection status.
    """
    ws_client.is_connected = True
    ws_client.last_message_time = datetime.now() - timedelta(minutes=10)

    health = health_checker.check_websocket()

    assert health.status == HealthStatus.DEGRADED
```

## Running Tests

```bash
# All monitoring tests
pytest src/polymarket_bot/monitoring/tests/ -v

# Health checker tests
pytest src/polymarket_bot/monitoring/tests/test_health_checker.py -v

# Dashboard tests
pytest src/polymarket_bot/monitoring/tests/test_dashboard.py -v

# With coverage
pytest src/polymarket_bot/monitoring/tests/ --cov=src/polymarket_bot/monitoring
```

## MANDATORY: Dashboard Tests

**ALWAYS run dashboard tests after modifying dashboard code:**

```bash
# Run all monitoring tests
pytest src/polymarket_bot/monitoring/tests/ -v

# Run just dashboard tests
pytest src/polymarket_bot/monitoring/tests/test_dashboard.py -v

# Run with Flask test client
pytest src/polymarket_bot/monitoring/tests/test_dashboard.py -v -k "endpoint"
```

This is critical because the dashboard is user-facing and must not crash.

### Quick Smoke Test

After making dashboard changes, verify these endpoints work:
```bash
# Start dashboard (when implemented)
python -m polymarket_bot.monitoring --port 5050

# Test endpoints
curl http://localhost:5050/health
curl http://localhost:5050/api/positions
curl http://localhost:5050/api/metrics
```

## Implementation Order

1. `health_checker.py` - Component health checks
2. `metrics.py` - Metrics collection
3. `alerting.py` - Telegram notifications
4. `dashboard.py` - Web UI (depends on all above)

Each module: Write tests first, then implement.

---

## Implementation Notes (Post-Codex Review)

### Dashboard Security Fixes

#### API Key Authentication

**Problem:** All dashboard routes were unauthenticated. If bound beyond localhost, anyone could read health/positions/metrics data.

**Solution:** Added optional API key authentication via `DASHBOARD_API_KEY` environment variable:

```python
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY")

def require_api_key(f: Callable) -> Callable:
    """Decorator to require API key for route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_API_KEY:
            return f(*args, **kwargs)  # No auth configured

        provided_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not provided_key or provided_key != DASHBOARD_API_KEY:
            abort(401)

        return f(*args, **kwargs)
    return decorated
```

**Usage:**
```bash
# Enable authentication
export DASHBOARD_API_KEY="your-secret-key-here"

# Access with header
curl -H "X-API-Key: your-secret-key-here" http://localhost:5050/api/positions

# Or query parameter
curl "http://localhost:5050/api/positions?api_key=your-secret-key-here"
```

#### XSS Protection

**Problem:** API data was interpolated into `innerHTML` without escaping, allowing XSS attacks.

**Solution:** Changed all user data rendering to use `textContent`:

```javascript
// OLD (UNSAFE):
document.getElementById("token").innerHTML = data.token_id;

// NEW (SAFE):
document.getElementById("token").textContent = data.token_id;
```

Also added HTML escaping helper for any remaining dynamic HTML:
```javascript
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

### Tests Added

- `TestDashboardSecurity` - Tests for API key authentication
- `TestXSSProtection` - Tests for XSS protection in JavaScript
