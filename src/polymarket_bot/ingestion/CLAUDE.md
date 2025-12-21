# Ingestion Layer

## You Are

A **TDD developer** implementing the ingestion layer of a Polymarket trading bot. You write tests first, then implement code to pass them. You understand that this component is part of a larger system, but your focus is on this directory only.

**Critical**: This layer interacts with external APIs. All tests MUST mock HTTP/WebSocket calls. Never hit real APIs in tests.

## Broader System Context

This is a **strategy-agnostic trading bot framework** for Polymarket prediction markets. The architecture:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  INGESTION  │────▶│    CORE     │────▶│  EXECUTION  │
│ (API data)  │     │ (orchestr.) │     │  (orders)   │
└─────────────┘     └─────────────┘     └─────────────┘
      ↑
  YOU ARE HERE
      │
┌─────────────┐
│   STORAGE   │  ← Already implemented
└─────────────┘
```

**Your component's role**: Fetch data from Polymarket APIs (REST and WebSocket), normalize it, and provide it to other components. You handle the unpredictable external world.

## Dependencies (What You Import)

```python
# From storage layer (ALREADY IMPLEMENTED)
from polymarket_bot.storage import (
    Database,
    DatabaseConfig,
    PolymarketTrade,
    PolymarketTokenMeta,
    TradeWatermark,
    TradeRepository,
    TradeWatermarkRepository,
    TokenMetaRepository,
)

# External libraries (in pyproject.toml)
import aiohttp          # Async HTTP client
import websockets       # WebSocket client

# Standard library
import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, AsyncIterator
```

## Public Interface (What You Must Export)

Other components will import from you. Your `__init__.py` must export:

```python
# REST API client
PolymarketClient      # Fetches markets, orderbooks, trades

# WebSocket client
WebSocketClient       # Real-time price streaming
PriceUpdate           # Data class for price events

# Trade fetching with staleness protection
TradeFetcher          # Fetches trades with G1 protection
fetch_recent_trades   # Convenience function

# Metadata synchronization
MetadataSync          # Keeps token metadata in sync

# Orderbook verification
verify_orderbook_price  # G5 protection - verify before execute
```

## Relevant Gotchas (CRITICAL - These Caused Production Bugs)

### G1: Stale Trade Data - "Belichick Bug" (CRITICAL FOR YOU)

Polymarket's "recent trades" API returns trades that may be **MONTHS old** for low-volume markets. We executed at 95¢ based on a 2-month-old trade when the actual market was at 5¢.

```python
# WRONG - trusts API's definition of "recent"
async def get_trades(self, token_id: str):
    response = await self.client.get(f"/trades?token_id={token_id}")
    return response.json()  # May contain 60-day-old trades!

# RIGHT - explicitly filter by timestamp
async def get_recent_trades(
    self,
    token_id: str,
    max_age_seconds: int = 300  # 5 minutes default
) -> list[Trade]:
    response = await self.client.get(f"/trades?token_id={token_id}")
    trades = response.json()

    now = time.time()
    cutoff = now - max_age_seconds

    return [
        t for t in trades
        if t["timestamp"] / 1000 > cutoff  # API uses milliseconds
    ]
```

**You MUST have tests that verify old trades are filtered out.**

### G3: WebSocket Missing Trade Size (CRITICAL FOR YOU)

WebSocket price updates do NOT include trade size. The size filter (>= 50) is critical for win rate.

```python
# WebSocket message (NO SIZE!):
{"type": "price_change", "asset_id": "0x...", "price": "0.95"}

