"""
Ingestion Layer - External data sources and API clients.

This module provides real-time data ingestion from Polymarket APIs:
    - REST client for market data, trades, and orderbooks
    - WebSocket client for real-time price updates
    - Event processor with gotcha protections (G1, G3, G5)
    - Ingestion service orchestrator
    - Dashboard for monitoring

Critical Gotchas Handled:
    - G1: Stale Trade Data (Belichick Bug) - Filter by timestamp, max 300 seconds
    - G3: WebSocket Missing Trade Size - Fetch size separately via REST
    - G5: Orderbook vs Trade Price Divergence - Verify before execution

Usage:
    from polymarket_bot.ingestion import (
        IngestionService,
        IngestionConfig,
        PolymarketRestClient,
        PolymarketWebSocket,
        PriceUpdate,
    )

    # Create and start the service
    config = IngestionConfig(dashboard_port=8080)
    service = IngestionService(config=config)
    await service.start()

    # Access metrics
    metrics = service.metrics
    health = service.health()

    # Stop gracefully
    await service.stop()
"""

# Models
from .models import (
    ErrorRecord,
    Market,
    OrderbookLevel,
    OrderbookSnapshot,
    OutcomeType,
    PriceUpdate,
    ProcessedEvent,
    TokenInfo,
    Trade,
    TradeSide,
)

# Metrics
from .metrics import (
    IngestionMetrics,
    MetricsCollector,
)

# REST Client
from .client import (
    PolymarketAPIError,
    PolymarketRestClient,
    RateLimitError,
    verify_orderbook_price,
)

# WebSocket Client
from .websocket import (
    PolymarketWebSocket,
    WebSocketState,
)

# Event Processor
from .processor import (
    EventBuffer,
    EventProcessor,
    ProcessorConfig,
    ProcessorStats,
)

# Service
from .service import (
    HealthStatus,
    IngestionConfig,
    IngestionService,
    ServiceState,
    run_ingestion_service,
)

# Dashboard (optional - requires fastapi and uvicorn)
try:
    from .dashboard import (
        create_dashboard_app,
        run_dashboard,
    )
    _DASHBOARD_AVAILABLE = True
except ImportError:
    create_dashboard_app = None  # type: ignore
    run_dashboard = None  # type: ignore
    _DASHBOARD_AVAILABLE = False


__all__ = [
    # Models
    "ErrorRecord",
    "Market",
    "OrderbookLevel",
    "OrderbookSnapshot",
    "OutcomeType",
    "PriceUpdate",
    "ProcessedEvent",
    "TokenInfo",
    "Trade",
    "TradeSide",
    # Metrics
    "IngestionMetrics",
    "MetricsCollector",
    # REST Client
    "PolymarketAPIError",
    "PolymarketRestClient",
    "RateLimitError",
    "verify_orderbook_price",
    # WebSocket
    "PolymarketWebSocket",
    "WebSocketState",
    # Processor
    "EventBuffer",
    "EventProcessor",
    "ProcessorConfig",
    "ProcessorStats",
    # Service
    "HealthStatus",
    "IngestionConfig",
    "IngestionService",
    "ServiceState",
    "run_ingestion_service",
    # Dashboard
    "create_dashboard_app",
    "run_dashboard",
]
