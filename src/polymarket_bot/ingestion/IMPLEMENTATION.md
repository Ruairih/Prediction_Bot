# Ingestion Layer Implementation Plan

## Overview

This document describes the rock-solid ingestion service with live dashboard for the Polymarket trading bot.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION SERVICE                             │
│                                                                  │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐          │
│  │ WebSocket  │────▶│   Event    │────▶│  Storage   │          │
│  │  Client    │     │ Processor  │     │   Writer   │          │
│  └────────────┘     └────────────┘     └────────────┘          │
│        │                  │                   │                 │
│        │            ┌─────▼─────┐             │                 │
│        │            │  Metrics  │             │                 │
│        │            │ Collector │             │                 │
│        │            └─────┬─────┘             │                 │
│        ▼                  ▼                   ▼                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Supervisor (auto-restart, health)           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│  ════════════════════════════╪══════════════════════════════   │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Dashboard (FastAPI + HTML + WebSocket)         │   │
│  │                                                          │   │
│  │   GET  /              → Live dashboard UI                │   │
│  │   GET  /api/status    → Health + connection state        │   │
│  │   GET  /api/metrics   → Ingestion stats                  │   │
│  │   GET  /api/events    → Recent events (paginated)        │   │
│  │   WS   /ws/live       → Real-time event stream           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                         Port 8080                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
src/polymarket_bot/ingestion/
├── __init__.py              # Public API exports
├── CLAUDE.md                # TDD spec (existing)
├── IMPLEMENTATION.md        # This file
├── models.py                # PriceUpdate, Trade, Market, OrderbookSnapshot
├── client.py                # REST client (markets, trades, orderbook)
├── websocket.py             # WebSocket client (reconnect, heartbeat)
├── processor.py             # Event processing + G1/G3/G5 filters
├── service.py               # Main IngestionService orchestrator
├── metrics.py               # MetricsCollector dataclass
├── dashboard.py             # FastAPI app + routes
├── templates/
│   └── index.html           # Dashboard UI (Jinja2)
└── tests/
    ├── conftest.py          # Fixtures, mocked APIs
    ├── test_client.py       # REST client tests
    ├── test_websocket.py    # WebSocket + reconnect tests
    ├── test_processor.py    # G1/G3/G5 filter tests
    ├── test_service.py      # Service lifecycle tests
    └── test_dashboard.py    # API endpoint tests
```

---

## Component Specifications

### 1. models.py - Data Structures

```python
@dataclass
class PriceUpdate:
    """Real-time price update from WebSocket."""
    token_id: str
    price: Decimal
    timestamp: datetime
    condition_id: Optional[str] = None
    # NOTE: size NOT available from WebSocket (G3)

@dataclass
class Trade:
    """Trade from REST API."""
    id: str
    token_id: str
    price: Decimal
    size: Decimal
    side: str  # "BUY" or "SELL"
    timestamp: datetime
    condition_id: Optional[str] = None

@dataclass
class Market:
    """Market metadata."""
    condition_id: str
    question: str
    slug: str
    end_date: datetime
    tokens: list[TokenInfo]
    active: bool

@dataclass
class OrderbookSnapshot:
    """Orderbook state at a point in time."""
    token_id: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    timestamp: datetime

    @property
    def best_bid(self) -> Optional[Decimal]: ...

    @property
    def best_ask(self) -> Optional[Decimal]: ...
```

### 2. metrics.py - Metrics Collection

```python
@dataclass
class IngestionMetrics:
    """Tracks ingestion service health and performance."""
    # Connection state
    websocket_connected: bool = False
    websocket_connected_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    reconnection_count: int = 0
    subscribed_markets: int = 0

    # Data flow (rolling 5-minute window)
    events_received: int = 0
    events_per_second: float = 0.0
    trades_stored: int = 0
    price_updates: int = 0

    # Data quality (G1/G3/G5)
    g1_stale_filtered: int = 0
    g3_missing_size: int = 0
    g3_size_backfilled: int = 0
    g5_divergence_detected: int = 0
    average_trade_age_seconds: float = 0.0

    # Errors
    errors_last_hour: list[ErrorRecord] = field(default_factory=list)

class MetricsCollector:
    """Thread-safe metrics collection with rolling windows."""
    def record_event(self, event_type: str): ...
    def record_error(self, error: Exception): ...
    def record_g1_filter(self): ...
    def record_g5_divergence(self): ...
    def get_metrics(self) -> IngestionMetrics: ...