# You MUST fetch size separately via REST:
size = await client.fetch_trade_size_at_price(token_id, price, max_age_seconds=60)
```

**You MUST document this limitation and provide a REST fallback method.**

### G5: Orderbook vs Trade Price Divergence (CRITICAL FOR YOU)

Spike trades can show 95¢ while the orderbook is actually at 5¢. Before executing, the core layer will call your verification function.

```python
async def verify_orderbook_price(
    self,
    token_id: str,
    expected_price: Decimal,
    max_deviation: Decimal = Decimal("0.10")
) -> tuple[bool, Decimal, str]:
    """
    Returns (is_valid, actual_best_bid, reason).

    is_valid = True if |best_bid - expected_price| <= max_deviation
    """
    orderbook = await self.fetch_orderbook(token_id)
    best_bid = Decimal(orderbook["bids"][0]["price"]) if orderbook["bids"] else Decimal("0")

    deviation = abs(best_bid - expected_price)
    is_valid = deviation <= max_deviation

    reason = "" if is_valid else f"Orderbook {best_bid} vs expected {expected_price}"
    return is_valid, best_bid, reason
```

## Directory Structure

```
ingestion/
├── __init__.py              # Public exports (update this)
├── CLAUDE.md                # This file
├── polymarket_client.py     # REST API client
├── websocket_client.py      # WebSocket streaming
├── trade_fetcher.py         # Trade fetching with staleness filter
├── metadata_sync.py         # Token metadata synchronization
├── orderbook.py             # Orderbook fetching and verification
└── tests/
    ├── __init__.py
    ├── conftest.py          # Mock fixtures for APIs
    ├── test_polymarket_client.py
    ├── test_websocket_client.py
    ├── test_trade_fetcher.py
    ├── test_metadata_sync.py
    └── test_orderbook.py
```

## Implementation Order (TDD)

Build in this order. For each file: **write tests first**, then implement.

1. `polymarket_client.py` + tests - Basic REST client (markets, tokens)
2. `trade_fetcher.py` + tests - Trade fetching with G1 staleness filter
3. `orderbook.py` + tests - Orderbook fetching with G5 verification
4. `websocket_client.py` + tests - WebSocket streaming (note G3 limitation)
5. `metadata_sync.py` + tests - Token metadata sync to database

## Key Specifications

### PolymarketClient

```python
class PolymarketClient:
    """REST API client for Polymarket Gamma and CLOB APIs."""

    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"

    async def fetch_active_markets(self) -> list[Market]: ...
    async def fetch_market(self, condition_id: str) -> Optional[Market]: ...
    async def fetch_orderbook(self, token_id: str) -> Orderbook: ...
    async def fetch_trades(self, token_id: str, limit: int = 100) -> list[Trade]: ...
```

### TradeFetcher (G1 Protection)

```python
class TradeFetcher:
    """Fetches trades with staleness protection."""

    def __init__(self, client: PolymarketClient, max_age_seconds: int = 300):
        self.client = client
        self.max_age_seconds = max_age_seconds

    async def fetch_recent_trades(self, token_id: str) -> list[Trade]:
        """Returns only trades within max_age_seconds."""
        ...

    async def fetch_trade_size_at_price(
        self,
        token_id: str,
        target_price: Decimal,
        price_tolerance: Decimal = Decimal("0.01")
    ) -> Optional[Decimal]:
        """
        Find the size of a recent trade near target_price.
        Used to get trade size that WebSocket doesn't provide (G3).
        """
        ...
```

### WebSocketClient

```python
@dataclass
class PriceUpdate:
    """Price update from WebSocket."""
    token_id: str
    price: Decimal
    timestamp: datetime
    # NOTE: size is NOT available from WebSocket (G3)

