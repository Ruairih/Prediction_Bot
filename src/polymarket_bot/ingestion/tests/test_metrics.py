"""Tests for metrics collection."""

import time
from datetime import datetime, timezone

import pytest

from polymarket_bot.ingestion.metrics import IngestionMetrics, MetricsCollector


class TestIngestionMetrics:
    """Tests for IngestionMetrics dataclass."""

    def test_default_values(self):
        """Default metrics are sensible."""
        metrics = IngestionMetrics()
        assert not metrics.websocket_connected
        assert metrics.events_received == 0
        assert metrics.freshness_percentage == 100.0
        assert metrics.errors_last_hour == 0

    def test_is_healthy_when_connected(self):
        """Healthy when connected with recent messages."""
        metrics = IngestionMetrics(
            websocket_connected=True,
            last_message_at=datetime.now(timezone.utc),
            errors_last_hour=0,
        )
        assert metrics.is_healthy

    def test_unhealthy_when_disconnected(self):
        """Unhealthy when not connected."""
        metrics = IngestionMetrics(
            websocket_connected=False,
        )
        assert not metrics.is_healthy

    def test_to_dict(self):
        """Can convert to dictionary for JSON."""
        metrics = IngestionMetrics(
            websocket_connected=True,
            events_received=100,
        )
        data = metrics.to_dict()
        assert data["websocket_connected"] is True
        assert data["events_received"] == 100
        assert "is_healthy" in data


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_initial_state(self):
        """Collector starts with clean state."""
        collector = MetricsCollector()
        metrics = collector.get_metrics()

        assert not metrics.websocket_connected
        assert metrics.events_received == 0
        assert metrics.g1_stale_filtered == 0

    def test_record_price_update(self, metrics_collector):
        """Records price update events."""
        metrics_collector.record_price_update()
        metrics_collector.record_price_update()

        metrics = metrics_collector.get_metrics()
        assert metrics.events_received >= 2
        assert metrics.price_updates_received >= 2

    def test_record_trade_stored(self, metrics_collector):
        """Records stored trades with age."""
        metrics_collector.record_trade_stored(age_seconds=10.0)
        metrics_collector.record_trade_stored(age_seconds=20.0)

        metrics = metrics_collector.get_metrics()
        assert metrics.trades_stored >= 2
        # Average age should be 15
        assert 14 < metrics.average_trade_age_seconds < 16

    def test_record_g1_filter(self, metrics_collector):
        """Records G1 stale trade filtering."""
        metrics_collector.record_g1_filter()

        metrics = metrics_collector.get_metrics()
        assert metrics.g1_stale_filtered >= 1

    def test_record_g3_backfill(self, metrics_collector):
        """Records G3 size backfill."""
        metrics_collector.record_g3_missing_size()
        metrics_collector.record_g3_backfill()

        metrics = metrics_collector.get_metrics()
        assert metrics.g3_missing_size >= 1
        assert metrics.g3_size_backfilled >= 1

    def test_record_g5_divergence(self, metrics_collector):
        """Records G5 price divergence."""
        metrics_collector.record_g5_divergence()

        metrics = metrics_collector.get_metrics()
        assert metrics.g5_divergence_detected >= 1

    def test_record_error(self, metrics_collector):
        """Records errors."""
        metrics_collector.record_error(
            error_type="ConnectionError",
            message="Test error",
            component="websocket",
        )

        metrics = metrics_collector.get_metrics()
        assert metrics.errors_last_hour >= 1
        assert len(metrics.recent_errors) >= 1
        assert metrics.recent_errors[-1].error_type == "ConnectionError"

    def test_websocket_state(self, metrics_collector):
        """Tracks WebSocket connection state."""
        metrics_collector.set_websocket_connected(True)
        metrics = metrics_collector.get_metrics()
        assert metrics.websocket_connected

        metrics_collector.set_websocket_connected(False)
        metrics = metrics_collector.get_metrics()
        assert not metrics.websocket_connected
        assert metrics.reconnection_count >= 1

    def test_uptime_tracking(self, metrics_collector):
        """Tracks service uptime."""
        # Sleep briefly to get measurable uptime
        time.sleep(0.1)

        metrics = metrics_collector.get_metrics()
        assert metrics.uptime_seconds > 0
        assert metrics.started_at is not None

    def test_events_per_second(self, metrics_collector):
        """Calculates events per second."""
        # Record some events
        for _ in range(10):
            metrics_collector.record_price_update()

        metrics = metrics_collector.get_metrics()
        # Should have some events per second (over 5 min window)
        assert metrics.events_per_second >= 0

    def test_freshness_percentage(self, metrics_collector):
        """Calculates data freshness percentage."""
        # Record some good trades
        metrics_collector.record_trade_stored(age_seconds=10)
        metrics_collector.record_trade_stored(age_seconds=10)
        metrics_collector.record_trade_stored(age_seconds=10)

        # Record one filtered trade
        metrics_collector.record_g1_filter()

        metrics = metrics_collector.get_metrics()
        # 3 out of 4 = 75%
        assert metrics.freshness_percentage == 75.0

    def test_reset(self, metrics_collector):
        """Can reset all metrics."""
        metrics_collector.record_price_update()
        metrics_collector.record_g1_filter()

        metrics_collector.reset()

        metrics = metrics_collector.get_metrics()
        assert metrics.events_received == 0
        assert metrics.g1_stale_filtered == 0
