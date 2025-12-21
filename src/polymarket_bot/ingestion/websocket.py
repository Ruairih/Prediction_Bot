"""
WebSocket client for real-time Polymarket price updates.

Features:
    - Auto-reconnect with exponential backoff
    - Heartbeat monitoring (detect stale connections)
    - Subscription persistence across reconnects
    - State change callbacks

G3 Note:
    WebSocket price updates do NOT include trade size.
    Use PolymarketRestClient.get_trade_size_at_price() to fetch size.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Awaitable, Callable, Optional, Set

import websockets
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
)

from .models import PriceUpdate

logger = logging.getLogger(__name__)


class WebSocketState(str, Enum):
    """WebSocket connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"


# Type aliases for callbacks
PriceCallback = Callable[[PriceUpdate], Awaitable[None]]
StateCallback = Callable[[WebSocketState], Awaitable[None]]
ErrorCallback = Callable[[Exception], Awaitable[None]]


class PolymarketWebSocket:
    """
    Resilient WebSocket client for Polymarket price updates.

    Features:
        - Exponential backoff reconnection (1s -> 2s -> 4s -> ... -> max)
        - Heartbeat monitoring (reconnect if no message > timeout)
        - Subscription persistence across reconnects
        - Event callbacks for price updates and state changes

    Usage:
        async def handle_price(update: PriceUpdate):
            print(f"Price: {update.token_id} = {update.price}")

        ws = PolymarketWebSocket(on_price_update=handle_price)
        await ws.start()

        # Subscribe to markets
        await ws.subscribe(["token_id_1", "token_id_2"])

        # ... later
        await ws.stop()
    """

    # Polymarket WebSocket endpoints
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        on_price_update: PriceCallback,
        on_state_change: Optional[StateCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        heartbeat_timeout: float = 30.0,
        initial_reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        reconnect_multiplier: float = 2.0,
        url: Optional[str] = None,
    ):
        """
        Initialize the WebSocket client.

        Args:
            on_price_update: Callback for price updates (required)
            on_state_change: Optional callback for connection state changes
            on_error: Optional callback for errors
            heartbeat_timeout: Seconds without message before reconnect
            initial_reconnect_delay: Initial delay before reconnect attempt
            max_reconnect_delay: Maximum delay between reconnect attempts
            reconnect_multiplier: Multiplier for exponential backoff
            url: Optional WebSocket URL override (defaults to Polymarket production)
        """
        self._on_price_update = on_price_update
        self._on_state_change = on_state_change
        self._on_error = on_error
        self._url = url or self.WS_URL

        self._heartbeat_timeout = heartbeat_timeout
        self._initial_reconnect_delay = initial_reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._reconnect_multiplier = reconnect_multiplier

        # Connection state
        self._state = WebSocketState.DISCONNECTED
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscribed_tokens: Set[str] = set()
        self._pending_subscriptions: Set[str] = set()

        # Reconnection state
        self._current_reconnect_delay = initial_reconnect_delay
        self._reconnect_count = 0

        # Tasks
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        # Heartbeat tracking
        self._last_message_time: Optional[float] = None

    @property
    def state(self) -> WebSocketState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Whether currently connected."""
        return self._state == WebSocketState.CONNECTED

    @property
    def subscribed_tokens(self) -> Set[str]:
        """Currently subscribed token IDs."""
        return self._subscribed_tokens.copy()

    @property
    def reconnect_count(self) -> int:
        """Number of reconnection attempts since start."""
        return self._reconnect_count

    @property
    def last_message_time(self) -> Optional[float]:
        """Unix timestamp of last received message."""
        return self._last_message_time

    async def _set_state(self, state: WebSocketState) -> None:
        """Update state and notify callback."""
        if self._state != state:
            old_state = self._state
            self._state = state
            logger.info(f"WebSocket state: {old_state.value} -> {state.value}")

            if self._on_state_change:
                try:
                    await self._on_state_change(state)
                except Exception as e:
                    logger.error(f"Error in state change callback: {e}")

    async def start(self) -> None:
        """
        Start the WebSocket client.

        This will:
        1. Connect to Polymarket WebSocket
        2. Start the message receive loop
        3. Start the heartbeat monitor
        4. Auto-reconnect on disconnection
        """
        if self._state != WebSocketState.DISCONNECTED:
            logger.warning(f"Cannot start: already in state {self._state.value}")
            return

        self._stop_event.clear()
        await self._connect()

    async def stop(self) -> None:
        """
        Stop the WebSocket client gracefully.

        This will:
        1. Signal all tasks to stop
        2. Close the WebSocket connection
        3. Cancel background tasks
        """
        if self._state == WebSocketState.DISCONNECTED:
            return

        logger.info("Stopping WebSocket client...")
        await self._set_state(WebSocketState.STOPPING)
        self._stop_event.set()

        # Cancel tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close connection
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            self._ws = None

        await self._set_state(WebSocketState.DISCONNECTED)
        logger.info("WebSocket client stopped")

    async def _connect(self) -> None:
        """Establish WebSocket connection."""
        await self._set_state(WebSocketState.CONNECTING)

        try:
            self._ws = await websockets.connect(
                self._url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )

            self._last_message_time = asyncio.get_event_loop().time()
            self._current_reconnect_delay = self._initial_reconnect_delay

            await self._set_state(WebSocketState.CONNECTED)
            logger.info(f"Connected to {self._url}")

            # Re-subscribe to tokens
            if self._subscribed_tokens:
                await self._send_subscribe(list(self._subscribed_tokens))

            # Start background tasks
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            if self._on_error:
                await self._on_error(e)
            await self._schedule_reconnect()

    async def _receive_loop(self) -> None:
        """Main loop for receiving WebSocket messages."""
        try:
            while not self._stop_event.is_set() and self._ws:
                try:
                    message = await asyncio.wait_for(
                        self._ws.recv(),
                        timeout=self._heartbeat_timeout,
                    )
                    self._last_message_time = asyncio.get_event_loop().time()
                    await self._handle_message(message)

                except asyncio.TimeoutError:
                    # No message received within timeout - connection may be stale
                    logger.warning(
                        f"No message received in {self._heartbeat_timeout}s, reconnecting..."
                    )
                    # FIX: Close socket before breaking to avoid resource leak
                    if self._ws:
                        try:
                            await self._ws.close()
                        except Exception as close_err:
                            logger.debug(f"Error closing stale socket: {close_err}")
                        self._ws = None
                    break

                except ConnectionClosedOK:
                    logger.info("WebSocket closed normally")
                    break

                except ConnectionClosedError as e:
                    logger.warning(f"WebSocket closed with error: {e}")
                    break

                except ConnectionClosed as e:
                    logger.warning(f"WebSocket connection closed: {e}")
                    break

        except asyncio.CancelledError:
            logger.debug("Receive loop cancelled")
            raise

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            if self._on_error:
                await self._on_error(e)

        # Reconnect if not stopping
        if not self._stop_event.is_set():
            await self._schedule_reconnect()

    async def _heartbeat_loop(self) -> None:
        """Monitor connection health and trigger reconnect if stale."""
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(5)  # Check every 5 seconds

                if self._last_message_time is None:
                    continue

                elapsed = asyncio.get_event_loop().time() - self._last_message_time

                if elapsed > self._heartbeat_timeout:
                    logger.warning(
                        f"Connection stale ({elapsed:.1f}s since last message), "
                        f"triggering reconnect..."
                    )
                    # Force close to trigger reconnect in receive loop
                    if self._ws:
                        await self._ws.close()
                    break

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
            raise

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt with exponential backoff."""
        if self._stop_event.is_set():
            return

        self._reconnect_count += 1
        await self._set_state(WebSocketState.RECONNECTING)

        delay = self._current_reconnect_delay
        logger.info(
            f"Reconnecting in {delay:.1f}s "
            f"(attempt #{self._reconnect_count})..."
        )

        await asyncio.sleep(delay)

        # Exponential backoff
        self._current_reconnect_delay = min(
            self._current_reconnect_delay * self._reconnect_multiplier,
            self._max_reconnect_delay,
        )

        if not self._stop_event.is_set():
            await self._connect()

    async def _handle_message(self, raw_message: str) -> None:
        """Parse and handle a WebSocket message."""
        try:
            # Handle empty string as heartbeat/acknowledgment
            if not raw_message or not raw_message.strip():
                logger.debug("Received empty message (heartbeat)")
                return

            data = json.loads(raw_message)

            # Handle list of events (Polymarket sends arrays)
            if isinstance(data, list):
                if len(data) == 0:
                    # Empty array is acknowledgment/heartbeat
                    logger.debug("Received empty array (acknowledgment)")
                    return
                # Process each event in the array
                for event in data:
                    if isinstance(event, dict):
                        await self._handle_single_message(event)
                return

            # Handle single event as dict
            if isinstance(data, dict):
                await self._handle_single_message(data)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse message: {e}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if self._on_error:
                await self._on_error(e)

    async def _handle_single_message(self, data: dict) -> None:
        """Handle a single WebSocket message dict."""
        # Handle different message types
        msg_type = data.get("event_type") or data.get("type")

        if msg_type in ("price_change", "trade", "book", "last_trade_price"):
            await self._handle_price_message(data)

        elif msg_type == "subscribed":
            logger.debug(f"Subscription confirmed: {data}")

        elif msg_type == "error":
            logger.error(f"WebSocket error message: {data}")

        else:
            # Log unknown types at debug level to see what we're getting
            logger.debug(f"Unknown message type '{msg_type}': {str(data)[:200]}")

    async def _handle_price_message(self, data: dict) -> None:
        """Handle a price update message."""
        try:
            # Extract token ID - only use asset_id or token_id
            # NOTE: "market" field is the condition_id, not the token_id
            token_id = data.get("asset_id") or data.get("token_id")

            if not token_id:
                logger.debug(f"Price message missing asset_id/token_id, skipping")
                return

            # Extract price - handle different event formats
            # Use explicit None/empty string checks (not truthiness)
            # to handle cases where price might be "0"
            price_str = data.get("price")

            # Try last_trade_price from book events
            if price_str is None or price_str == "":
                price_str = data.get("last_trade_price")

            # Try alternative field names
            if price_str is None or price_str == "":
                price_str = data.get("yes") or data.get("outcome_price")

            # For book events, fall back to best bid price
            if (price_str is None or price_str == "") and data.get("bids"):
                bids = data.get("bids", [])
                if bids and isinstance(bids, list) and len(bids) > 0:
                    # Sort bids by price descending to ensure we get the best bid
                    try:
                        sorted_bids = sorted(
                            bids,
                            key=lambda b: Decimal(str(b.get("price", "0"))),
                            reverse=True,
                        )
                        price_str = sorted_bids[0].get("price")
                    except (ValueError, TypeError):
                        # If sorting fails, use first bid as fallback
                        price_str = bids[0].get("price")

            if price_str is None or price_str == "":
                # Silently skip if we really can't find a price
                logger.debug(f"No price found in message for {token_id}")
                return

            price = Decimal(str(price_str))

            # Create PriceUpdate
            # Note: G3 - size is NOT available from WebSocket
            update = PriceUpdate(
                token_id=token_id,
                price=price,
                timestamp=datetime.now(timezone.utc),
                condition_id=data.get("condition_id") or data.get("market"),
                market_slug=data.get("slug") or data.get("market_slug"),
            )

            # Call the callback
            await self._on_price_update(update)

        except Exception as e:
            logger.error(f"Error handling price message: {e}")
            if self._on_error:
                await self._on_error(e)

    async def subscribe(self, token_ids: list[str]) -> None:
        """
        Subscribe to price updates for tokens.

        Args:
            token_ids: List of token IDs to subscribe to

        Subscriptions persist across reconnections.
        """
        new_tokens = set(token_ids) - self._subscribed_tokens
        if not new_tokens:
            return

        self._subscribed_tokens.update(new_tokens)

        if self.is_connected:
            await self._send_subscribe(list(new_tokens))
        else:
            logger.debug(f"Queued {len(new_tokens)} tokens for subscription on connect")

    async def unsubscribe(self, token_ids: list[str]) -> None:
        """
        Unsubscribe from price updates for tokens.

        Args:
            token_ids: List of token IDs to unsubscribe from
        """
        tokens_to_remove = set(token_ids) & self._subscribed_tokens
        if not tokens_to_remove:
            return

        self._subscribed_tokens -= tokens_to_remove

        if self.is_connected:
            await self._send_unsubscribe(list(tokens_to_remove))

    async def _send_subscribe(self, token_ids: list[str]) -> None:
        """Send subscription message to WebSocket."""
        if not self._ws:
            return

        try:
            # Polymarket market channel subscription format
            # See: https://docs.polymarket.com/developers/CLOB/websocket/wss-overview
            message = {
                "assets_ids": token_ids,
                "type": "market",
            }
            await self._ws.send(json.dumps(message))
            logger.info(f"Sent subscription for {len(token_ids)} tokens")

        except Exception as e:
            logger.error(f"Failed to send subscription: {e}")

    async def _send_unsubscribe(self, token_ids: list[str]) -> None:
        """Send unsubscription message to WebSocket."""
        if not self._ws:
            return

        try:
            # Polymarket unsubscription format
            message = {
                "assets_ids": token_ids,
                "type": "market",
            }
            await self._ws.send(json.dumps(message))
            logger.info(f"Sent unsubscription for {len(token_ids)} tokens")

        except Exception as e:
            logger.error(f"Failed to send unsubscription: {e}")

    async def subscribe_all_markets(self) -> None:
        """
        Subscribe to all active markets.

        NOTE: Polymarket WebSocket doesn't support a built-in "subscribe all" option.
        Use the IngestionService which fetches markets via REST API first, then
        subscribes to all token IDs.

        This method is deprecated - use subscribe() with specific token IDs instead.
        """
        logger.warning(
            "subscribe_all_markets() called but Polymarket WebSocket doesn't support "
            "'subscribe all'. Use IngestionService with subscribe_all_markets=True config, "
            "or call subscribe() with specific token IDs."
        )
