"""
Health Checker for component health monitoring.

Monitors health of database, WebSocket, and balance with configurable thresholds.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health check result for a single component."""

    component: str
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None


@dataclass
class AggregateHealth:
    """Overall system health."""

    status: HealthStatus
    components: List[ComponentHealth] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HealthChecker:
    """
    Checks health of system components.

    Monitors:
    - Database connectivity
    - WebSocket connection and message staleness
    - Balance thresholds
    - Position limits

    Usage:
        checker = HealthChecker(db, websocket_client, clob_client)

        # Check single component
        health = await checker.check_database()

        # Check all components
        overall = await checker.check_all()
    """

    def __init__(
        self,
        db: Optional["Database"] = None,
        websocket_client: Optional[Any] = None,
        clob_client: Optional[Any] = None,
        message_staleness_threshold: float = 300.0,  # 5 minutes
        min_balance_threshold: Decimal = Decimal("100"),
    ) -> None:
        """
        Initialize the health checker.

        Args:
            db: Database connection to check
            websocket_client: WebSocket client to check
            clob_client: CLOB client for balance checks
            message_staleness_threshold: Seconds without messages to consider stale
            min_balance_threshold: Minimum balance for healthy status
        """
        self.db = db
        self._websocket_client = websocket_client
        self._clob_client = clob_client
        self._message_staleness_threshold = message_staleness_threshold
        self._min_balance_threshold = min_balance_threshold

    async def check_database(self) -> ComponentHealth:
        """
        Check database connectivity.

        Returns:
            ComponentHealth with status
        """
        start_time = time.time()

        try:
            if self.db is None:
                return ComponentHealth(
                    component="database",
                    status=HealthStatus.UNHEALTHY,
                    message="No database connection configured",
                )

            # Try a simple query
            await self.db.execute("SELECT 1")

            latency_ms = (time.time() - start_time) * 1000

            return ComponentHealth(
                component="database",
                status=HealthStatus.HEALTHY,
                message="Database is accessible",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                component="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def check_websocket(self) -> ComponentHealth:
        """
        Check WebSocket connection and message staleness.

        Returns:
            ComponentHealth with status
        """
        if self._websocket_client is None:
            return ComponentHealth(
                component="websocket",
                status=HealthStatus.WARNING,
                message="No WebSocket client configured",
            )

        # Check connection status
        is_connected = getattr(self._websocket_client, "is_connected", False)
        if not is_connected:
            return ComponentHealth(
                component="websocket",
                status=HealthStatus.UNHEALTHY,
                message="WebSocket is disconnected",
            )

        # Check message staleness
        last_message_time = getattr(self._websocket_client, "last_message_time", None)
        if last_message_time:
            now = datetime.now(timezone.utc)
            if isinstance(last_message_time, datetime):
                age_seconds = (now - last_message_time).total_seconds()
            else:
                age_seconds = now.timestamp() - last_message_time

            if age_seconds > self._message_staleness_threshold:
                return ComponentHealth(
                    component="websocket",
                    status=HealthStatus.DEGRADED,
                    message=f"WebSocket messages are stale ({age_seconds:.0f}s old)",
                )

        return ComponentHealth(
            component="websocket",
            status=HealthStatus.HEALTHY,
            message="WebSocket is connected and receiving messages",
        )

    async def check_balance(
        self,
        min_balance: Optional[Decimal] = None,
    ) -> ComponentHealth:
        """
        Check USDC balance.

        Args:
            min_balance: Minimum balance threshold (default from config)

        Returns:
            ComponentHealth with status
        """
        if min_balance is None:
            min_balance = self._min_balance_threshold

        if self._clob_client is None:
            return ComponentHealth(
                component="balance",
                status=HealthStatus.WARNING,
                message="No CLOB client configured for balance check",
            )

        try:
            result = self._clob_client.get_balance()
            balance = Decimal(str(result.get("USDC", "0")))

            if balance >= min_balance:
                return ComponentHealth(
                    component="balance",
                    status=HealthStatus.HEALTHY,
                    message=f"Balance is ${balance:.2f}",
                )
            else:
                return ComponentHealth(
                    component="balance",
                    status=HealthStatus.WARNING,
                    message=f"Low balance: ${balance:.2f} (min: ${min_balance:.2f})",
                )

        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return ComponentHealth(
                component="balance",
                status=HealthStatus.UNHEALTHY,
                message=f"Balance check error: {str(e)}",
            )

    async def check_all(self, timeout: float = 5.0) -> AggregateHealth:
        """
        Check all components with timeout.

        Args:
            timeout: Maximum time for all checks in seconds

        Returns:
            AggregateHealth with all component results
        """
        components = []

        # Run checks with timeout
        checks = [
            ("database", self.check_database),
            ("websocket", self.check_websocket),
            ("balance", self.check_balance),
        ]

        for name, check_func in checks:
            try:
                result = await asyncio.wait_for(
                    check_func(),
                    timeout=timeout / len(checks),
                )
                components.append(result)
            except asyncio.TimeoutError:
                components.append(ComponentHealth(
                    component=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"{name} check timed out",
                ))
            except Exception as e:
                components.append(ComponentHealth(
                    component=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"{name} check failed: {str(e)}",
                ))

        # Determine overall status
        overall_status = self._calculate_overall_status(components)

        return AggregateHealth(
            status=overall_status,
            components=components,
        )

    def _calculate_overall_status(
        self,
        components: List[ComponentHealth],
    ) -> HealthStatus:
        """Calculate overall status from component statuses."""
        statuses = [c.status for c in components]

        # Any UNHEALTHY -> overall UNHEALTHY
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY

        # Any DEGRADED or WARNING -> overall DEGRADED
        if HealthStatus.DEGRADED in statuses or HealthStatus.WARNING in statuses:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY
