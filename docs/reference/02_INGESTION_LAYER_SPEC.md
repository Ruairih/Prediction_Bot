# Ingestion Layer Specification

## Overview

The Ingestion Layer handles all data retrieval from Polymarket's APIs. It provides a clean interface for the rest of the system to fetch market data, prices, and trades.

**Responsibilities:**
- REST API client (Gamma, CLOB, Data APIs)
- WebSocket streaming client
- Market metadata synchronization
- Historical trade fetching
- Rate limiting and retries

**Does NOT:**
- Make trading decisions
- Store data (that's Storage Layer's job)
- Execute orders (that's Execution Layer's job)

---

## Directory Structure

```
src/polymarket_bot/ingestion/
├── CLAUDE.md                    # Component AI context
├── __init__.py                  # Public exports
├── types.py                     # Data types (Market, Token, Trade, etc.)
├── polymarket_client.py         # REST API wrapper
├── websocket_client.py          # WebSocket streaming
├── metadata_sync.py             # Market metadata synchronization
├── trade_fetcher.py             # Historical trade fetching
└── tests/
    ├── __init__.py
    ├── conftest.py              # Fixtures (mock responses)
    ├── test_polymarket_client.py
    ├── test_websocket_client.py
    ├── test_metadata_sync.py
    └── test_trade_fetcher.py
```

---

## 1. Data Types

### `types.py`

```python
"""
Data types for Polymarket API responses.

All types are Pydantic models for validation and serialization.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Side(str, Enum):
    """Trade side."""
    BUY = "buy"
    SELL = "sell"


class TokenOutcome(str, Enum):
    """Common token outcomes."""
    YES = "Yes"
    NO = "No"
    OVER = "Over"
    UNDER = "Under"


# ============================================================
# API Response Models
# ============================================================

class MarketResponse(BaseModel):
    """Market from Gamma API."""
    condition_id: str
    question: str
    description: Optional[str] = None
    category: Optional[str] = None
    slug: Optional[str] = None

    # Note: Polymarket's category field is often None for newer markets.
    # Use detect_category() for reliable categorization.

    end_date_iso: Optional[str] = Field(None, alias="endDateIso")
    game_start_time: Optional[str] = Field(None, alias="gameStartTime")
    created_at: Optional[str] = Field(None, alias="createdAt")

    closed: bool = False
    archived: bool = False

    volume: Optional[float] = None
    liquidity: Optional[float] = None

    tokens: List["TokenResponse"] = []

    @property
    def scheduled_end(self) -> Optional[str]:
        """Best estimate of when market ends."""
        return self.end_date_iso or self.game_start_time


class TokenResponse(BaseModel):
    """Token from Gamma API."""
    token_id: str
    outcome: str
    winner: Optional[bool] = None


class TradeResponse(BaseModel):
    """Trade from Data API."""
    id: Optional[str] = None
    asset: str  # token_id
    market: Optional[str] = None  # condition_id (sometimes missing!)

    price: float
    size: float
    side: Side

    # Timestamp handling - API uses different field names
    timestamp: Optional[int] = None
    match_time: Optional[int] = None
    created_at: Optional[str] = None

    @property
    def unix_timestamp(self) -> int:
        """Get Unix timestamp from whichever field is available."""
        if self.timestamp:
            return self.timestamp
        if self.match_time:
            return self.match_time
        if self.created_at:
            try:
                dt = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
                return int(dt.timestamp())
            except ValueError:
                pass
        return 0

    @property
    def is_stale(self) -> bool:
        """
        Check if trade is stale (older than 5 minutes).

        CRITICAL: The Polymarket API returns "recent" trades that may be
        MONTHS old for low-volume markets. Always check this!
        """
        import time
        age = time.time() - self.unix_timestamp
        return age > 300  # 5 minutes


class OrderBookLevel(BaseModel):
    """Single level in orderbook."""
    price: Decimal
    size: Decimal


class OrderBook(BaseModel):
    """Orderbook from CLOB API."""
    market: str  # condition_id
    asset_id: str  # token_id
    bids: List[OrderBookLevel] = []
    asks: List[OrderBookLevel] = []
    timestamp: Optional[int] = None

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Midpoint between best bid and ask."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> Optional[Decimal]:
        """Bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None


# ============================================================
# WebSocket Message Types
# ============================================================

class PriceUpdate(BaseModel):
    """Price update from WebSocket."""
    asset_id: str  # token_id
    price: Decimal
    timestamp: int

    # NOTE: WebSocket does NOT include trade size!
    # Must fetch from REST API separately.


class WebSocketMessage(BaseModel):
    """Raw WebSocket message."""
    channel: Optional[str] = None
    type: Optional[str] = None
    data: Optional[dict] = None
    price_changes: Optional[List[dict]] = None
```

