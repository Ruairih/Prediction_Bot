"""
Main ingestion service orchestrator.

Manages the complete ingestion pipeline:
    - WebSocket client for real-time updates
    - REST client for data fetching and backfill
    - Event processor with G1/G3/G5 protections
    - Metrics collection
    - Health monitoring

Features:
    - Graceful startup/shutdown
    - Component supervision (restart on failure)
    - Health endpoint for Docker healthcheck
    - Signal handling (SIGTERM, SIGINT)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Union

from .client import PolymarketRestClient
from .metrics import IngestionMetrics, MetricsCollector
from .models import PriceUpdate
from .processor import EventProcessor, ProcessorConfig
from .websocket import PolymarketWebSocket, WebSocketState

logger = logging.getLogger(__name__)


class ServiceState(str, Enum):
    """Service lifecycle state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass
class IngestionConfig:
    """Configuration for the ingestion service."""

    # WebSocket settings
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    heartbeat_timeout: float = 30.0
    max_reconnect_delay: float = 60.0

    # REST API settings
    rate_limit: float = 10.0
    request_timeout: float = 30.0
    max_retries: int = 3

    # Processing settings
    max_trade_age_seconds: int = 300  # G1
    backfill_missing_size: bool = True  # G3
    check_price_divergence: bool = True  # G5
    max_price_deviation: Decimal = Decimal("0.10")  # G5

    # Dashboard settings
    dashboard_enabled: bool = True
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080

    # Market subscription
    subscribe_all_markets: bool = False
    initial_token_ids: list[str] = field(default_factory=list)

    # Health check
    max_message_age_seconds: float = 60.0


@dataclass
class HealthStatus:
    """Overall service health status."""
    healthy: bool
    state: ServiceState
    uptime_seconds: float
    websocket_state: WebSocketState
    websocket_connected: bool
    last_message_age_seconds: Optional[float]
    database_connected: bool
    errors_last_hour: int
    subscribed_markets: int
    events_per_second: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "healthy": self.healthy,
            "state": self.state.value,
            "uptime_seconds": round(self.uptime_seconds, 0),
            "websocket": {
                "state": self.websocket_state.value,
                "connected": self.websocket_connected,
                "last_message_age_seconds": (
                    round(self.last_message_age_seconds, 1)
                    if self.last_message_age_seconds else None
                ),
                "subscribed_markets": self.subscribed_markets,
            },
            "database_connected": self.database_connected,
            "errors_last_hour": self.errors_last_hour,
            "events_per_second": round(self.events_per_second, 2),
            "details": self.details,
        }


# Type alias for event callbacks (supports both sync and async)
EventCallback = Callable[[PriceUpdate], Any]  # Returns None or Awaitable[None]