```

### 3. client.py - REST API Client

```python
class PolymarketRestClient:
    """Async REST client for Polymarket APIs."""

    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        rate_limit: float = 10.0,  # requests per second
        timeout: float = 30.0,
    ): ...

    # Market data
    async def get_markets(self, active_only: bool = True) -> list[Market]: ...
    async def get_market(self, condition_id: str) -> Optional[Market]: ...

    # Trade data (G1 protection built-in)
    async def get_trades(
        self,
        token_id: str,
        max_age_seconds: int = 300,  # G1: Default 5 minutes
        limit: int = 100,
    ) -> list[Trade]: ...

    async def get_trade_size_at_price(
        self,
        token_id: str,
        target_price: Decimal,
        tolerance: Decimal = Decimal("0.01"),
        max_age_seconds: int = 60,
    ) -> Optional[Decimal]: ...  # G3: REST fallback for size

    # Orderbook
    async def get_orderbook(self, token_id: str) -> OrderbookSnapshot: ...

    async def verify_price(
        self,
        token_id: str,
        expected_price: Decimal,
        max_deviation: Decimal = Decimal("0.10"),
    ) -> tuple[bool, Decimal, str]: ...  # G5 protection
```

### 4. websocket.py - WebSocket Client

```python
class WebSocketState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"

class PolymarketWebSocket:
    """
    Resilient WebSocket client with auto-reconnect.

    Features:
    - Exponential backoff reconnection (1s -> 2s -> 4s -> ... -> 60s max)
    - Heartbeat monitoring (reconnect if no message > 30s)
    - Subscription persistence across reconnects
    - Event callbacks for state changes
    """

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        on_price_update: Callable[[PriceUpdate], Awaitable[None]],
        on_state_change: Optional[Callable[[WebSocketState], Awaitable[None]]] = None,
        heartbeat_timeout: float = 30.0,
        max_reconnect_delay: float = 60.0,
    ): ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self, token_ids: list[str]) -> None: ...
    async def unsubscribe(self, token_ids: list[str]) -> None: ...

    @property
    def state(self) -> WebSocketState: ...

    @property
    def subscribed_tokens(self) -> set[str]: ...
```

### 5. processor.py - Event Processing

```python
class EventProcessor:
    """
    Processes incoming events with gotcha protections.

    Responsibilities:
    - Parse raw WebSocket messages
    - Apply G1 staleness filter
    - Backfill G3 missing size via REST
    - Flag G5 price divergences
    - Route valid events to storage
    """

    def __init__(
        self,
        rest_client: PolymarketRestClient,
        trade_repo: TradeRepository,
        metrics: MetricsCollector,
        max_trade_age_seconds: int = 300,
    ): ...

    async def process_price_update(self, update: PriceUpdate) -> ProcessResult: ...
    async def process_trade(self, trade: Trade) -> ProcessResult: ...

    def is_stale(self, timestamp: datetime) -> bool: ...  # G1
    async def backfill_size(self, update: PriceUpdate) -> Optional[Decimal]: ...  # G3
    async def verify_price(self, token_id: str, price: Decimal) -> bool: ...  # G5

@dataclass
class ProcessResult:
    """Result of processing an event."""
    accepted: bool
    stored: bool
    reason: Optional[str] = None
    g1_filtered: bool = False
    g3_backfilled: bool = False
    g5_divergence: bool = False
```

### 6. service.py - Main Service

```python
class IngestionService:
    """
    Main ingestion service orchestrator.

    Features:
    - Manages WebSocket + REST clients
    - Supervisor pattern for component failures
    - Graceful startup/shutdown
    - Health monitoring
    """

    def __init__(
        self,
        db: Database,
        config: IngestionConfig,
    ): ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> HealthStatus: ...

    @property
    def metrics(self) -> IngestionMetrics: ...

    @property
    def is_running(self) -> bool: ...

@dataclass
class IngestionConfig:
    """Configuration for ingestion service."""
    # WebSocket
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    heartbeat_timeout: float = 30.0
    max_reconnect_delay: float = 60.0

    # REST API
    rate_limit: float = 10.0
    request_timeout: float = 30.0

    # Processing
    max_trade_age_seconds: int = 300  # G1
    price_deviation_max: Decimal = Decimal("0.10")  # G5

    # Dashboard
    dashboard_port: int = 8080
    dashboard_host: str = "0.0.0.0"

@dataclass
class HealthStatus:
    """Overall service health."""
    healthy: bool
    uptime_seconds: float
    websocket_state: WebSocketState
    last_event_age_seconds: Optional[float]
    database_connected: bool
    errors_last_hour: int
    details: dict[str, Any]
```

### 7. dashboard.py - FastAPI Dashboard

```python
def create_dashboard_app(service: IngestionService) -> FastAPI:
    """Create FastAPI app for ingestion dashboard."""

    app = FastAPI(title="Polymarket Ingestion Monitor")

    @app.get("/")
    async def dashboard(): ...  # Renders HTML template

    @app.get("/api/status")
    async def status() -> HealthStatus: ...

    @app.get("/api/metrics")
    async def metrics() -> IngestionMetrics: ...

    @app.get("/api/events")
    async def events(limit: int = 50, offset: int = 0) -> list[Event]: ...

    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket): ...

    return app