---

## 2. REST API Client

### `polymarket_client.py`

```python
"""
Polymarket REST API client.

Provides unified access to:
- Gamma API (market metadata)
- CLOB API (orderbook, trading)
- Data API (historical trades)

CRITICAL GOTCHAS:
1. Trade data can be months old - always check timestamps
2. Category field is often None - use keyword detection
3. Some markets have multiple token_ids for same condition_id
4. Rate limits vary by endpoint
"""
from __future__ import annotations

import hashlib
import logging
import time
from decimal import Decimal
from typing import List, Optional

import httpx
from pydantic import BaseModel

from .types import (
    MarketResponse,
    OrderBook,
    OrderBookLevel,
    Side,
    TradeResponse,
)

logger = logging.getLogger(__name__)


class PolymarketClientConfig(BaseModel):
    """Configuration for Polymarket API client."""
    # API endpoints
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    data_base_url: str = "https://data-api.polymarket.com"

    # Request settings
    timeout: float = 10.0
    max_retries: int = 3
    retry_backoff: float = 1.0  # Base backoff in seconds

    # Rate limiting
    requests_per_second: float = 10.0  # Conservative default


class PolymarketClient:
    """
    Unified REST API client for Polymarket.

    Usage:
        client = PolymarketClient(PolymarketClientConfig())

        # Get markets
        markets = await client.get_markets(active=True)

        # Get orderbook
        book = await client.get_orderbook(token_id)

        # Get recent trades (with freshness check!)
        trades = await client.get_recent_trades(
            condition_id,
            max_age_seconds=300,  # Only last 5 minutes
        )
    """

    def __init__(self, config: PolymarketClientConfig) -> None:
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = 1.0 / self.config.requests_per_second
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with retry logic."""
        client = await self._get_client()

        last_error = None
        for attempt in range(self.config.max_retries):
            await self._rate_limit()

            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:  # Rate limited
                    wait = self.config.retry_backoff * (2 ** attempt)
                    logger.warning(f"Rate limited, waiting {wait}s")
                    await asyncio.sleep(wait)
                elif e.response.status_code >= 500:  # Server error
                    wait = self.config.retry_backoff * (2 ** attempt)
                    logger.warning(f"Server error {e.response.status_code}, retrying in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    raise

            except httpx.RequestError as e:
                last_error = e
                wait = self.config.retry_backoff * (2 ** attempt)
                logger.warning(f"Request failed: {e}, retrying in {wait}s")
                await asyncio.sleep(wait)

        raise last_error or Exception("Max retries exceeded")

    # ============================================================
    # GAMMA API - Market Metadata
    # ============================================================

    async def get_markets(
        self,
        active: bool = True,
        limit: int = 500,
        offset: int = 0,
    ) -> List[MarketResponse]:
        """
        Get markets from Gamma API.

        Args:
            active: If True, only return active (non-closed) markets
            limit: Max markets to return
            offset: Pagination offset
        """
        url = f"{self.config.gamma_base_url}/markets"
        params = {"limit": limit, "offset": offset}
        if active:
            params["closed"] = "false"
            params["archived"] = "false"

        response = await self._request("GET", url, params=params)
        data = response.json()

        # Handle both list and paginated responses
        if isinstance(data, list):
            markets = data
        else:
            markets = data.get("data", data.get("markets", []))

        return [MarketResponse.model_validate(m) for m in markets]

    async def get_market(self, condition_id: str) -> Optional[MarketResponse]:
        """Get single market by condition_id."""
        url = f"{self.config.gamma_base_url}/markets/{condition_id}"

        try:
            response = await self._request("GET", url)
            return MarketResponse.model_validate(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    # ============================================================
    # CLOB API - Orderbook
    # ============================================================

    async def get_orderbook(self, token_id: str) -> OrderBook:
        """
        Get orderbook for a token.

        Used for:
        - Verifying price before execution
        - Computing spread
        - Detecting anomalous prices
        """
        url = f"{self.config.clob_base_url}/book"
        params = {"token_id": token_id}

        response = await self._request("GET", url, params=params)
        data = response.json()

        return OrderBook(
            market=data.get("market", ""),
            asset_id=token_id,
            bids=[
                OrderBookLevel(price=Decimal(b["price"]), size=Decimal(b["size"]))
                for b in data.get("bids", [])
            ],
            asks=[
                OrderBookLevel(price=Decimal(a["price"]), size=Decimal(a["size"]))
                for a in data.get("asks", [])
            ],
        )

    async def verify_price(
        self,
        token_id: str,
        expected_price: float,
        max_deviation: float = 0.10,
    ) -> tuple[bool, float, str]:
        """
        Verify that orderbook price matches expected price.

        CRITICAL: Protects against anomalous spike trades.
        See "Belichick Bug" in main CLAUDE.md.

        Returns:
            (is_valid, actual_price, reason)
        """
        try:
            book = await self.get_orderbook(token_id)
            actual_price = float(book.mid_price) if book.mid_price else 0

            deviation = abs(actual_price - expected_price)

            if deviation > max_deviation:
                return (
                    False,
                    actual_price,
                    f"orderbook_price={actual_price:.2f} differs from "
                    f"expected={expected_price:.2f} by {deviation:.2f}",
                )

            return True, actual_price, "ok"

        except Exception as e:
            logger.warning(f"Could not verify price for {token_id[:16]}: {e}")
            # Fail closed - reject if we can't verify
            return False, 0, f"verification_failed: {e}"

    async def get_tick_size(self, token_id: str) -> Decimal:
        """Get minimum tick size for token. Usually 0.01."""
        url = f"{self.config.clob_base_url}/tick-size"
        params = {"token_id": token_id}

        try:
            response = await self._request("GET", url, params=params)
            return Decimal(response.json().get("minimum_tick_size", "0.01"))
        except Exception:
            return Decimal("0.01")  # Safe default

    # ============================================================
    # DATA API - Trades
    # ============================================================

    async def get_recent_trades(
        self,
        condition_id: str,
        limit: int = 20,
        max_age_seconds: int = 300,
    ) -> List[TradeResponse]:
        """
        Get recent trades for a market.

        CRITICAL: The API returns "recent" trades that may be MONTHS old
        for low-volume markets. Always filter by max_age_seconds!

        Args:
            condition_id: Market condition ID
            limit: Max trades to fetch
            max_age_seconds: Only return trades newer than this (default 5 min)

        Returns:
            List of fresh trades (filtered by age)
        """
        url = f"{self.config.data_base_url}/trades"
        params = {"market": condition_id, "limit": limit}

        response = await self._request("GET", url, params=params)
        data = response.json()

        if not data:
            return []

        now = time.time()
        fresh_trades = []

        for trade_data in data:
            trade = TradeResponse.model_validate(trade_data)

            # CRITICAL: Filter stale trades
            age = now - trade.unix_timestamp
            if age > max_age_seconds:
                logger.debug(
                    f"Filtering stale trade: age={age:.0f}s, "
                    f"price={trade.price}, token={trade.asset[:16]}"
                )
                continue

            fresh_trades.append(trade)

        if not fresh_trades and data:
            logger.warning(
                f"All {len(data)} trades for {condition_id[:16]} are stale "
                f"(older than {max_age_seconds}s)"
            )

        return fresh_trades

    async def get_trade_size_at_price(
        self,
        condition_id: str,
        target_price: float,
        tolerance: float = 0.02,
        max_age_seconds: int = 300,
    ) -> Optional[float]:
        """
        Get the trade size for a specific price.

        Used when WebSocket triggers (which don't include size)
        to fetch the actual trade size for model features.

        Args:
            condition_id: Market condition ID
            target_price: Price to match
            tolerance: Price tolerance (default 2 cents)
            max_age_seconds: Only consider fresh trades

        Returns:
            Trade size if found, None otherwise
        """
        trades = await self.get_recent_trades(
            condition_id, limit=20, max_age_seconds=max_age_seconds
        )

        for trade in trades:
            if abs(trade.price - target_price) <= tolerance:
                return trade.size

        return None
```

