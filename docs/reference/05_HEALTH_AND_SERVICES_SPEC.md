# Health Check & Services Specification

## Overview

This spec covers:
1. Health checking service that monitors all components
2. systemd service definitions for production deployment
3. Monitoring and alerting infrastructure

---

## Part 1: Health Check Service

### Purpose

A dedicated service that:
- Monitors health of all trading bot components
- Exposes health status via HTTP endpoint
- Sends alerts on failures
- Enables automated recovery

### Directory Structure

```
src/polymarket_bot/monitoring/
├── CLAUDE.md
├── __init__.py
├── health_checker.py     # Main health check service
├── health_types.py       # Health status types
├── alerter.py            # Telegram/email alerts
├── dashboard/            # Web dashboard
│   ├── app.py
│   └── templates/
└── tests/
```

### `health_types.py` - Health Status Types

```python
"""
Health check types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    last_check: datetime = field(default_factory=datetime.utcnow)
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check": self.last_check.isoformat(),
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "consecutive_failures": self.consecutive_failures,
            "metadata": self.metadata,
        }


@dataclass
class SystemHealth:
    """Overall system health status."""
    status: HealthStatus
    components: List[ComponentHealth]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "components": [c.to_dict() for c in self.components],
        }
```

### `health_checker.py` - Health Check Service

