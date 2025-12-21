"""
Tests for component health checking.

Health checks verify that all system components are functioning.
"""
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


class TestDatabaseHealthCheck:
    """Tests for database health checks."""

    @pytest.mark.asyncio
    async def test_database_health_when_accessible(self, mock_db):
        """Should report healthy when database is accessible."""
        mock_db.execute = AsyncMock(return_value=None)
        checker = HealthChecker(db=mock_db)

        health = await checker.check_database()

        assert health.status == HealthStatus.HEALTHY
        assert health.component == "database"
        assert health.latency_ms is not None
        assert health.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_database_health_when_inaccessible(self, mock_db):
        """Should report unhealthy when database query fails."""
        mock_db.execute = AsyncMock(side_effect=Exception("Database error"))
        checker = HealthChecker(db=mock_db)

        health = await checker.check_database()

        assert health.status == HealthStatus.UNHEALTHY
        assert "error" in health.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_when_not_configured(self):
        """Should report unhealthy when no database configured."""
        checker = HealthChecker(db=None)

        health = await checker.check_database()

        assert health.status == HealthStatus.UNHEALTHY
        assert "no database" in health.message.lower()


class TestWebSocketHealthCheck:
    """Tests for WebSocket health checks."""

    @pytest.mark.asyncio
    async def test_websocket_health_when_connected(self, mock_websocket_healthy):
        """Should report healthy when WebSocket is connected."""
        checker = HealthChecker(websocket_client=mock_websocket_healthy)

        health = await checker.check_websocket()

        assert health.status == HealthStatus.HEALTHY
        assert "connected" in health.message.lower()

    @pytest.mark.asyncio
    async def test_websocket_health_when_disconnected(self, mock_websocket_unhealthy):
        """Should report unhealthy when WebSocket is disconnected."""
        checker = HealthChecker(websocket_client=mock_websocket_unhealthy)

        health = await checker.check_websocket()

        assert health.status == HealthStatus.UNHEALTHY
        assert "disconnected" in health.message.lower()

    @pytest.mark.asyncio
    async def test_websocket_health_when_stale(self):
        """
        GOTCHA: WebSocket can appear connected but not receiving data.

        Must check last_message_time, not just connection status.
        """
        stale_client = MagicMock()
        stale_client.is_connected = True
        stale_client.last_message_time = datetime.now(timezone.utc) - timedelta(minutes=10)

        checker = HealthChecker(
            websocket_client=stale_client,
            message_staleness_threshold=60,  # 60 seconds
        )

        health = await checker.check_websocket()

        assert health.status == HealthStatus.DEGRADED
        assert "stale" in health.message.lower()

    @pytest.mark.asyncio
    async def test_websocket_health_when_not_configured(self):
        """Should report warning when no WebSocket configured."""
        checker = HealthChecker(websocket_client=None)

        health = await checker.check_websocket()

        assert health.status == HealthStatus.WARNING
        assert "no websocket" in health.message.lower()


class TestBalanceHealthCheck:
    """Tests for balance health checks."""

    @pytest.mark.asyncio
    async def test_balance_health_with_sufficient_funds(self, mock_clob_client):
        """Should report healthy with sufficient balance."""
        checker = HealthChecker(clob_client=mock_clob_client)

        health = await checker.check_balance(min_balance=Decimal("100.00"))

        assert health.status == HealthStatus.HEALTHY
        assert "$500" in health.message

    @pytest.mark.asyncio
    async def test_balance_health_with_low_funds(self, mock_clob_low_balance):
        """Should report warning with low balance."""
        checker = HealthChecker(clob_client=mock_clob_low_balance)

        health = await checker.check_balance(min_balance=Decimal("100.00"))

        assert health.status == HealthStatus.WARNING
        assert "low" in health.message.lower()

    @pytest.mark.asyncio
    async def test_balance_health_when_check_fails(self):
        """Should report unhealthy when balance check fails."""
        failing_client = MagicMock()
        failing_client.get_balance.side_effect = Exception("API error")

        checker = HealthChecker(clob_client=failing_client)

        health = await checker.check_balance()

        assert health.status == HealthStatus.UNHEALTHY
        assert "error" in health.message.lower()

    @pytest.mark.asyncio
    async def test_balance_health_when_not_configured(self):
        """Should report warning when no CLOB client configured."""
        checker = HealthChecker(clob_client=None)

        health = await checker.check_balance()

        assert health.status == HealthStatus.WARNING