class IngestionService:
    """
    Main ingestion service orchestrator.

    Manages the complete pipeline: WebSocket -> Processor -> Storage

    Usage:
        config = IngestionConfig(
            dashboard_port=8080,
            subscribe_all_markets=True,
        )

        service = IngestionService(config=config)

        # Start the service
        await service.start()

        # Check health
        health = service.health()
        print(f"Healthy: {health.healthy}")

        # Get metrics
        metrics = service.metrics

        # Stop gracefully
        await service.stop()
    """

    def __init__(
        self,
        config: Optional[IngestionConfig] = None,
        on_price_update: Optional[EventCallback] = None,
    ):
        """
        Initialize the ingestion service.

        Args:
            config: Service configuration
            on_price_update: Optional callback for price updates
        """
        self._config = config or IngestionConfig()
        self._external_callback = on_price_update

        # State
        self._state = ServiceState.STOPPED
        self._started_at: Optional[datetime] = None
        self._stop_event = asyncio.Event()

        # Components (created on start)
        self._rest_client: Optional[PolymarketRestClient] = None
        self._websocket: Optional[PolymarketWebSocket] = None
        self._processor: Optional[EventProcessor] = None
        self._metrics: Optional[MetricsCollector] = None

        # Dashboard app (created if enabled)
        self._dashboard_app = None
        self._dashboard_task: Optional[asyncio.Task] = None

        # Market data
        self._markets_cache: dict[str, Any] = {}
        self._token_to_market: dict[str, str] = {}

    @property
    def state(self) -> ServiceState:
        """Current service state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Whether the service is running."""
        return self._state == ServiceState.RUNNING

    @property
    def metrics(self) -> Optional[IngestionMetrics]:
        """Get current metrics snapshot."""
        if self._metrics:
            return self._metrics.get_metrics()
        return None

    @property
    def processor(self) -> Optional[EventProcessor]:
        """Get the event processor."""
        return self._processor

    @property
    def websocket(self) -> Optional[PolymarketWebSocket]:
        """Get the WebSocket client."""
        return self._websocket

    @property
    def rest_client(self) -> Optional[PolymarketRestClient]:
        """Get the REST client."""
        return self._rest_client

    async def start(self) -> None:
        """
        Start the ingestion service.

        This will:
        1. Initialize all components
        2. Connect to WebSocket
        3. Start the dashboard (if enabled)
        4. Subscribe to markets
        """
        if self._state != ServiceState.STOPPED:
            logger.warning(f"Cannot start: already in state {self._state.value}")
            return

        logger.info("Starting ingestion service...")
        self._state = ServiceState.STARTING
        self._started_at = datetime.now(timezone.utc)
        self._stop_event.clear()

        try:
            # Initialize metrics
            self._metrics = MetricsCollector()
            self._metrics.start()

            # Initialize REST client
            self._rest_client = PolymarketRestClient(
                rate_limit=self._config.rate_limit,
                timeout=self._config.request_timeout,
                max_retries=self._config.max_retries,
            )
            await self._rest_client.__aenter__()

            # Initialize processor
            processor_config = ProcessorConfig(
                max_trade_age_seconds=self._config.max_trade_age_seconds,
                backfill_missing_size=self._config.backfill_missing_size,
                check_price_divergence=self._config.check_price_divergence,
                max_price_deviation=self._config.max_price_deviation,
            )
            self._processor = EventProcessor(
                rest_client=self._rest_client,
                metrics=self._metrics,
                config=processor_config,
            )

            # Initialize WebSocket
            self._websocket = PolymarketWebSocket(
                on_price_update=self._handle_price_update,
                on_state_change=self._handle_ws_state_change,
                on_error=self._handle_ws_error,
                heartbeat_timeout=self._config.heartbeat_timeout,
                max_reconnect_delay=self._config.max_reconnect_delay,
                url=self._config.websocket_url,
            )

            # Fetch initial market data first (needed for subscribe_all)
            await self._refresh_markets()

            # Update processor with market lookup for question display
            if self._processor:
                self._processor.set_market_lookup(
                    self._markets_cache,
                    self._token_to_market,
                )

            # Start WebSocket
            await self._websocket.start()

            # Subscribe to markets
            if self._config.subscribe_all_markets:
                # Get all token IDs from fetched markets
                all_token_ids = list(self._token_to_market.keys())
                if all_token_ids:
                    logger.info(f"Subscribing to {len(all_token_ids)} tokens from {len(self._markets_cache)} markets")
                    # Chunk subscriptions to avoid payload limits (100 tokens per chunk)
                    chunk_size = 100
                    for i in range(0, len(all_token_ids), chunk_size):
                        chunk = all_token_ids[i:i + chunk_size]
                        await self._websocket.subscribe(chunk)
                        logger.debug(f"Subscribed to chunk {i // chunk_size + 1} ({len(chunk)} tokens)")
                else:
                    logger.warning("No token IDs available for subscription")
            elif self._config.initial_token_ids:
                await self._websocket.subscribe(self._config.initial_token_ids)

            # Start dashboard if enabled
            if self._config.dashboard_enabled:
                await self._start_dashboard()

            self._state = ServiceState.RUNNING
            logger.info("Ingestion service started successfully")

            # Setup signal handlers
            self._setup_signal_handlers()

        except Exception as e:
            logger.error(f"Failed to start ingestion service: {e}")
            self._state = ServiceState.FAILED
            await self._cleanup()
            raise

    async def stop(self) -> None:
        """
        Stop the ingestion service gracefully.

        This will:
        1. Signal all tasks to stop
        2. Close WebSocket connection
        3. Close REST client
        4. Stop the dashboard
        """
        if self._state in (ServiceState.STOPPED, ServiceState.STOPPING):
            return

        logger.info("Stopping ingestion service...")
        self._state = ServiceState.STOPPING
        self._stop_event.set()

        await self._cleanup()

        if self._metrics:
            self._metrics.stop()

        self._state = ServiceState.STOPPED
        logger.info("Ingestion service stopped")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        # Stop WebSocket
        if self._websocket:
            try:
                await self._websocket.stop()
            except Exception as e:
                logger.warning(f"Error stopping WebSocket: {e}")
            self._websocket = None

        # Close REST client
        if self._rest_client:
            try:
                await self._rest_client.close()
            except Exception as e:
                logger.warning(f"Error closing REST client: {e}")
            self._rest_client = None

        # Stop dashboard
        if self._dashboard_task:
            self._dashboard_task.cancel()
            try:
                await self._dashboard_task
            except asyncio.CancelledError:
                pass
            self._dashboard_task = None

    def health(self) -> HealthStatus:
        """
        Get current health status.

        Returns:
            HealthStatus indicating overall service health
        """
        metrics = self._metrics.get_metrics() if self._metrics else None

        # Calculate uptime
        uptime = 0.0
        if self._started_at:
            uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        # Determine WebSocket state
        ws_state = WebSocketState.DISCONNECTED
        ws_connected = False
        last_msg_age = None
        subscribed = 0

        if self._websocket:
            ws_state = self._websocket.state
            ws_connected = self._websocket.is_connected
            subscribed = len(self._websocket.subscribed_tokens)
            if self._websocket.last_message_time:
                last_msg_age = (
                    asyncio.get_event_loop().time() -
                    self._websocket.last_message_time
                )

        # Determine health
        healthy = True
        details = {}

        if self._state != ServiceState.RUNNING:
            healthy = False
            details["reason"] = f"Service not running: {self._state.value}"

        elif not ws_connected:
            healthy = False
            details["reason"] = "WebSocket not connected"

        elif last_msg_age and last_msg_age > self._config.max_message_age_seconds:
            healthy = False
            details["reason"] = f"No messages for {last_msg_age:.1f}s"

        return HealthStatus(
            healthy=healthy,
            state=self._state,
            uptime_seconds=uptime,
            websocket_state=ws_state,
            websocket_connected=ws_connected,
            last_message_age_seconds=last_msg_age,
            database_connected=True,  # TODO: Check DB connection
            errors_last_hour=metrics.errors_last_hour if metrics else 0,
            subscribed_markets=subscribed,
            events_per_second=metrics.events_per_second if metrics else 0.0,
            details=details,
        )

    async def subscribe(self, token_ids: list[str]) -> None:
        """
        Subscribe to price updates for tokens.

        Args:
            token_ids: List of token IDs to subscribe to
        """
        if self._websocket:
            await self._websocket.subscribe(token_ids)
            if self._metrics:
                self._metrics.set_subscribed_markets(
                    len(self._websocket.subscribed_tokens)
                )

    async def unsubscribe(self, token_ids: list[str]) -> None:
        """
        Unsubscribe from price updates.

        Args:
            token_ids: List of token IDs to unsubscribe from
        """
        if self._websocket:
            await self._websocket.unsubscribe(token_ids)
            if self._metrics:
                self._metrics.set_subscribed_markets(
                    len(self._websocket.subscribed_tokens)
                )

    async def _handle_price_update(self, update: PriceUpdate) -> None:
        """Handle incoming price update from WebSocket."""
        if self._metrics:
            self._metrics.record_message_received()

        # Process through the pipeline
        if self._processor:
            result = await self._processor.process_price_update(update)

            # Log significant events
            if result.g5_flagged:
                logger.warning(
                    f"G5: Price divergence flagged for {update.token_id} "
                    f"@ {update.price}"
                )

        # Call external callback if provided (supports both sync and async)
        if self._external_callback:
            try:
                result = self._external_callback(update)
                # Await if the callback returns any awaitable (coroutine, Task, Future)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.error(f"Error in external callback: {e}")

    async def _handle_ws_state_change(self, state: WebSocketState) -> None:
        """Handle WebSocket state changes."""
        if self._metrics:
            self._metrics.set_websocket_connected(state == WebSocketState.CONNECTED)

        if state == WebSocketState.CONNECTED:
            logger.info("WebSocket connected")
        elif state == WebSocketState.RECONNECTING:
            logger.warning("WebSocket reconnecting...")
        elif state == WebSocketState.DISCONNECTED:
            logger.warning("WebSocket disconnected")

    async def _handle_ws_error(self, error: Exception) -> None:
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {error}")
        if self._metrics:
            self._metrics.record_error(
                error_type=type(error).__name__,
                message=str(error),
                component="websocket",
            )

    async def _refresh_markets(self) -> None:
        """Fetch and cache market data with pagination."""
        if not self._rest_client:
            return

        try:
            self._markets_cache.clear()
            self._token_to_market.clear()

            # Paginate through all markets
            offset = 0
            limit = 100
            total_fetched = 0

            while True:
                markets = await self._rest_client.get_markets(
                    active_only=True,
                    limit=limit,
                    offset=offset,
                )

                if not markets:
                    break

                for market in markets:
                    self._markets_cache[market.condition_id] = market
                    for token in market.tokens:
                        self._token_to_market[token.token_id] = market.condition_id

                total_fetched += len(markets)

                # If we got fewer than limit, we've reached the end
                if len(markets) < limit:
                    break

                offset += limit

                # Safety limit to prevent infinite loops
                if total_fetched >= 10000:
                    logger.warning("Reached market fetch limit (10000)")
                    break

            logger.info(f"Fetched {total_fetched} active markets")

        except Exception as e:
            logger.error(f"Failed to refresh markets: {e}")

    async def _start_dashboard(self) -> None:
        """Start the dashboard server in the background."""
        try:
            # Import lazily to avoid requiring dashboard dependencies if not used
            from .dashboard import create_dashboard_app

            import uvicorn

            self._dashboard_app = create_dashboard_app(self)

            # Configure uvicorn
            config = uvicorn.Config(
                self._dashboard_app,
                host=self._config.dashboard_host,
                port=self._config.dashboard_port,
                log_level="warning",
            )
            server = uvicorn.Server(config)

            # Run in background task
            self._dashboard_task = asyncio.create_task(server.serve())
            logger.info(
                f"Dashboard started at http://{self._config.dashboard_host}:"
                f"{self._config.dashboard_port}"
            )

        except ImportError as e:
            logger.warning(
                f"Dashboard dependencies not installed: {e}. "
                "Install with: pip install polymarket-bot[dashboard]"
            )
        except Exception as e:
            logger.error(f"Failed to start dashboard: {e}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig):
            logger.info(f"Received signal {sig}, initiating shutdown...")
            asyncio.create_task(self.stop())

        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    async def run_forever(self) -> None:
        """
        Run the service until stopped.

        This is useful for running as a standalone service.
        """
        await self.start()

        try:
            # Wait until stop event is set
            await self._stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()


async def run_ingestion_service(config: Optional[IngestionConfig] = None) -> None:
    """
    Run the ingestion service as a standalone process.

    Args:
        config: Optional service configuration
    """
    service = IngestionService(config=config)
    await service.run_forever()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Run the service
    asyncio.run(run_ingestion_service())
