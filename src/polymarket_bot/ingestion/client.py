"""
REST API client for Polymarket.

Provides async access to Polymarket's Gamma (metadata) and CLOB (trading) APIs
with built-in protections for known gotchas.

Gotcha Protections:
    - G1: Trade staleness filtering (max_age_seconds parameter)
    - G5: Orderbook price verification (verify_price method)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import aiohttp

from .models import (
    Market,
    OrderbookLevel,
    OrderbookSnapshot,
    OutcomeType,
    TokenInfo,
    Trade,
    TradeSide,
)

logger = logging.getLogger(__name__)


class PolymarketAPIError(Exception):
    """Base exception for Polymarket API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(PolymarketAPIError):
    """Rate limit exceeded."""
    pass


class PolymarketRestClient:
    """
    Async REST client for Polymarket APIs.

    Features:
        - Rate limiting to avoid API throttling
        - Automatic retries with exponential backoff
        - G1 protection: Trade staleness filtering
        - G5 protection: Orderbook price verification

    Usage:
        async with PolymarketRestClient() as client:
            markets = await client.get_markets()
            trades = await client.get_trades(token_id, max_age_seconds=300)

            # G5 verification before trade
            is_valid, best_bid, reason = await client.verify_price(
                token_id, expected_price=Decimal("0.95")
            )
    """

    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        rate_limit: float = 10.0,  # requests per second
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize the REST client.

        Args:
            session: Optional aiohttp session (created if not provided)
            rate_limit: Maximum requests per second
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts for failed requests
            retry_delay: Base delay between retries (exponential backoff)
        """
        self._session = session
        self._owns_session = session is None
        self._rate_limit = rate_limit
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # Rate limiting
        self._request_times: list[float] = []
        self._rate_lock = asyncio.Lock()

    async def __aenter__(self) -> "PolymarketRestClient":
        """Async context manager entry."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._owns_session and self._session:
            await self._session.close()

    async def close(self) -> None:
        """Close the client session."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def _rate_limit_wait(self) -> None:
        """Wait if necessary to respect rate limits."""
        async with self._rate_lock:
            now = time.time()

            # Remove old timestamps outside the 1-second window
            self._request_times = [t for t in self._request_times if now - t < 1.0]

            # Wait if we've hit the rate limit
            if len(self._request_times) >= self._rate_limit:
                wait_time = 1.0 - (now - self._request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._request_times.append(time.time())

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> Any:
        """
        Make an HTTP request with rate limiting and retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Additional arguments for aiohttp

        Returns:
            Parsed JSON response

        Raises:
            PolymarketAPIError: On API errors
            RateLimitError: When rate limited
            asyncio.CancelledError: When task is cancelled (re-raised)
        """
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True

        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                await self._rate_limit_wait()

                async with self._session.request(method, url, **kwargs) as response:
                    if response.status == 429:
                        raise RateLimitError(
                            "Rate limit exceeded",
                            status_code=429
                        )

                    # 4xx client errors (except 429) - don't retry
                    if 400 <= response.status < 500:
                        text = await response.text()
                        raise PolymarketAPIError(
                            f"API error: {response.status} - {text}",
                            status_code=response.status
                        )

                    # 5xx server errors - retry
                    if response.status >= 500:
                        text = await response.text()
                        raise PolymarketAPIError(
                            f"Server error: {response.status} - {text}",
                            status_code=response.status
                        )

                    return await response.json()

            except RateLimitError:
                # Longer delay for rate limiting
                delay = self._retry_delay * (2 ** attempt) * 2
                logger.warning(f"Rate limited, waiting {delay}s before retry")
                await asyncio.sleep(delay)
                last_error = RateLimitError("Rate limit exceeded")

            except PolymarketAPIError as e:
                # 5xx errors should be retried, 4xx should not
                if e.status_code and e.status_code >= 500:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Server error {e.status_code}, retry {attempt + 1}/{self._max_retries}"
                    )
                    await asyncio.sleep(delay)
                    last_error = e
                else:
                    # 4xx client errors - don't retry, fail immediately
                    raise

            except asyncio.TimeoutError:
                # Timeout - retry with backoff
                delay = self._retry_delay * (2 ** attempt)
                logger.warning(
                    f"Request timeout, retry {attempt + 1}/{self._max_retries}"
                )
                await asyncio.sleep(delay)
                last_error = PolymarketAPIError("Request timed out")

            except asyncio.CancelledError:
                # CRITICAL FIX: Re-raise CancelledError to allow graceful shutdown
                # This was being swallowed by the generic Exception handler
                logger.debug("Request cancelled")
                raise

            except aiohttp.ClientError as e:
                delay = self._retry_delay * (2 ** attempt)
                logger.warning(f"Request failed: {e}, retry {attempt + 1}/{self._max_retries}")
                await asyncio.sleep(delay)
                last_error = PolymarketAPIError(str(e))

            except Exception as e:
                logger.error(f"Unexpected error in request: {e}")
                last_error = PolymarketAPIError(str(e))
                break

        raise last_error or PolymarketAPIError("Request failed after retries")

    # =========================================================================
    # Market Data
    # =========================================================================

    async def get_markets(
        self,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Market]:
        """
        Fetch markets from Polymarket.

        Args:
            active_only: Only return active markets
            limit: Maximum number of markets to return
            offset: Pagination offset

        Returns:
            List of Market objects
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"  # Exclude closed markets

        url = f"{self.GAMMA_API}/markets"
        data = await self._request("GET", url, params=params)

        markets = []
        for item in data:
            try:
                market = self._parse_market(item)
                if market:
                    markets.append(market)
            except Exception as e:
                logger.warning(f"Failed to parse market: {e}")

        return markets

    async def get_market(self, condition_id: str) -> Optional[Market]:
        """
        Fetch a single market by condition ID.

        Args:
            condition_id: The market's condition ID

        Returns:
            Market object or None if not found
        """
        url = f"{self.GAMMA_API}/markets/{condition_id}"

        try:
            data = await self._request("GET", url)
            return self._parse_market(data)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    def _parse_market(self, data: dict) -> Optional[Market]:
        """Parse market data from API response."""
        import json as json_module

        try:
            # Parse tokens from clobTokenIds, outcomes, and outcomePrices
            # API returns these as JSON strings
            tokens = []

            clob_token_ids_raw = data.get("clobTokenIds")
            outcomes_raw = data.get("outcomes")
            outcome_prices_raw = data.get("outcomePrices")

            # Parse JSON strings, handling null/None values
            clob_token_ids = []
            outcomes = []
            outcome_prices = []

            try:
                if clob_token_ids_raw is not None:
                    if isinstance(clob_token_ids_raw, str):
                        clob_token_ids = json_module.loads(clob_token_ids_raw) or []
                    elif isinstance(clob_token_ids_raw, list):
                        clob_token_ids = clob_token_ids_raw

                if outcomes_raw is not None:
                    if isinstance(outcomes_raw, str):
                        outcomes = json_module.loads(outcomes_raw) or []
                    elif isinstance(outcomes_raw, list):
                        outcomes = outcomes_raw

                if outcome_prices_raw is not None:
                    if isinstance(outcome_prices_raw, str):
                        outcome_prices = json_module.loads(outcome_prices_raw) or []
                    elif isinstance(outcome_prices_raw, list):
                        outcome_prices = outcome_prices_raw
            except json_module.JSONDecodeError:
                # If any JSON parsing fails, reset to empty
                clob_token_ids = []
                outcomes = []
                outcome_prices = []

            # Build token list
            for i, token_id in enumerate(clob_token_ids):
                outcome_str = outcomes[i] if i < len(outcomes) else "Unknown"
                if outcome_str.capitalize() not in ("Yes", "No"):
                    outcome_str = "Yes" if i == 0 else "No"

                price = None
                if i < len(outcome_prices):
                    try:
                        price = Decimal(str(outcome_prices[i]))
                    except Exception:
                        pass

                tokens.append(TokenInfo(
                    token_id=str(token_id),
                    outcome=OutcomeType(outcome_str.capitalize()),
                    price=price,
                ))

            # Parse end date
            end_date_str = data.get("endDateIso") or data.get("endDate") or data.get("end_date_iso")
            if end_date_str:
                # Handle various date formats
                try:
                    if "T" in end_date_str:
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    else:
                        end_date = datetime.fromisoformat(end_date_str + "T00:00:00+00:00")
                except ValueError:
                    end_date = datetime.now(timezone.utc)
            else:
                end_date = datetime.now(timezone.utc)

            # condition_id can be conditionId (camelCase) or condition_id (snake_case)
            condition_id = data.get("conditionId") or data.get("condition_id", "")

            return Market(
                condition_id=condition_id,
                question=data.get("question", ""),
                slug=data.get("slug", data.get("market_slug", "")),
                end_date=end_date,
                tokens=tokens,
                active=data.get("active", True),
                category=data.get("category"),
                volume=Decimal(str(data.get("volume", 0))) if data.get("volume") else None,
            )
        except Exception as e:
            logger.warning(f"Failed to parse market data: {e}")
            return None

    # =========================================================================
    # Trade Data (with G1 Protection)
    # =========================================================================

    async def get_trades(
        self,
        token_id: str,
        max_age_seconds: int = 300,  # G1: Default 5 minutes
        limit: int = 100,
    ) -> list[Trade]:
        """
        Fetch recent trades for a token with staleness filtering.

        G1 PROTECTION (Belichick Bug):
            This method filters out trades older than max_age_seconds.
            The Polymarket API's definition of "recent" is unreliable -
            it may return trades that are months old.

        Args:
            token_id: The token's unique identifier
            max_age_seconds: Maximum age of trades to return (G1 protection)
            limit: Maximum number of trades to fetch from API

        Returns:
            List of Trade objects, filtered by age
        """
        url = f"{self.CLOB_API}/trades"
        params = {
            "asset_id": token_id,
            "limit": limit,
        }

        data = await self._request("GET", url, params=params)

        now = time.time()
        cutoff = now - max_age_seconds

        trades = []
        filtered_count = 0

        for item in data:
            try:
                trade = self._parse_trade(item, token_id)
                if trade:
                    # G1: Filter stale trades
                    if trade.timestamp.timestamp() >= cutoff:
                        trades.append(trade)
                    else:
                        filtered_count += 1
            except Exception as e:
                logger.warning(f"Failed to parse trade: {e}")

        if filtered_count > 0:
            logger.debug(
                f"G1: Filtered {filtered_count} stale trades "
                f"(older than {max_age_seconds}s) for token {token_id}"
            )

        return trades

    async def get_trade_size_at_price(
        self,
        token_id: str,
        target_price: Decimal,
        tolerance: Decimal = Decimal("0.01"),
        max_age_seconds: int = 60,
    ) -> Optional[Decimal]:
        """
        Find the size of a recent trade near a target price.

        G3 SUPPORT:
            WebSocket price updates don't include trade size.
            Use this method to fetch the size of a trade that
            triggered a price update.

        Args:
            token_id: The token's unique identifier
            target_price: The price to search for
            tolerance: How close the trade price must be
            max_age_seconds: Maximum age of trades to consider

        Returns:
            Trade size if found, None otherwise
        """
        trades = await self.get_trades(
            token_id,
            max_age_seconds=max_age_seconds,
            limit=50,
        )

        for trade in trades:
            if abs(trade.price - target_price) <= tolerance:
                return trade.size

        return None

    def _parse_trade(self, data: dict, token_id: str) -> Optional[Trade]:
        """Parse trade data from API response."""
        try:
            # Polymarket uses millisecond timestamps
            ts_ms = data.get("timestamp") or data.get("match_time", 0)
            if isinstance(ts_ms, str):
                ts_ms = int(ts_ms)
            timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

            # Parse side
            side_str = data.get("side", "BUY").upper()
            side = TradeSide.BUY if side_str == "BUY" else TradeSide.SELL

            return Trade(
                id=data.get("id", data.get("trade_id", "")),
                token_id=token_id,
                price=Decimal(str(data.get("price", 0))),
                size=Decimal(str(data.get("size", 0))),
                side=side,
                timestamp=timestamp,
                condition_id=data.get("condition_id"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse trade data: {e}")
            return None

    # =========================================================================
    # Orderbook (with G5 Protection)
    # =========================================================================

    async def get_orderbook(self, token_id: str) -> OrderbookSnapshot:
        """
        Fetch the current orderbook for a token.

        Args:
            token_id: The token's unique identifier

        Returns:
            OrderbookSnapshot with current bids and asks
        """
        url = f"{self.CLOB_API}/book"
        params = {"token_id": token_id}

        data = await self._request("GET", url, params=params)

        bids = []
        for bid in data.get("bids", []):
            bids.append(OrderbookLevel(
                price=Decimal(str(bid.get("price", 0))),
                size=Decimal(str(bid.get("size", 0))),
            ))

        asks = []
        for ask in data.get("asks", []):
            asks.append(OrderbookLevel(
                price=Decimal(str(ask.get("price", 0))),
                size=Decimal(str(ask.get("size", 0))),
            ))

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderbookSnapshot(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    async def verify_price(
        self,
        token_id: str,
        expected_price: Decimal,
        max_deviation: Decimal = Decimal("0.10"),
    ) -> tuple[bool, Optional[Decimal], str]:
        """
        Verify that orderbook price matches expected price.

        G5 PROTECTION (Price Divergence):
            Spike trades can show 95c while the orderbook is at 5c.
            ALWAYS verify the orderbook before executing a trade
            based on a price trigger.

        Args:
            token_id: The token's unique identifier
            expected_price: The price that triggered the trade signal
            max_deviation: Maximum allowed difference from orderbook

        Returns:
            Tuple of (is_valid, best_bid, reason)
            - is_valid: True if orderbook matches expected price
            - best_bid: Current best bid price
            - reason: Explanation (empty if valid)
        """
        try:
            orderbook = await self.get_orderbook(token_id)

            if orderbook.best_bid is None:
                return False, None, "No bids in orderbook"

            is_valid, reason = orderbook.price_within_tolerance(
                expected_price,
                max_deviation,
            )

            return is_valid, orderbook.best_bid, reason

        except Exception as e:
            logger.error(f"Failed to verify price: {e}")
            return False, None, f"Failed to fetch orderbook: {e}"

    # =========================================================================
    # Token Metadata
    # =========================================================================

    async def get_token_metadata(self, token_id: str) -> Optional[dict]:
        """
        Fetch metadata for a token.

        Args:
            token_id: The token's unique identifier

        Returns:
            Token metadata dict or None if not found
        """
        # Try to get from CLOB API
        url = f"{self.CLOB_API}/token/{token_id}"

        try:
            return await self._request("GET", url)
        except PolymarketAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_price(self, token_id: str) -> Optional[Decimal]:
        """
        Get the current price for a token.

        This fetches the best bid from the orderbook.

        Args:
            token_id: The token's unique identifier

        Returns:
            Current best bid price, or None if no bids
        """
        orderbook = await self.get_orderbook(token_id)
        return orderbook.best_bid


# Convenience function for G5 verification
async def verify_orderbook_price(
    client: PolymarketRestClient,
    token_id: str,
    expected_price: Decimal,
    max_deviation: Decimal = Decimal("0.10"),
) -> tuple[bool, Optional[Decimal], str]:
    """
    Verify orderbook price matches expected price.

    Convenience function that wraps client.verify_price().
    See PolymarketRestClient.verify_price() for details.
    """
    return await client.verify_price(token_id, expected_price, max_deviation)
