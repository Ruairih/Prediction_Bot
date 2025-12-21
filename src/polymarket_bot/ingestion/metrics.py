"""
Metrics collection for the ingestion service.

Provides thread-safe metrics collection with rolling time windows
for tracking ingestion health and data quality.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .models import ErrorRecord


@dataclass
class IngestionMetrics:
    """
    Snapshot of ingestion service health and performance.

    This is an immutable snapshot - use MetricsCollector to track
    metrics over time.
    """
    # Connection state
    websocket_connected: bool = False
    websocket_connected_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    reconnection_count: int = 0
    subscribed_markets: int = 0

    # Data flow (from rolling window)
    events_received: int = 0
    events_per_second: float = 0.0
    trades_stored: int = 0
    price_updates_received: int = 0

    # Data quality (G1/G3/G5)
    g1_stale_filtered: int = 0
    g3_missing_size: int = 0
    g3_size_backfilled: int = 0
    g5_divergence_detected: int = 0
    average_trade_age_seconds: float = 0.0
    freshness_percentage: float = 100.0

    # Errors
    errors_last_hour: int = 0
    recent_errors: list[ErrorRecord] = field(default_factory=list)

    # Uptime
    started_at: Optional[datetime] = None
    uptime_seconds: float = 0.0

    @property
    def last_message_age_seconds(self) -> Optional[float]:
        """Seconds since last message received."""
        if self.last_message_at is None:
            return None
        now = datetime.now(timezone.utc)
        return (now - self.last_message_at).total_seconds()

    @property
    def is_healthy(self) -> bool:
        """Quick health check based on metrics."""
        if not self.websocket_connected:
            return False
        if self.last_message_age_seconds and self.last_message_age_seconds > 60:
            return False
        if self.errors_last_hour > 100:
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "websocket_connected": self.websocket_connected,
            "websocket_connected_at": self.websocket_connected_at.isoformat() if self.websocket_connected_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_message_age_seconds": self.last_message_age_seconds,
            "reconnection_count": self.reconnection_count,
            "subscribed_markets": self.subscribed_markets,
            "events_received": self.events_received,
            "events_per_second": round(self.events_per_second, 2),
            "trades_stored": self.trades_stored,
            "price_updates_received": self.price_updates_received,
            "g1_stale_filtered": self.g1_stale_filtered,
            "g3_missing_size": self.g3_missing_size,
            "g3_size_backfilled": self.g3_size_backfilled,
            "g5_divergence_detected": self.g5_divergence_detected,
            "average_trade_age_seconds": round(self.average_trade_age_seconds, 1),
            "freshness_percentage": round(self.freshness_percentage, 1),
            "errors_last_hour": self.errors_last_hour,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_seconds": round(self.uptime_seconds, 0),
            "is_healthy": self.is_healthy,
        }


class MetricsCollector:
    """
    Thread-safe metrics collection with rolling time windows.

    Tracks events over configurable time windows (default 5 minutes)
    to compute rates and averages.

    Usage:
        collector = MetricsCollector()
        collector.start()

        # Record events as they happen
        collector.record_price_update()
        collector.record_trade_stored(age_seconds=12.5)
        collector.record_g1_filter()

        # Get current metrics snapshot
        metrics = collector.get_metrics()
        print(f"Events/sec: {metrics.events_per_second}")
    """

    def __init__(
        self,
        window_seconds: float = 300.0,  # 5 minute window
        max_errors: int = 100,  # Keep last N errors
    ):
        self._window_seconds = window_seconds
        self._max_errors = max_errors

        # Connection state
        self._websocket_connected = False
        self._websocket_connected_at: Optional[datetime] = None
        self._last_message_at: Optional[datetime] = None
        self._reconnection_count = 0
        self._subscribed_markets = 0

        # Rolling window data (timestamp, value)
        self._events: deque[float] = deque()
        self._price_updates: deque[float] = deque()
        self._trades_stored: deque[tuple[float, float]] = deque()  # (timestamp, age)

        # Gotcha counters (rolling window)
        self._g1_filters: deque[float] = deque()
        self._g3_missing: deque[float] = deque()
        self._g3_backfilled: deque[float] = deque()
        self._g5_divergences: deque[float] = deque()

        # Error tracking
        self._errors: deque[ErrorRecord] = deque(maxlen=max_errors)

        # Uptime
        self._started_at: Optional[datetime] = None

        # Lock for thread safety
        self._lock = asyncio.Lock()

    def start(self) -> None:
        """Mark the service as started."""
        self._started_at = datetime.now(timezone.utc)

    def stop(self) -> None:
        """Mark the service as stopped."""
        self._websocket_connected = False

    def _now(self) -> float:
        """Current time as Unix timestamp."""
        return time.time()

    def _prune_old(self, dq: deque, cutoff: float) -> None:
        """Remove entries older than cutoff."""
        while dq and (isinstance(dq[0], tuple) and dq[0][0] < cutoff or
                      isinstance(dq[0], float) and dq[0] < cutoff):
            dq.popleft()

    def _prune_all(self) -> None:
        """Prune all rolling windows."""
        cutoff = self._now() - self._window_seconds
        self._prune_old(self._events, cutoff)
        self._prune_old(self._price_updates, cutoff)
        self._prune_old(self._trades_stored, cutoff)
        self._prune_old(self._g1_filters, cutoff)
        self._prune_old(self._g3_missing, cutoff)
        self._prune_old(self._g3_backfilled, cutoff)
        self._prune_old(self._g5_divergences, cutoff)

    # Connection state updates

    def set_websocket_connected(self, connected: bool) -> None:
        """Update WebSocket connection state."""
        self._websocket_connected = connected
        if connected:
            self._websocket_connected_at = datetime.now(timezone.utc)
        else:
            self._reconnection_count += 1

    def set_subscribed_markets(self, count: int) -> None:
        """Update number of subscribed markets."""
        self._subscribed_markets = count

    def record_message_received(self) -> None:
        """Record that a message was received."""
        self._last_message_at = datetime.now(timezone.utc)

    # Event recording

    def record_price_update(self) -> None:
        """Record a price update event."""
        now = self._now()
        self._events.append(now)
        self._price_updates.append(now)
        self._last_message_at = datetime.now(timezone.utc)

    def record_trade_stored(self, age_seconds: float) -> None:
        """Record a trade that was stored."""
        now = self._now()
        self._events.append(now)
        self._trades_stored.append((now, age_seconds))
        self._last_message_at = datetime.now(timezone.utc)

    def record_g1_filter(self) -> None:
        """Record a trade filtered for staleness (G1)."""
        self._g1_filters.append(self._now())

    def record_g3_missing_size(self) -> None:
        """Record a price update missing size (G3)."""
        self._g3_missing.append(self._now())

    def record_g3_backfill(self) -> None:
        """Record a successful size backfill (G3)."""
        self._g3_backfilled.append(self._now())

    def record_g5_divergence(self) -> None:
        """Record a price divergence detection (G5)."""
        self._g5_divergences.append(self._now())

    def record_error(
        self,
        error_type: str,
        message: str,
        component: str,
        token_id: Optional[str] = None,
        recoverable: bool = True,
    ) -> None:
        """Record an error."""
        self._errors.append(ErrorRecord(
            timestamp=datetime.now(timezone.utc),
            error_type=error_type,
            message=message,
            component=component,
            token_id=token_id,
            recoverable=recoverable,
        ))

    # Metrics retrieval

    def get_metrics(self) -> IngestionMetrics:
        """Get current metrics snapshot."""
        self._prune_all()

        now = self._now()
        window = self._window_seconds

        # Calculate events per second
        event_count = len(self._events)
        events_per_second = event_count / window if window > 0 else 0.0

        # Calculate average trade age
        trade_ages = [age for _, age in self._trades_stored]
        avg_trade_age = sum(trade_ages) / len(trade_ages) if trade_ages else 0.0

        # Calculate freshness (trades not filtered by G1)
        total_trades = len(self._trades_stored) + len(self._g1_filters)
        freshness = (len(self._trades_stored) / total_trades * 100) if total_trades > 0 else 100.0

        # Count errors in last hour
        hour_ago = now - 3600
        errors_last_hour = sum(1 for e in self._errors if e.timestamp.timestamp() > hour_ago)

        # Uptime
        uptime = 0.0
        if self._started_at:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        return IngestionMetrics(
            websocket_connected=self._websocket_connected,
            websocket_connected_at=self._websocket_connected_at,
            last_message_at=self._last_message_at,
            reconnection_count=self._reconnection_count,
            subscribed_markets=self._subscribed_markets,
            events_received=event_count,
            events_per_second=events_per_second,
            trades_stored=len(self._trades_stored),
            price_updates_received=len(self._price_updates),
            g1_stale_filtered=len(self._g1_filters),
            g3_missing_size=len(self._g3_missing),
            g3_size_backfilled=len(self._g3_backfilled),
            g5_divergence_detected=len(self._g5_divergences),
            average_trade_age_seconds=avg_trade_age,
            freshness_percentage=freshness,
            errors_last_hour=errors_last_hour,
            recent_errors=list(self._errors)[-10:],  # Last 10 errors
            started_at=self._started_at,
            uptime_seconds=uptime,
        )

    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        self._events.clear()
        self._price_updates.clear()
        self._trades_stored.clear()
        self._g1_filters.clear()
        self._g3_missing.clear()
        self._g3_backfilled.clear()
        self._g5_divergences.clear()
        self._errors.clear()
        self._reconnection_count = 0
        self._websocket_connected = False
        self._websocket_connected_at = None
        self._last_message_at = None
        self._started_at = None