### Tests for `polymarket_client.py`

```python
# tests/test_polymarket_client.py

import pytest
import respx
from httpx import Response
from decimal import Decimal

from polymarket_bot.ingestion.polymarket_client import (
    PolymarketClient,
    PolymarketClientConfig,
)
from polymarket_bot.ingestion.types import TradeResponse


@pytest.fixture
def client() -> PolymarketClient:
    """Create client with test config."""
    config = PolymarketClientConfig(
        max_retries=1,
        timeout=5.0,
    )
    return PolymarketClient(config)


class TestGetMarkets:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_market_list(self, client: PolymarketClient) -> None:
        """Should parse market list from API."""
        respx.get("https://gamma-api.polymarket.com/markets").mock(
            return_value=Response(200, json=[
                {
                    "condition_id": "0x123",
                    "question": "Will it rain?",
                    "category": "weather",
                }
            ])
        )

        markets = await client.get_markets()

        assert len(markets) == 1
        assert markets[0].condition_id == "0x123"
        assert markets[0].question == "Will it rain?"


class TestGetOrderbook:
    @respx.mock
    @pytest.mark.asyncio
    async def test_parses_orderbook(self, client: PolymarketClient) -> None:
        """Should parse orderbook with bids and asks."""
        respx.get("https://clob.polymarket.com/book").mock(
            return_value=Response(200, json={
                "market": "0x123",
                "bids": [{"price": "0.45", "size": "100"}],
                "asks": [{"price": "0.55", "size": "200"}],
            })
        )

        book = await client.get_orderbook("token123")

        assert book.best_bid == Decimal("0.45")
        assert book.best_ask == Decimal("0.55")
        assert book.mid_price == Decimal("0.50")
        assert book.spread == Decimal("0.10")


class TestVerifyPrice:
    @respx.mock
    @pytest.mark.asyncio
    async def test_accepts_matching_price(self, client: PolymarketClient) -> None:
        """Should accept when orderbook matches expected price."""
        respx.get("https://clob.polymarket.com/book").mock(
            return_value=Response(200, json={
                "bids": [{"price": "0.94", "size": "100"}],
                "asks": [{"price": "0.96", "size": "100"}],
            })
        )

        is_valid, actual, reason = await client.verify_price("token", 0.95)

        assert is_valid is True
        assert abs(actual - 0.95) < 0.01

    @respx.mock
    @pytest.mark.asyncio
    async def test_rejects_deviated_price(self, client: PolymarketClient) -> None:
        """Should reject when orderbook differs significantly."""
        respx.get("https://clob.polymarket.com/book").mock(
            return_value=Response(200, json={
                "bids": [{"price": "0.45", "size": "100"}],
                "asks": [{"price": "0.55", "size": "100"}],
            })
        )

        is_valid, actual, reason = await client.verify_price("token", 0.95)

        assert is_valid is False
        assert "differs" in reason


class TestGetRecentTrades:
    """
    CRITICAL: These tests verify the stale trade filtering.
    This is essential to prevent the Belichick bug.
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_stale_trades(self, client: PolymarketClient) -> None:
        """Should filter out trades older than max_age_seconds."""
        import time

        now = int(time.time())
        old_ts = now - 3600  # 1 hour ago

        respx.get("https://data-api.polymarket.com/trades").mock(
            return_value=Response(200, json=[
                {"asset": "token1", "price": 0.95, "size": 100, "side": "buy",
                 "timestamp": now - 60},  # Fresh (1 min ago)
                {"asset": "token2", "price": 0.95, "size": 50, "side": "buy",
                 "timestamp": old_ts},    # Stale (1 hour ago)
            ])
        )

        trades = await client.get_recent_trades("0x123", max_age_seconds=300)

        assert len(trades) == 1
        assert trades[0].asset == "token1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_empty_when_all_stale(self, client: PolymarketClient) -> None:
        """Should return empty list when all trades are stale."""
        import time

        old_ts = int(time.time()) - 86400  # 1 day ago

        respx.get("https://data-api.polymarket.com/trades").mock(
            return_value=Response(200, json=[
                {"asset": "token", "price": 0.95, "size": 100, "side": "buy",
                 "timestamp": old_ts},
            ])
        )

        trades = await client.get_recent_trades("0x123", max_age_seconds=300)

        assert len(trades) == 0


class TestTradeResponseStaleness:
    """Test the is_stale property on TradeResponse."""

    def test_fresh_trade_not_stale(self) -> None:
        """Trade from 1 minute ago should not be stale."""
        import time

        trade = TradeResponse(
            asset="token",
            price=0.95,
            size=100,
            side="buy",
            timestamp=int(time.time()) - 60,
        )

        assert trade.is_stale is False

    def test_old_trade_is_stale(self) -> None:
        """Trade from 1 hour ago should be stale."""
        import time

        trade = TradeResponse(
            asset="token",
            price=0.95,
            size=100,
            side="buy",
            timestamp=int(time.time()) - 3600,
        )

        assert trade.is_stale is True
```