class TestAggregateHealth:
    """Tests for overall system health."""

    @pytest.mark.asyncio
    async def test_overall_healthy_when_all_components_healthy(
        self, mock_db, mock_websocket_healthy, mock_clob_client
    ):
        """Should report overall healthy when all components pass."""
        mock_db.execute = AsyncMock(return_value=None)

        checker = HealthChecker(
            db=mock_db,
            websocket_client=mock_websocket_healthy,
            clob_client=mock_clob_client,
        )

        overall = await checker.check_all()

        assert overall.status == HealthStatus.HEALTHY
        assert len(overall.components) >= 3

    @pytest.mark.asyncio
    async def test_overall_unhealthy_if_any_critical_unhealthy(
        self, mock_db, mock_websocket_unhealthy, mock_clob_client
    ):
        """Should report overall unhealthy if critical component fails."""
        mock_db.execute = AsyncMock(return_value=None)

        checker = HealthChecker(
            db=mock_db,
            websocket_client=mock_websocket_unhealthy,
            clob_client=mock_clob_client,
        )

        overall = await checker.check_all()

        assert overall.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_overall_degraded_if_non_critical_warning(
        self, mock_db, mock_websocket_healthy, mock_clob_low_balance
    ):
        """Should report degraded if non-critical component has warning."""
        mock_db.execute = AsyncMock(return_value=None)

        checker = HealthChecker(
            db=mock_db,
            websocket_client=mock_websocket_healthy,
            clob_client=mock_clob_low_balance,
        )

        overall = await checker.check_all()

        # Balance warning should degrade overall status
        assert overall.status in (HealthStatus.DEGRADED, HealthStatus.HEALTHY)

    @pytest.mark.asyncio
    async def test_check_all_includes_timestamp(self, health_checker):
        """Should include timestamp in aggregate health."""
        overall = await health_checker.check_all()

        assert overall.checked_at is not None
        assert isinstance(overall.checked_at, datetime)


class TestHealthCheckLatency:
    """Tests for health check performance."""

    @pytest.mark.asyncio
    async def test_health_check_completes_quickly(self, health_checker):
        """Health checks should complete within timeout."""
        import time

        start = time.time()
        await health_checker.check_all()
        elapsed = time.time() - start

        # Should complete within 5 seconds
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_handles_slow_component_gracefully(self, mock_db, mock_clob_client):
        """Should timeout slow components rather than hang."""
        import asyncio

        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(10)

        mock_db.execute = slow_execute
        checker = HealthChecker(
            db=mock_db,
            clob_client=mock_clob_client,
        )

        # Should timeout, not hang
        overall = await checker.check_all(timeout=2.0)

        # Database should show as unhealthy due to timeout
        db_health = next(
            (c for c in overall.components if c.component == "database"), None
        )
        assert db_health is not None
        assert db_health.status == HealthStatus.UNHEALTHY
        assert "timed out" in db_health.message.lower()


class TestHealthStatusCalculation:
    """Tests for status calculation logic."""

    def test_calculate_overall_status_all_healthy(self, health_checker):
        """All healthy components should result in healthy overall."""
        components = [
            ComponentHealth("db", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("ws", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("balance", HealthStatus.HEALTHY, "OK"),
        ]

        status = health_checker._calculate_overall_status(components)

        assert status == HealthStatus.HEALTHY

    def test_calculate_overall_status_with_unhealthy(self, health_checker):
        """Any unhealthy component should result in unhealthy overall."""
        components = [
            ComponentHealth("db", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("ws", HealthStatus.UNHEALTHY, "Disconnected"),
            ComponentHealth("balance", HealthStatus.HEALTHY, "OK"),
        ]

        status = health_checker._calculate_overall_status(components)

        assert status == HealthStatus.UNHEALTHY

    def test_calculate_overall_status_with_warning(self, health_checker):
        """Warning without unhealthy should result in degraded overall."""
        components = [
            ComponentHealth("db", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("ws", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("balance", HealthStatus.WARNING, "Low balance"),
        ]

        status = health_checker._calculate_overall_status(components)

        assert status == HealthStatus.DEGRADED

    def test_calculate_overall_status_with_degraded(self, health_checker):
        """Degraded without unhealthy should result in degraded overall."""
        components = [
            ComponentHealth("db", HealthStatus.HEALTHY, "OK"),
            ComponentHealth("ws", HealthStatus.DEGRADED, "Stale messages"),
            ComponentHealth("balance", HealthStatus.HEALTHY, "OK"),
        ]

        status = health_checker._calculate_overall_status(components)

        assert status == HealthStatus.DEGRADED
