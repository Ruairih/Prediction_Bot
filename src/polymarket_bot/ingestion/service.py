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
import time
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

# Import for token metadata persistence
try:
    from polymarket_bot.storage import TokenMetaRepository, PolymarketTokenMeta
    HAS_TOKEN_META = True
except ImportError:
    HAS_TOKEN_META = False

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

    # Startup performance: limit initial market fetch to avoid blocking startup
    # for 30+ seconds. UniverseUpdater handles full market discovery.
    startup_market_limit: int = 2000  # Fetch first 2000 markets on startup (20 API calls ~6s)


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
        db: Optional[Any] = None,
    ):
        """
        Initialize the ingestion service.

        Args:
            config: Service configuration
            on_price_update: Optional callback for price updates
            db: Optional database reference for health checking
        """
        self._config = config or IngestionConfig()
        self._external_callback = on_price_update
        self._db = db

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

        # Background market fetch task (for remaining markets after startup)
        self._background_market_task: Optional[asyncio.Task] = None

        # Market data
        self._markets_cache: dict[str, Any] = {}
        self._token_to_market: dict[str, str] = {}
        self._initial_fetch_complete = False  # Track if startup fetch hit limit

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

            # If subscribe_all_markets is True, launch background task to
            # fetch and subscribe to remaining markets (runs even if startup
            # limit=0 or errors occurred - allows recovery)
            if self._config.subscribe_all_markets:
                self._background_market_task = asyncio.create_task(
                    self._background_fetch_remaining_markets()
                )
                logger.info("Started background task for remaining market subscriptions")

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
        # Cancel background market fetch task
        if self._background_market_task:
            self._background_market_task.cancel()
            try:
                await self._background_market_task
            except asyncio.CancelledError:
                pass
            self._background_market_task = None

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
                    time.time() -
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
            database_connected=self._db.is_connected if self._db else True,
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

    async def _refresh_markets(self) -> int:
        """
        Fetch and cache market data with pagination.

        Uses startup_market_limit to avoid blocking startup for 30+ seconds.
        Background task handles remaining markets if limit is hit.

        Returns:
            The offset where fetching stopped (for background continuation)
        """
        if not self._rest_client:
            return 0

        self._initial_fetch_complete = False

        try:
            self._markets_cache.clear()
            self._token_to_market.clear()

            # Paginate through markets up to startup limit
            offset = 0
            limit = 100
            total_fetched = 0
            startup_limit = max(0, self._config.startup_market_limit)  # Ensure non-negative
            start_time = asyncio.get_event_loop().time()

            # Allow skipping fetch entirely if limit is 0
            if startup_limit == 0:
                logger.info("Startup market fetch disabled (limit=0)")
                return 0

            logger.info(f"Fetching markets (limit: {startup_limit})...")

            while True:
                # Check if shutdown requested
                if self._stop_event.is_set():
                    logger.info("Market refresh aborted: shutdown requested")
                    break

                # Calculate how many more we need (enforce limit strictly)
                remaining = startup_limit - total_fetched
                if remaining <= 0:
                    self._initial_fetch_complete = True
                    logger.info(
                        f"Reached startup limit ({startup_limit}). "
                        "Background task will fetch remaining markets."
                    )
                    break

                fetch_limit = min(limit, remaining)

                markets = await self._rest_client.get_markets(
                    active_only=True,
                    limit=fetch_limit,
                    offset=offset,
                )

                if not markets:
                    break

                for market in markets:
                    self._markets_cache[market.condition_id] = market
                    for token in market.tokens:
                        self._token_to_market[token.token_id] = market.condition_id

                # Persist token metadata to database for dashboard access
                await self._save_token_metadata(markets)

                total_fetched += len(markets)
                offset += len(markets)

                # Progress logging every 500 markets
                if total_fetched % 500 == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.debug(f"  ... {total_fetched} markets fetched ({elapsed:.1f}s)")

                # If we got fewer than requested, we've reached the end
                if len(markets) < fetch_limit:
                    break

            elapsed = asyncio.get_event_loop().time() - start_time
            token_count = len(self._token_to_market)
            logger.info(
                f"Fetched {total_fetched} markets ({token_count} tokens) in {elapsed:.1f}s"
            )
            return offset

        except asyncio.CancelledError:
            logger.info("Market refresh cancelled")
            raise
        except Exception as e:
            logger.error(f"Failed to refresh markets: {e}")
            return 0

    async def _background_fetch_remaining_markets(self) -> None:
        """
        Background task to fetch remaining markets after startup.

        Continues from where _refresh_markets() stopped and subscribes
        to new tokens incrementally.
        """
        if not self._rest_client or not self._websocket:
            return

        # Start from where startup fetch ended
        offset = len(self._markets_cache)
        limit = 100
        total_fetched = 0
        new_tokens: list[str] = []
        start_time = asyncio.get_event_loop().time()

        logger.info(f"Background: fetching remaining markets from offset {offset}...")

        try:
            while not self._stop_event.is_set():
                markets = await self._rest_client.get_markets(
                    active_only=True,
                    limit=limit,
                    offset=offset,
                )

                if not markets:
                    break

                new_markets = []
                for market in markets:
                    if market.condition_id not in self._markets_cache:
                        self._markets_cache[market.condition_id] = market
                        new_markets.append(market)
                        for token in market.tokens:
                            if token.token_id not in self._token_to_market:
                                self._token_to_market[token.token_id] = market.condition_id
                                new_tokens.append(token.token_id)

                # Persist token metadata for new markets
                if new_markets:
                    await self._save_token_metadata(new_markets)

                total_fetched += len(markets)
                offset += len(markets)

                # Subscribe to new tokens in chunks
                # Note: WebSocket.subscribe() queues tokens for reconnect, so we
                # call it even if disconnected to ensure no tokens are lost
                if len(new_tokens) >= 100 and self._websocket:
                    await self._websocket.subscribe(new_tokens[:100])
                    logger.debug(f"Background: subscribed to {len(new_tokens[:100])} new tokens")
                    new_tokens = new_tokens[100:]

                # Progress logging every 1000 markets
                if total_fetched % 1000 == 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.info(f"Background: {total_fetched} additional markets fetched ({elapsed:.1f}s)")

                # If we got fewer than limit, we've reached the end
                if len(markets) < limit:
                    break

                # Safety limit
                if total_fetched >= 10000:
                    logger.warning("Background: reached safety limit (10000 additional markets)")
                    break

            # Subscribe to any remaining tokens
            # Note: WebSocket.subscribe() queues tokens for reconnect
            if new_tokens and self._websocket:
                await self._websocket.subscribe(new_tokens)
                logger.debug(f"Background: subscribed to final {len(new_tokens)} tokens")

            elapsed = asyncio.get_event_loop().time() - start_time
            total_markets = len(self._markets_cache)
            total_tokens = len(self._token_to_market)
            logger.info(
                f"Background: completed. Total: {total_markets} markets, "
                f"{total_tokens} tokens ({elapsed:.1f}s)"
            )

        except asyncio.CancelledError:
            logger.info("Background market fetch cancelled")
            raise
        except Exception as e:
            logger.error(f"Background market fetch failed: {e}")

    async def _save_token_metadata(self, markets: list) -> None:
        """
        Persist token metadata to database for dashboard access.

        This ensures the polymarket_token_meta table is populated,
        which is required for the dashboard's manual order feature
        to display tokens for a selected market.
        """
        if not HAS_TOKEN_META:
            logger.debug("TokenMetaRepository not available, skipping token persistence")
            return

        if not self._db:
            logger.debug("No database connection, skipping token persistence")
            return

        try:
            from polymarket_bot.ingestion.models import OutcomeType

            repo = TokenMetaRepository(self._db)
            tokens_saved = 0

            for market in markets:
                for idx, token in enumerate(market.tokens):
                    # Map OutcomeType to outcome_index and string
                    if token.outcome == OutcomeType.YES:
                        outcome_index = 0
                        outcome_str = "Yes"
                    elif token.outcome == OutcomeType.NO:
                        outcome_index = 1
                        outcome_str = "No"
                    else:
                        outcome_index = idx
                        outcome_str = str(token.outcome.value) if hasattr(token.outcome, 'value') else str(token.outcome)

                    meta = PolymarketTokenMeta(
                        token_id=token.token_id,
                        condition_id=market.condition_id,
                        market_id=market.condition_id,
                        outcome_index=outcome_index,
                        outcome=outcome_str,
                        question=market.question,
                        fetched_at=datetime.now(timezone.utc).isoformat(),
                    )

                    await repo.upsert(meta)
                    tokens_saved += 1

            if tokens_saved > 0:
                logger.debug(f"Persisted {tokens_saved} token metadata records")

        except Exception as e:
            # Don't fail the service if token persistence fails
            logger.warning(f"Failed to persist token metadata: {e}")

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