```python
"""
Health check service.

Monitors all trading bot components and exposes status via HTTP.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from aiohttp import web

from ..storage.database import Database
from ..ingestion.polymarket_client import PolymarketClient
from ..ingestion.websocket_client import WebSocketClient
from .health_types import ComponentHealth, HealthStatus, SystemHealth
from .alerter import Alerter

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckConfig:
    """Configuration for health checker."""
    # HTTP server
    host: str = "0.0.0.0"
    port: int = 5051

    # Check intervals
    check_interval_seconds: int = 30

    # Failure thresholds
    unhealthy_threshold: int = 3  # Consecutive failures for UNHEALTHY
    degraded_threshold: int = 1   # Consecutive failures for DEGRADED

    # Alert settings
    alert_on_unhealthy: bool = True
    alert_cooldown_minutes: int = 15


class HealthChecker:
    """
    Health check service that monitors all components.

    Components checked:
    - Database connectivity
    - Polymarket API connectivity
    - WebSocket connection status
    - Service processes (systemd)
    - Trading activity (recent trades)

    Exposes:
    - GET /health - Overall health status
    - GET /health/{component} - Single component status
    - GET /metrics - Prometheus-format metrics
    """

    def __init__(
        self,
        db: Database,
        polymarket_client: Optional[PolymarketClient] = None,
        websocket_client: Optional[WebSocketClient] = None,
        alerter: Optional[Alerter] = None,
        config: Optional[HealthCheckConfig] = None,
    ) -> None:
        self.db = db
        self.polymarket_client = polymarket_client
        self.websocket_client = websocket_client
        self.alerter = alerter
        self.config = config or HealthCheckConfig()

        # State
        self._component_status: Dict[str, ComponentHealth] = {}
        self._last_alert_time: Dict[str, datetime] = {}
        self._running = False

        # Custom health checks
        self._custom_checks: Dict[str, Callable] = {}

    def register_check(self, name: str, check_fn: Callable) -> None:
        """Register a custom health check function."""
        self._custom_checks[name] = check_fn

    async def check_all(self) -> SystemHealth:
        """Run all health checks and return system status."""
        components = []

        # Core checks
        components.append(await self._check_database())
        components.append(await self._check_polymarket_api())
        components.append(await self._check_websocket())
        components.append(await self._check_services())
        components.append(await self._check_trading_activity())

        # Custom checks
        for name, check_fn in self._custom_checks.items():
            try:
                result = await check_fn()
                components.append(result)
            except Exception as e:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                ))

        # Calculate overall status
        overall_status = self._calculate_overall_status(components)

        # Send alerts if needed
        if self.alerter and self.config.alert_on_unhealthy:
            await self._send_alerts(components)

        # Store in DB for history
        self._store_health(components)

        return SystemHealth(
            status=overall_status,
            components=components,
        )

    async def _check_database(self) -> ComponentHealth:
        """Check database connectivity."""
        try:
            is_healthy = self.db.health_check()
            return self._update_component(
                "database",
                HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY,
                "Connected" if is_healthy else "Connection failed",
            )
        except Exception as e:
            return self._update_component("database", HealthStatus.UNHEALTHY, str(e))

    async def _check_polymarket_api(self) -> ComponentHealth:
        """Check Polymarket API connectivity."""
        if not self.polymarket_client:
            return self._update_component(
                "polymarket_api",
                HealthStatus.UNKNOWN,
                "Client not configured",
            )

        try:
            # Try to fetch a single market
            markets = await self.polymarket_client.get_markets(limit=1)
            return self._update_component(
                "polymarket_api",
                HealthStatus.HEALTHY,
                f"Connected, {len(markets)} markets fetched",
            )
        except Exception as e:
            return self._update_component("polymarket_api", HealthStatus.UNHEALTHY, str(e))

    async def _check_websocket(self) -> ComponentHealth:
        """Check WebSocket connection status."""
        if not self.websocket_client:
            return self._update_component(
                "websocket",
                HealthStatus.UNKNOWN,
                "Client not configured",
            )

        is_connected = self.websocket_client.is_connected
        sub_count = self.websocket_client.subscription_count

        if is_connected:
            return self._update_component(
                "websocket",
                HealthStatus.HEALTHY,
                f"Connected, {sub_count} subscriptions",
                metadata={"subscription_count": sub_count},
            )
        else:
            return self._update_component(
                "websocket",
                HealthStatus.UNHEALTHY,
                "Disconnected",
            )

    async def _check_services(self) -> ComponentHealth:
        """Check systemd services status."""
        import subprocess

        services = [
            "polymarket-trader",
            "polymarket-dashboard",
            "polymarket-monitor",
        ]

        running = []
        failed = []

        for service in services:
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", service],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    running.append(service)
                else:
                    failed.append(service)
            except Exception:
                failed.append(service)

        if not failed:
            return self._update_component(
                "services",
                HealthStatus.HEALTHY,
                f"All {len(running)} services running",
                metadata={"running": running},
            )
        elif running:
            return self._update_component(
                "services",
                HealthStatus.DEGRADED,
                f"{len(failed)} services down: {', '.join(failed)}",
                metadata={"running": running, "failed": failed},
            )
        else:
            return self._update_component(
                "services",
                HealthStatus.UNHEALTHY,
                "All services down",
                metadata={"failed": failed},
            )

    async def _check_trading_activity(self) -> ComponentHealth:
        """Check recent trading activity."""
        try:
            with self.db.connection() as conn:
                # Check for recent triggers (last hour)
                row = conn.execute("""
                    SELECT COUNT(*) FROM triggers
                    WHERE created_at > datetime('now', '-1 hour')
                """).fetchone()
                recent_triggers = row[0] if row else 0

                # Check for recent orders (last day)
                row = conn.execute("""
                    SELECT COUNT(*) FROM orders
                    WHERE created_at > datetime('now', '-1 day')
                """).fetchone()
                recent_orders = row[0] if row else 0

            # Trading activity check is informational
            # No activity doesn't mean unhealthy (markets might be quiet)
            return self._update_component(
                "trading_activity",
                HealthStatus.HEALTHY,
                f"{recent_triggers} triggers/1h, {recent_orders} orders/24h",
                metadata={
                    "triggers_last_hour": recent_triggers,
                    "orders_last_day": recent_orders,
                },
            )
        except Exception as e:
            return self._update_component("trading_activity", HealthStatus.UNHEALTHY, str(e))

    def _update_component(
        self,
        name: str,
        status: HealthStatus,
        message: str,
        metadata: Optional[dict] = None,
    ) -> ComponentHealth:
        """Update component status with failure tracking."""
        now = datetime.utcnow()
        prev = self._component_status.get(name)

        if status == HealthStatus.HEALTHY:
            consecutive_failures = 0
            last_success = now
        else:
            consecutive_failures = (prev.consecutive_failures + 1) if prev else 1
            last_success = prev.last_success if prev else None

        health = ComponentHealth(
            name=name,
            status=status,
            message=message,
            last_check=now,
            last_success=last_success,
            consecutive_failures=consecutive_failures,
            metadata=metadata or {},
        )

        self._component_status[name] = health
        return health

    def _calculate_overall_status(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall system status from component statuses."""
        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.DEGRADED

    async def _send_alerts(self, components: List[ComponentHealth]) -> None:
        """Send alerts for unhealthy components."""
        for component in components:
            if component.status != HealthStatus.UNHEALTHY:
                continue

            if component.consecutive_failures < self.config.unhealthy_threshold:
                continue

            # Check cooldown
            last_alert = self._last_alert_time.get(component.name)
            if last_alert:
                cooldown = timedelta(minutes=self.config.alert_cooldown_minutes)
                if datetime.utcnow() - last_alert < cooldown:
                    continue

            # Send alert
            await self.alerter.send_alert(
                f"🚨 {component.name} is UNHEALTHY",
                f"Status: {component.status.value}\n"
                f"Message: {component.message}\n"
                f"Failures: {component.consecutive_failures}",
            )
            self._last_alert_time[component.name] = datetime.utcnow()

    def _store_health(self, components: List[ComponentHealth]) -> None:
        """Store health status in database."""
        try:
            with self.db.transaction() as conn:
                for component in components:
                    conn.execute("""
                        INSERT OR REPLACE INTO service_health
                        (service_name, status, last_check, last_success,
                         consecutive_failures, error_message, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        component.name,
                        component.status.value,
                        component.last_check.isoformat(),
                        component.last_success.isoformat() if component.last_success else None,
                        component.consecutive_failures,
                        component.message,
                        str(component.metadata),
                    ))
        except Exception as e:
            logger.warning(f"Failed to store health status: {e}")

    # ================================================================
    # HTTP Server
    # ================================================================

    async def start_server(self) -> None:
        """Start HTTP health check server."""
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/health/{component}", self._handle_component_health)
        app.router.add_get("/metrics", self._handle_metrics)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()

        logger.info(f"Health check server started on http://{self.config.host}:{self.config.port}")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle /health endpoint."""
        health = await self.check_all()
        status_code = 200 if health.is_healthy else 503

        return web.json_response(health.to_dict(), status=status_code)

    async def _handle_component_health(self, request: web.Request) -> web.Response:
        """Handle /health/{component} endpoint."""
        component_name = request.match_info["component"]

        if component_name not in self._component_status:
            return web.json_response({"error": "Component not found"}, status=404)

        component = self._component_status[component_name]
        status_code = 200 if component.status == HealthStatus.HEALTHY else 503

        return web.json_response(component.to_dict(), status=status_code)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handle /metrics endpoint (Prometheus format)."""
        lines = []

        for component in self._component_status.values():
            # Status metric (1=healthy, 0.5=degraded, 0=unhealthy)
            value = {"healthy": 1, "degraded": 0.5, "unhealthy": 0, "unknown": -1}
            lines.append(
                f'polymarket_health_status{{component="{component.name}"}} '
                f'{value.get(component.status.value, -1)}'
            )

            # Failure count
            lines.append(
                f'polymarket_health_failures{{component="{component.name}"}} '
                f'{component.consecutive_failures}'
            )

        return web.Response(text="\n".join(lines), content_type="text/plain")

    # ================================================================
    # Main Loop
    # ================================================================

    async def run(self) -> None:
        """Run health checker loop."""
        self._running = True

        # Start HTTP server
        await self.start_server()

        # Check loop
        while self._running:
            try:
                await self.check_all()
            except Exception as e:
                logger.error(f"Health check failed: {e}")

            await asyncio.sleep(self.config.check_interval_seconds)

    def stop(self) -> None:
        """Stop health checker."""
        self._running = False
```