---

## 3. WebSocket Client

### `websocket_client.py`

```python
"""
WebSocket client for real-time Polymarket price updates.

CRITICAL GOTCHAS:
1. WebSocket does NOT include trade size - only price
2. IPv6 may not work - force IPv4 if needed
3. Need to handle reconnection gracefully
4. Subscription management for many tokens
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from typing import AsyncIterator, Callable, Dict, List, Optional, Set

import websockets
from pydantic import BaseModel
from websockets.exceptions import ConnectionClosed

from .types import PriceUpdate

logger = logging.getLogger(__name__)


class WebSocketConfig(BaseModel):
    """WebSocket client configuration."""
    url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    origin: str = "https://polymarket.com"

    # Connection settings
    ping_interval: float = 30.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0

    # Reconnection
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    max_reconnect_attempts: int = 0  # 0 = infinite

    # Subscription limits
    max_subscriptions: int = 500

    # IPv6 workaround
    force_ipv4: bool = True


class WebSocketClient:
    """
    WebSocket streaming client with auto-reconnection.

    Usage:
        client = WebSocketClient(WebSocketConfig())

        # Subscribe to tokens
        await client.subscribe(["token1", "token2"])

        # Process messages
        async for message in client.run():
            if price_update := message.get("price_update"):
                # Handle price update
                # NOTE: No trade size! Fetch from REST API.
                pass

        await client.close()
    """

    def __init__(self, config: WebSocketConfig) -> None:
        self.config = config
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscribed_tokens: Set[str] = set()
        self._running = False
        self._reconnect_attempts = 0

        # Apply IPv4 workaround if needed
        if config.force_ipv4:
            self._apply_ipv4_workaround()

    def _apply_ipv4_workaround(self) -> None:
        """
        Force IPv4 connections.

        Polymarket's WebSocket may fail on IPv6.
        """
        _orig_getaddrinfo = socket.getaddrinfo

        def _ipv4_only_getaddrinfo(*args, **kwargs):
            results = _orig_getaddrinfo(*args, **kwargs)
            return [r for r in results if r[0] == socket.AF_INET]

        socket.getaddrinfo = _ipv4_only_getaddrinfo
        logger.debug("Applied IPv4 workaround for WebSocket")

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        extra_headers = {"Origin": self.config.origin}

        self._ws = await websockets.connect(
            self.config.url,
            extra_headers=extra_headers,
            ping_interval=self.config.ping_interval,
            ping_timeout=self.config.ping_timeout,
            close_timeout=self.config.close_timeout,
        )

        logger.info(f"WebSocket connected to {self.config.url}")
        self._reconnect_attempts = 0

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
            logger.info("WebSocket closed")

    async def subscribe(self, token_ids: List[str]) -> None:
        """
        Subscribe to token price updates.

        Args:
            token_ids: List of token IDs to subscribe to
        """
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket not connected")

        # Respect subscription limit
        new_tokens = set(token_ids) - self._subscribed_tokens
        if len(self._subscribed_tokens) + len(new_tokens) > self.config.max_subscriptions:
            logger.warning(
                f"Subscription limit ({self.config.max_subscriptions}) would be exceeded"
            )
            # Only subscribe to what fits
            remaining = self.config.max_subscriptions - len(self._subscribed_tokens)
            new_tokens = set(list(new_tokens)[:remaining])

        if not new_tokens:
            return

        # Send subscription message
        message = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": list(new_tokens),
        }

        await self._ws.send(json.dumps(message))
        self._subscribed_tokens.update(new_tokens)
        logger.info(f"Subscribed to {len(new_tokens)} tokens (total: {len(self._subscribed_tokens)})")

    async def unsubscribe(self, token_ids: List[str]) -> None:
        """Unsubscribe from token price updates."""
        if not self._ws or self._ws.closed:
            return

        tokens_to_remove = set(token_ids) & self._subscribed_tokens
        if not tokens_to_remove:
            return

        message = {
            "type": "unsubscribe",
            "channel": "market",
            "assets_ids": list(tokens_to_remove),
        }

        await self._ws.send(json.dumps(message))
        self._subscribed_tokens -= tokens_to_remove
        logger.debug(f"Unsubscribed from {len(tokens_to_remove)} tokens")

    async def run(self) -> AsyncIterator[Dict]:
        """
        Run WebSocket client and yield messages.

        Handles:
        - Automatic reconnection on disconnect
        - Exponential backoff
        - Re-subscription after reconnect

        Yields:
            Dict with message data. Price updates have structure:
            {
                "price_changes": [
                    {"asset_id": "...", "price": "0.95"},
                    ...
                ],
                "timestamp": 1234567890
            }

            NOTE: No trade size in WebSocket messages!
        """
        self._running = True

        while self._running:
            try:
                # Connect if not connected
                if not self._ws or self._ws.closed:
                    await self._connect_with_backoff()

                    # Re-subscribe after reconnect
                    if self._subscribed_tokens:
                        tokens = list(self._subscribed_tokens)
                        self._subscribed_tokens.clear()
                        await self.subscribe(tokens)

                # Receive messages
                async for raw_message in self._ws:
                    if not self._running:
                        break

                    try:
                        message = json.loads(raw_message)
                        yield message
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from WebSocket: {raw_message[:100]}")

            except ConnectionClosed as e:
                if self._running:
                    logger.warning(f"WebSocket disconnected: {e}")
                    # Will reconnect on next iteration

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self._running:
                    await asyncio.sleep(self.config.reconnect_delay)

    async def _connect_with_backoff(self) -> None:
        """Connect with exponential backoff."""
        while self._running:
            try:
                await self.connect()
                return

            except Exception as e:
                self._reconnect_attempts += 1

                if (self.config.max_reconnect_attempts > 0 and
                    self._reconnect_attempts >= self.config.max_reconnect_attempts):
                    logger.error(f"Max reconnect attempts reached: {e}")
                    raise

                delay = min(
                    self.config.reconnect_delay * (2 ** self._reconnect_attempts),
                    self.config.max_reconnect_delay,
                )
                logger.warning(
                    f"Connection failed (attempt {self._reconnect_attempts}), "
                    f"retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and not self._ws.closed

    @property
    def subscription_count(self) -> int:
        """Number of active subscriptions."""
        return len(self._subscribed_tokens)


def parse_price_updates(message: Dict) -> List[PriceUpdate]:
    """
    Parse price updates from WebSocket message.

    IMPORTANT: These updates do NOT include trade size!
    You must fetch size from REST API if needed for model features.
    """
    updates = []

    # Handle price_changes format
    if "price_changes" in message:
        timestamp = message.get("timestamp", int(time.time()))
        for change in message["price_changes"]:
            updates.append(PriceUpdate(
                asset_id=change.get("asset_id", ""),
                price=Decimal(str(change.get("price", "0"))),
                timestamp=timestamp,
            ))

    return updates
```