class WebSocketClient:
    """WebSocket client for real-time price updates."""

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    async def connect(self) -> None: ...
    async def subscribe(self, token_ids: list[str]) -> None: ...
    async def receive(self) -> PriceUpdate: ...
    async def close(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...
```

### Orderbook Verification (G5 Protection)

```python
async def verify_orderbook_price(
    client: PolymarketClient,
    token_id: str,
    expected_price: Decimal,
    max_deviation: Decimal = Decimal("0.10")
) -> tuple[bool, Decimal, str]:
    """
    Verify orderbook price matches expected price within tolerance.

    CRITICAL: Always call this before executing trades.
    Prevents buying at spike price when orderbook is elsewhere.

    Returns:
        (is_valid, actual_best_bid, reason_if_invalid)
    """
```

## Test Fixtures (conftest.py)

```python
"""Ingestion layer test fixtures. ALL API CALLS MUST BE MOCKED."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import time

@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession."""
    session = AsyncMock()
    return session

@pytest.fixture
def sample_trades_with_stale():
    """Trades response including STALE data for G1 testing."""
    now = time.time()
    return [
        # Fresh trade (10 seconds ago) - SHOULD BE INCLUDED
        {
            "id": "trade_fresh",
            "price": "0.95",
            "size": "75",
            "side": "BUY",
            "timestamp": int((now - 10) * 1000),
        },
        # Stale trade (60 days ago) - MUST BE FILTERED OUT
        {
            "id": "trade_stale",
            "price": "0.95",
            "size": "4.2",
            "side": "BUY",
            "timestamp": int((now - 86400 * 60) * 1000),
        },
    ]

@pytest.fixture
def sample_orderbook():
    """Standard orderbook response."""
    return {
        "bids": [
            {"price": "0.94", "size": "150"},
            {"price": "0.93", "size": "200"},
        ],
        "asks": [
            {"price": "0.96", "size": "100"},
            {"price": "0.97", "size": "250"},
        ],
    }

@pytest.fixture
def divergent_orderbook():
    """Orderbook with price FAR from 0.95 - for G5 testing."""
    return {
        "bids": [
            {"price": "0.05", "size": "1000"},  # Way off from 0.95!
        ],
        "asks": [
            {"price": "0.06", "size": "1000"},
        ],
    }

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value='{"type":"price_change","asset_id":"0x123","price":"0.95"}')
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws
```

## Critical Test Cases

### G1: Stale Trade Filtering (MUST PASS)

```python
async def test_filters_out_stale_trades(trade_fetcher, sample_trades_with_stale):
    """
    REGRESSION TEST: Belichick Bug

    API returns 'recent' trades that are actually months old.
    We MUST filter by timestamp.
    """
    # Mock returns both fresh and stale trades
    trade_fetcher.client.fetch_trades = AsyncMock(return_value=sample_trades_with_stale)

    trades = await trade_fetcher.fetch_recent_trades("tok_123", max_age_seconds=300)

    # Only fresh trade should be returned
    assert len(trades) == 1
    assert trades[0]["id"] == "trade_fresh"

async def test_returns_empty_when_all_stale(trade_fetcher):
    """Should return empty list when all trades are too old."""
    stale_only = [{
        "id": "old",
        "price": "0.95",
        "timestamp": int((time.time() - 86400 * 30) * 1000),  # 30 days old
    }]
    trade_fetcher.client.fetch_trades = AsyncMock(return_value=stale_only)

    trades = await trade_fetcher.fetch_recent_trades("tok_123", max_age_seconds=300)

    assert trades == []
```

### G5: Orderbook Verification (MUST PASS)

```python
async def test_rejects_divergent_orderbook(client, divergent_orderbook):
    """
    REGRESSION TEST: Spike trade at 95c when orderbook is at 5c.

    Must reject execution when orderbook doesn't match trigger.
    """
    client.fetch_orderbook = AsyncMock(return_value=divergent_orderbook)

    is_valid, actual_price, reason = await verify_orderbook_price(
        client,
        token_id="tok_123",
        expected_price=Decimal("0.95"),
        max_deviation=Decimal("0.10")
    )

    assert is_valid is False
    assert actual_price == Decimal("0.05")
    assert "0.05" in reason and "0.95" in reason
```

### G3: WebSocket Size Limitation (Document and Test)

```python
async def test_websocket_message_lacks_size(websocket_client):
    """
    GOTCHA DOCUMENTATION: WebSocket does NOT provide trade size.

    The size filter (>= 50) is critical for win rate.
    Users MUST call fetch_trade_size_at_price() separately.
    """
    update = await websocket_client.receive()

    # Size should be None or not present
    assert not hasattr(update, 'size') or update.size is None
```

## Running Tests

```bash
# From this directory or project root
pytest tests/ -v