---

## Part 2: systemd Service Definitions

### Service Files

```ini
# /home/$USER/.config/systemd/user/polymarket-trader.service
[Unit]
Description=Polymarket Trading Bot - Main Trader
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/%i/polymarket_bot
Environment=PYTHONPATH=/home/%i/polymarket_bot/src
ExecStartPre=-/usr/bin/fuser -k 5050/tcp
ExecStart=/home/%i/.conda/envs/polymarket/bin/python -m polymarket_bot.services.trader
Restart=always
RestartSec=10
StandardOutput=append:/home/%i/polymarket_bot/logs/trader.log
StandardError=append:/home/%i/polymarket_bot/logs/trader.log

[Install]
WantedBy=default.target


# /home/$USER/.config/systemd/user/polymarket-dashboard.service
[Unit]
Description=Polymarket Trading Bot - Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/%i/polymarket_bot
Environment=PYTHONPATH=/home/%i/polymarket_bot/src
ExecStartPre=-/usr/bin/fuser -k 5050/tcp
ExecStart=/home/%i/.conda/envs/polymarket/bin/python -m polymarket_bot.monitoring.dashboard
Restart=always
RestartSec=10

[Install]
WantedBy=default.target


# /home/$USER/.config/systemd/user/polymarket-monitor.service
[Unit]
Description=Polymarket Trading Bot - Position Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/%i/polymarket_bot
Environment=PYTHONPATH=/home/%i/polymarket_bot/src
ExecStart=/home/%i/.conda/envs/polymarket/bin/python -m polymarket_bot.services.position_monitor
Restart=always
RestartSec=10

[Install]
WantedBy=default.target


# /home/$USER/.config/systemd/user/polymarket-health.service
[Unit]
Description=Polymarket Trading Bot - Health Checker
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/%i/polymarket_bot
Environment=PYTHONPATH=/home/%i/polymarket_bot/src
ExecStart=/home/%i/.conda/envs/polymarket/bin/python -m polymarket_bot.monitoring.health_checker
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

### Installation Script

```bash
#!/bin/bash
# install_services.sh - Install systemd services