---

## 4. Metadata Sync Service

### `metadata_sync.py`

```python
"""
Market metadata synchronization service.

Periodically fetches market/token data from Polymarket and
syncs to local database.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from ..storage.database import Database
from ..storage.repositories.market_repo import Market, Token, MarketRepository, TokenRepository
from .polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


class MetadataSyncConfig:
    """Configuration for metadata sync."""
    sync_interval_seconds: int = 3600  # 1 hour
    batch_size: int = 500  # Markets per API call
    max_markets: int = 10000  # Safety limit


class MetadataSync:
    """
    Synchronizes market metadata from Polymarket to local database.

    Usage:
        sync = MetadataSync(client, db)
        await sync.sync_all()  # Full sync
        await sync.run()       # Continuous sync loop
    """

    def __init__(
        self,
        client: PolymarketClient,
        db: Database,
        config: Optional[MetadataSyncConfig] = None,
    ) -> None:
        self.client = client
        self.db = db
        self.config = config or MetadataSyncConfig()

        self.market_repo = MarketRepository(db)
        self.token_repo = TokenRepository(db)

        self._running = False

    async def sync_all(self) -> dict:
        """
        Sync all active markets from Polymarket.

        Returns:
            Dict with sync statistics
        """
        stats = {
            "markets_fetched": 0,
            "markets_created": 0,
            "markets_updated": 0,
            "tokens_created": 0,
            "errors": 0,
        }

        offset = 0
        while offset < self.config.max_markets:
            try:
                markets = await self.client.get_markets(
                    active=True,
                    limit=self.config.batch_size,
                    offset=offset,
                )

                if not markets:
                    break

                stats["markets_fetched"] += len(markets)

                for market_response in markets:
                    try:
                        # Convert to our model
                        market = Market(
                            condition_id=market_response.condition_id,
                            question=market_response.question,
                            description=market_response.description,
                            category=market_response.category,
                            slug=market_response.slug,
                            created_at_polymarket=market_response.created_at,
                            scheduled_end=market_response.scheduled_end,
                            volume=market_response.volume,
                            liquidity=market_response.liquidity,
                            is_resolved=market_response.closed,
                        )

                        # Upsert market
                        existing = self.market_repo.get_by_id(market.condition_id)
                        if existing:
                            self.market_repo.update(market)
                            stats["markets_updated"] += 1
                        else:
                            self.market_repo.create(market)
                            stats["markets_created"] += 1

                        # Sync tokens
                        for token_response in market_response.tokens:
                            if not self.token_repo.exists(token_response.token_id):
                                token = Token(
                                    token_id=token_response.token_id,
                                    condition_id=market.condition_id,
                                    outcome=token_response.outcome,
                                )
                                self.token_repo.create(token)
                                stats["tokens_created"] += 1

                    except Exception as e:
                        logger.error(f"Error syncing market {market_response.condition_id}: {e}")
                        stats["errors"] += 1

                offset += len(markets)

                # Small delay between batches
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error fetching markets at offset {offset}: {e}")
                stats["errors"] += 1
                break

        logger.info(
            f"Metadata sync complete: {stats['markets_created']} created, "
            f"{stats['markets_updated']} updated, {stats['tokens_created']} tokens, "
            f"{stats['errors']} errors"
        )

        return stats

    async def run(self) -> None:
        """Run continuous sync loop."""
        self._running = True
        logger.info(f"Starting metadata sync (interval: {self.config.sync_interval_seconds}s)")

        while self._running:
            try:
                await self.sync_all()
            except Exception as e:
                logger.error(f"Sync iteration failed: {e}")

            await asyncio.sleep(self.config.sync_interval_seconds)

    def stop(self) -> None:
        """Stop the sync loop."""
        self._running = False
```