# Specific test file
pytest tests/test_trade_fetcher.py -v

# Belichick bug regression tests
pytest -k "stale" -v

# Orderbook verification tests
pytest -k "orderbook" -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing
```

## Database Usage

You write to the storage layer for caching/persistence:

```python
# Saving fetched trades
async def save_trades(self, trades: list[Trade], db: Database):
    repo = TradeRepository(db)
    for trade in trades:
        await repo.upsert(trade)

# Tracking watermarks (last processed timestamp per condition)
async def update_watermark(self, condition_id: str, timestamp: int, db: Database):
    repo = TradeWatermarkRepository(db)
    await repo.update(condition_id, timestamp)
```

## Definition of Done

- [ ] PolymarketClient fetches markets, orderbooks, trades
- [ ] TradeFetcher filters trades by age (G1 fix)
- [ ] G1 regression test passes (60-day-old trade filtered)
- [ ] verify_orderbook_price rejects divergent prices (G5 fix)
- [ ] G5 regression test passes (5c orderbook vs 95c trigger)
- [ ] WebSocketClient connects and receives price updates
- [ ] G3 limitation documented (no size in WebSocket)
- [ ] fetch_trade_size_at_price provides REST fallback for size
- [ ] MetadataSync updates token metadata in database
- [ ] All HTTP/WebSocket calls are mocked in tests
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Coverage > 85%
- [ ] `__init__.py` exports all public interface items

## Notes for Claude

- You are working in `/workspace/src/polymarket_bot/ingestion/`
- Storage layer is already implemented - import and use it
- ALL external API calls must be mocked in tests
- The three gotchas (G1, G3, G5) are your primary concerns
- Use `aiohttp` for HTTP, `websockets` for WebSocket
- Polymarket uses millisecond timestamps in their API

---

## Implementation Notes (Post-Codex Review)

### Retry Logic for 5xx Errors Fix

**Problem:** The original code caught any `PolymarketAPIError` with `status >= 400` in a generic `Exception` handler, causing HTTP 5xx errors and timeouts to fail immediately instead of retrying.

**Solution:** Added explicit handling in `client.py`:

```python
except asyncio.CancelledError:
    # CRITICAL FIX: Re-raise CancelledError to allow graceful shutdown
    logger.debug("Request cancelled")
    raise

except PolymarketAPIError as e:
    # 5xx errors should be retried, 4xx should not
    if e.status_code and e.status_code >= 500:
        delay = self._retry_delay * (2 ** attempt)
        await asyncio.sleep(delay)
        last_error = e
    else:
        raise  # 4xx client errors - don't retry
```

### WebSocket Reconnect Fix

**Problem:** Timeout triggered reconnect without closing the socket, potentially leaking connections.

**Solution:** Close socket before reconnecting in `websocket.py`:

```python
except asyncio.TimeoutError:
    logger.warning(f"No message received in {self._heartbeat_timeout}s, reconnecting...")
    # FIX: Close socket before breaking to avoid resource leak
    if self._ws:
        try:
            await self._ws.close()
        except Exception:
            pass
        self._ws = None
    break
```

### Lock During I/O Fix

**Problem:** `EventProcessor` held `_lock` while awaiting REST I/O, serializing all event processing.

**Solution:** Restructured to only lock during shared state updates in `processor.py`:

```python
async def process_price_update(self, update: PriceUpdate) -> ProcessedEvent:
    # Phase 1: Record receipt (minimal lock)
    async with self._lock:
        self._stats.total_processed += 1

    # Phase 2: I/O operations WITHOUT holding lock
    if self._config.backfill_missing_size:
        size = await self._backfill_size(update)  # No lock!

    # Phase 3: Update stats (lock needed)
    async with self._lock:
        if result.g3_backfilled:
            self._stats.g3_backfilled += 1
        self._recent_events.append(result)
```

### Tests Added

- `TestConcurrentProcessing` - Tests for lock-during-I/O fix
- Tests verify concurrent processing is faster than sequential