```

---

## Reliability Features

| Feature | Implementation |
|---------|----------------|
| **Auto-reconnect** | Exponential backoff: 1s → 2s → 4s → ... → 60s max |
| **Heartbeat monitor** | Detect dead connections (no message > 30s = reconnect) |
| **Graceful shutdown** | SIGTERM handler, clean disconnect, flush pending |
| **Error isolation** | One bad event doesn't crash the service |
| **Idempotent processing** | Watermarks prevent duplicate storage |
| **Health endpoint** | `/api/status` for Docker healthcheck |
| **Supervisor pattern** | Component-level restart without full service restart |
| **Structured logging** | JSON logs with correlation IDs |

---

## Docker Integration

### Exposed Ports
- **8080**: Dashboard (already configured in docker-compose.yml)

### Health Check
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/api/status"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Running the Service
```bash
# Inside container
python -m polymarket_bot.ingestion.service

# Or via main entry point
python -m polymarket_bot.main --ingestion-only
```

---

## Gotcha Protection Summary

| Gotcha | Protection | Location |
|--------|------------|----------|
| **G1: Stale Trades** | Filter trades > 300s old | `client.py`, `processor.py` |
| **G3: Missing Size** | REST backfill when WebSocket lacks size | `processor.py` |
| **G5: Price Divergence** | Verify orderbook before flagging trades | `client.py`, `processor.py` |

---

## Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────┐
│  POLYMARKET INGESTION                      Running 2h 34m    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CONNECTION                        DATA FLOW (5 min window)     │
│  ┌─────────────────────┐          ┌─────────────────────────┐   │
│  │ WebSocket: Connected│          │ Events:     1,247       │   │
│  │ Last msg:  0.3s ago │          │ Rate:       4.2/sec     │   │
│  │ Reconnects: 0       │          │ Trades:     892 stored  │   │
│  │ Markets:   147      │          │ Updates:    355         │   │
│  └─────────────────────┘          └─────────────────────────┘   │
│                                                                  │
│  DATA QUALITY                      GOTCHA PROTECTION            │
│  ┌─────────────────────┐          ┌─────────────────────────┐   │
│  │ Avg trade age: 12s  │          │ G1 Stale:   23 blocked  │   │
│  │ Freshness:   98.2%  │          │ G3 No-size: 7 backfilled│   │
│  │ Coverage:   147/150 │          │ G5 Diverge: 0 flagged   │   │
│  └─────────────────────┘          └─────────────────────────┘   │
│                                                                  │
│  LIVE EVENTS                                    [auto-updating] │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 18:42:31 │ BTC > 100k by Dec │ YES │ 0.67→0.68 │ 250 shares ││
│  │ 18:42:30 │ Trump wins 2024   │ YES │ 0.52→0.52 │ 100 shares ││
│  │ 18:42:28 │ ETH > 5k by Jan   │ NO  │ 0.23→0.24 │ 500 shares ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ERRORS (last hour): None                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Build Order

1. **models.py** - Data structures (no dependencies)
2. **metrics.py** - Metrics collection (depends on models)
3. **client.py** - REST client (depends on models)
4. **websocket.py** - WebSocket client (depends on models)
5. **processor.py** - Event processing (depends on client, models, storage)
6. **service.py** - Orchestrator (depends on all above)
7. **dashboard.py** - FastAPI app (depends on service)
8. **templates/index.html** - Dashboard UI
9. **tests/** - Comprehensive test suite

---

## Estimated Lines of Code

| File | Lines | Purpose |
|------|-------|---------|
| models.py | ~150 | Data structures |
| metrics.py | ~200 | Metrics collection |
| client.py | ~350 | REST API client |
| websocket.py | ~400 | WebSocket client |
| processor.py | ~250 | Event processing |
| service.py | ~300 | Service orchestrator |
| dashboard.py | ~200 | FastAPI routes |
| index.html | ~250 | Dashboard UI |
| tests/* | ~800 | Test suite |
| **Total** | **~2,900** | |

---

## Success Criteria

- [ ] WebSocket connects and receives price updates
- [ ] Auto-reconnects on disconnect with exponential backoff
- [ ] G1: Stale trades (> 300s) are filtered
- [ ] G3: Missing sizes are backfilled via REST
- [ ] G5: Price divergences are detected and flagged
- [ ] Dashboard shows live data at http://localhost:8080
- [ ] All metrics visible and updating in real-time
- [ ] Service handles errors gracefully without crashing
- [ ] All tests pass with > 85% coverage
- [ ] Docker healthcheck works