---

## 5. CLAUDE.md for Ingestion Layer

```markdown
# Ingestion Layer

## Purpose
Fetch all data from Polymarket APIs and WebSocket.

## Responsibilities
- REST API client (Gamma, CLOB, Data APIs)
- WebSocket streaming for real-time prices
- Market/token metadata synchronization
- Historical trade fetching
- Rate limiting and retries

## NOT Responsibilities
- Storing data (Storage Layer)
- Making trading decisions (Core/Strategies)
- Executing orders (Execution Layer)

## Key Files

| File | Purpose |
|------|---------|
| `types.py` | Data types (Market, Token, Trade, OrderBook, etc.) |
| `polymarket_client.py` | REST API wrapper |
| `websocket_client.py` | WebSocket streaming |
| `metadata_sync.py` | Periodic market metadata sync |
| `trade_fetcher.py` | Historical trade fetching |

## Public Interfaces

```python
# REST Client
client = PolymarketClient(PolymarketClientConfig())
markets = await client.get_markets(active=True)
book = await client.get_orderbook(token_id)
trades = await client.get_recent_trades(condition_id, max_age_seconds=300)
is_valid, price, reason = await client.verify_price(token_id, expected_price)

# WebSocket
ws = WebSocketClient(WebSocketConfig())
await ws.subscribe(token_ids)
async for message in ws.run():
    price_updates = parse_price_updates(message)
    # NOTE: No trade size in WebSocket!

