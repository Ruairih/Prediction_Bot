"""
Monitoring Layer - Health checks, alerting, and observability.

This module provides:
    - HealthChecker: Component health checks with timeouts
    - HealthStatus: Health status enum (HEALTHY, DEGRADED, UNHEALTHY, WARNING)
    - ComponentHealth: Health check result for a single component
    - AggregateHealth: Overall system health aggregation
    - AlertManager: Telegram notifications with deduplication
    - MetricsCollector: Trading metrics (win rate, P&L, positions)
    - TradingMetrics: Dataclass for metrics summary
    - create_app: Flask dashboard factory

Health Checks:
    - Database connectivity
    - WebSocket connection status AND message staleness
    - Balance thresholds
    - Position limits

Alert Deduplication:
    - Same alert won't fire repeatedly within cooldown window
    - Different alert types are tracked separately
"""

from .health_checker import (
    AggregateHealth,
    ComponentHealth,
    HealthChecker,
    HealthStatus,
)
from .metrics import MetricsCollector, TradingMetrics
from .alerting import AlertManager
from .dashboard import Dashboard, create_app

__all__ = [
    # Health checking
    "HealthChecker",
    "HealthStatus",
    "ComponentHealth",
    "AggregateHealth",
    # Alerting
    "AlertManager",
    # Metrics
    "MetricsCollector",
    "TradingMetrics",
    # Dashboard
    "Dashboard",
    "create_app",
]