set -e

USER_HOME=$HOME
SERVICE_DIR="$USER_HOME/.config/systemd/user"
PROJECT_DIR="$USER_HOME/polymarket_bot"

# Create directories
mkdir -p "$SERVICE_DIR"
mkdir -p "$PROJECT_DIR/logs"

# Copy service files
cp systemd/*.service "$SERVICE_DIR/"

# Replace %i with actual username
sed -i "s|%i|$USER|g" "$SERVICE_DIR"/polymarket-*.service

# Reload systemd
systemctl --user daemon-reload

# Enable services
systemctl --user enable polymarket-trader
systemctl --user enable polymarket-dashboard
systemctl --user enable polymarket-monitor
systemctl --user enable polymarket-health

# Start services
systemctl --user start polymarket-trader
systemctl --user start polymarket-dashboard
systemctl --user start polymarket-monitor
systemctl --user start polymarket-health

echo "Services installed and started!"
echo "Check status: systemctl --user status polymarket-*"
```

### Common Operations

```bash
# Check all services
systemctl --user status polymarket-trader polymarket-dashboard polymarket-monitor polymarket-health

# View logs
journalctl --user -u polymarket-trader -f

# Restart a service
systemctl --user restart polymarket-trader

# Stop all services
systemctl --user stop polymarket-*

# Check health endpoint
curl http://localhost:5051/health
```

---

## Part 3: CLAUDE.md for Monitoring

```markdown
# Monitoring Layer

## Purpose
Monitor system health, provide dashboard, send alerts.

## Responsibilities
- Health checking all components
- HTTP health endpoint (/health)
- Prometheus metrics (/metrics)
- Web dashboard for visualization
- Telegram alerts on failures

## NOT Responsibilities
- Making trading decisions
- Executing orders
- Data storage logic

## Key Files

| File | Purpose |
|------|---------|
| `health_checker.py` | Main health check service |
| `health_types.py` | Health status types |
| `alerter.py` | Telegram/email alerts |
| `dashboard/app.py` | Flask web dashboard |

## Health Checks

| Component | What's Checked |
|-----------|----------------|
| database | SQLite connectivity |
| polymarket_api | REST API reachable |
| websocket | WebSocket connected |
| services | systemd service status |
| trading_activity | Recent triggers/orders |

## HTTP Endpoints

| Endpoint | Purpose |
|----------|---------|
| GET /health | Overall system health |
| GET /health/{name} | Single component health |
| GET /metrics | Prometheus format metrics |

## Configuration

```python
HealthCheckConfig(
    host="0.0.0.0",
    port=5051,
    check_interval_seconds=30,
    unhealthy_threshold=3,
    alert_on_unhealthy=True,
)
```

## Alert Cooldown

Alerts are rate-limited:
- Only sent after 3 consecutive failures
- 15 minute cooldown between alerts for same component
```

---

## Summary: All Specs Created

| Spec | File | Status |
|------|------|--------|
| Storage Layer | `01_STORAGE_LAYER_SPEC.md` | ✅ Complete |
| Ingestion Layer | `02_INGESTION_LAYER_SPEC.md` | ✅ Complete |
| Strategy Interface | `03_STRATEGY_INTERFACE_SPEC.md` | ✅ Complete |
| Core + Execution | `04_CORE_AND_EXECUTION_SPEC.md` | ✅ Complete |
| Health + Services | `05_HEALTH_AND_SERVICES_SPEC.md` | ✅ Complete |

Each spec includes:
- Full code implementations
- Tests
- CLAUDE.md for AI agents
- Critical gotchas from production

Ready to build! 🚀