# Metadata Sync
sync = MetadataSync(client, db)
await sync.sync_all()
```

## Critical Gotchas

### 1. Stale Trade Data (BELICHICK BUG)
The trades API returns "recent" trades that may be **MONTHS old** for low-volume markets.

**ALWAYS** use `max_age_seconds` parameter:
```python
trades = await client.get_recent_trades(condition_id, max_age_seconds=300)
```

### 2. WebSocket Has No Trade Size
Price updates from WebSocket do NOT include trade size:
```json
{"price_changes": [{"asset_id": "...", "price": "0.95"}]}
// No size field!
```
If you need size for model features, fetch from REST API.

### 3. Category Field Often None
Polymarket's `category` field is frequently None for newer markets.
Use keyword detection instead:
```python
# Don't rely on this
if market.category == "weather":  # Often None!

# Do this instead
if detect_weather_keywords(market.question):
```

### 4. IPv6 May Not Work
Polymarket WebSocket may fail on IPv6. The client has `force_ipv4=True` by default.

### 5. Multiple Token IDs Per Market
A market (condition_id) can have multiple token_ids pointing to it.
Always track by condition_id to avoid duplicates.

## Testing

```bash
pytest src/polymarket_bot/ingestion/tests/ -v

# With mocked responses (no network)
pytest src/polymarket_bot/ingestion/tests/ -v -m "not integration"
```

## Configuration

```python
PolymarketClientConfig(
    gamma_base_url="https://gamma-api.polymarket.com",
    clob_base_url="https://clob.polymarket.com",
    data_base_url="https://data-api.polymarket.com",
    timeout=10.0,
    max_retries=3,
)

WebSocketConfig(
    url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
    force_ipv4=True,
    max_subscriptions=500,
)
```
```

---

This completes the Ingestion Layer specification. Ready for the Core Engine spec next?
