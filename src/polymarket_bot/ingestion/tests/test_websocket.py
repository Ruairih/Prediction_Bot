"""
Tests for WebSocket client message handling.

These tests verify:
- Array message handling (Polymarket sends arrays)
- Price extraction from different event formats
- Empty array handling (acknowledgments)
- Book event parsing with last_trade_price
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json

from polymarket_bot.ingestion.websocket import PolymarketWebSocket
from polymarket_bot.ingestion.models import PriceUpdate


class TestMessageHandling:
    """Tests for _handle_message and _handle_single_message."""

    @pytest.fixture
    def websocket(self):
        """Create a WebSocket client with mocked callback."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(on_price_update=callback)
        ws._on_price_update = callback
        return ws

    @pytest.mark.asyncio
    async def test_handles_empty_array_as_acknowledgment(self, websocket):
        """Empty arrays should be treated as acknowledgments and not error."""
        # Empty array is sent by Polymarket as acknowledgment
        await websocket._handle_message("[]")

        # No callback should be called for empty array
        websocket._on_price_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_array_of_events(self, websocket):
        """Array of events should process each event individually."""
        events = [
            {
                "event_type": "book",
                "asset_id": "token_1",
                "last_trade_price": "0.75",
                "bids": [{"price": "0.74", "size": "100"}],
                "asks": [{"price": "0.76", "size": "100"}],
            },
            {
                "event_type": "book",
                "asset_id": "token_2",
                "last_trade_price": "0.50",
                "bids": [{"price": "0.49", "size": "100"}],
                "asks": [{"price": "0.51", "size": "100"}],
            },
        ]

        await websocket._handle_message(json.dumps(events))

        # Both events should be processed
        assert websocket._on_price_update.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_single_dict_event(self, websocket):
        """Single dict events should be processed directly."""
        event = {
            "event_type": "price_change",
            "asset_id": "token_123",
            "price": "0.85",
        }

        await websocket._handle_message(json.dumps(event))

        websocket._on_price_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_invalid_json_gracefully(self, websocket):
        """Invalid JSON should be logged but not crash."""
        # Should not raise
        await websocket._handle_message("not valid json{")

        websocket._on_price_update.assert_not_called()


class TestPriceExtraction:
    """Tests for _handle_price_message price extraction logic."""

    @pytest.fixture
    def websocket(self):
        """Create a WebSocket client with mocked callback."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(on_price_update=callback)
        ws._on_price_update = callback
        return ws

    @pytest.mark.asyncio
    async def test_extracts_price_from_price_field(self, websocket):
        """Direct price field should be used first."""
        data = {
            "event_type": "price_change",
            "asset_id": "token_123",
            "price": "0.85",
        }

        await websocket._handle_price_message(data)

        call_args = websocket._on_price_update.call_args[0][0]
        assert call_args.price == Decimal("0.85")

    @pytest.mark.asyncio
    async def test_extracts_price_from_last_trade_price(self, websocket):
        """
        Book events have last_trade_price instead of price.
        This is the format Polymarket actually sends.
        """
        data = {
            "event_type": "book",
            "asset_id": "token_123",
            "last_trade_price": "0.92",
            "bids": [{"price": "0.91", "size": "100"}],
            "asks": [{"price": "0.93", "size": "100"}],
        }

        await websocket._handle_price_message(data)

        call_args = websocket._on_price_update.call_args[0][0]
        assert call_args.price == Decimal("0.92")

    @pytest.mark.asyncio
    async def test_falls_back_to_best_bid_when_no_price(self, websocket):
        """When no price fields exist, use best bid from orderbook."""
        data = {
            "event_type": "book",
            "asset_id": "token_123",
            "last_trade_price": "",  # Empty string
            "bids": [{"price": "0.88", "size": "100"}],
            "asks": [{"price": "0.90", "size": "100"}],
        }

        await websocket._handle_price_message(data)

        call_args = websocket._on_price_update.call_args[0][0]
        assert call_args.price == Decimal("0.88")

    @pytest.mark.asyncio
    async def test_skips_event_when_no_price_available(self, websocket):
        """Events with no extractable price should be skipped silently."""
        data = {
            "event_type": "book",
            "asset_id": "token_123",
            "last_trade_price": "",
            "bids": [],  # No bids
            "asks": [{"price": "0.90", "size": "100"}],
        }

        await websocket._handle_price_message(data)

        # Should not call callback when no price found
        websocket._on_price_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracts_token_id_from_asset_id(self, websocket):
        """Token ID should be extracted from asset_id field."""
        data = {
            "event_type": "price_change",
            "asset_id": "12345678901234567890",
            "price": "0.50",
        }

        await websocket._handle_price_message(data)

        call_args = websocket._on_price_update.call_args[0][0]
        assert call_args.token_id == "12345678901234567890"

    @pytest.mark.asyncio
    async def test_extracts_condition_id_from_market_field(self, websocket):
        """condition_id should be extracted from market field in book events."""
        data = {
            "event_type": "book",
            "asset_id": "token_123",
            "market": "0xabc123condition",
            "last_trade_price": "0.75",
            "bids": [],
            "asks": [],
        }

        await websocket._handle_price_message(data)

        call_args = websocket._on_price_update.call_args[0][0]
        assert call_args.condition_id == "0xabc123condition"

    @pytest.mark.asyncio
    async def test_skips_message_with_only_market_no_asset_id(self, websocket):
        """
        Messages with only 'market' field (no asset_id) should be skipped.
        'market' is condition_id, not token_id.
        """
        data = {
            "event_type": "book",
            "market": "0xabc123condition",  # This is condition_id, not token_id
            "last_trade_price": "0.75",
            "bids": [],
            "asks": [],
        }

        await websocket._handle_price_message(data)

        # Should NOT call callback because there's no valid token_id
        websocket._on_price_update.assert_not_called()


class TestEventTypeHandling:
    """Tests for handling different event types."""

    @pytest.fixture
    def websocket(self):
        """Create a WebSocket client with mocked callback."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(on_price_update=callback)
        ws._on_price_update = callback
        return ws

    @pytest.mark.asyncio
    async def test_handles_book_event_type(self, websocket):
        """Book events should be processed."""
        data = {
            "event_type": "book",
            "asset_id": "token_123",
            "last_trade_price": "0.75",
            "bids": [],
            "asks": [],
        }

        await websocket._handle_single_message(data)

        websocket._on_price_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_price_change_event_type(self, websocket):
        """Price change events should be processed."""
        data = {
            "event_type": "price_change",
            "asset_id": "token_123",
            "price": "0.80",
        }

        await websocket._handle_single_message(data)

        websocket._on_price_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_last_trade_price_event_type(self, websocket):
        """last_trade_price event type should be processed."""
        data = {
            "event_type": "last_trade_price",
            "asset_id": "token_123",
            "price": "0.65",
        }

        await websocket._handle_single_message(data)

        websocket._on_price_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_unknown_event_type(self, websocket):
        """Unknown event types should be ignored."""
        data = {
            "event_type": "unknown_type",
            "asset_id": "token_123",
            "price": "0.50",
        }

        await websocket._handle_single_message(data)

        websocket._on_price_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_subscribed_event_type(self, websocket):
        """Subscribed confirmation should not trigger callback."""
        data = {
            "type": "subscribed",
            "channel": "market",
        }

        await websocket._handle_single_message(data)

        websocket._on_price_update.assert_not_called()


class TestRealPolymarketMessages:
    """Tests using actual message formats from Polymarket."""

    @pytest.fixture
    def websocket(self):
        """Create a WebSocket client with mocked callback."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(on_price_update=callback)
        ws._on_price_update = callback
        return ws

    @pytest.mark.asyncio
    async def test_real_book_event_format(self, websocket):
        """
        Test with actual Polymarket book event format.
        This is the exact format received from the WebSocket.
        """
        # Real format from Polymarket
        data = {
            "market": "0x5a542fe246448e58671948b2f28bb746d7694172ad3c57b28d5cf86126834cf0",
            "asset_id": "11283302747327789018087926846254253631780904936940686956275996205259552151441",
            "timestamp": "1766106940569",
            "hash": "098e732f01617af67475838765402e69a4d39b00",
            "bids": [
                {"price": "0.001", "size": "1014447.49"},
                {"price": "0.002", "size": "3001509.82"},
            ],
            "asks": [
                {"price": "0.999", "size": "12750.71"},
            ],
            "event_type": "book",
            "last_trade_price": "0.002",
        }

        await websocket._handle_message(json.dumps([data]))

        websocket._on_price_update.assert_called_once()
        call_args = websocket._on_price_update.call_args[0][0]

        assert call_args.token_id == "11283302747327789018087926846254253631780904936940686956275996205259552151441"
        assert call_args.price == Decimal("0.002")
        assert call_args.condition_id == "0x5a542fe246448e58671948b2f28bb746d7694172ad3c57b28d5cf86126834cf0"

    @pytest.mark.asyncio
    async def test_real_book_event_empty_last_trade_price(self, websocket):
        """
        Test book event where last_trade_price is empty string.
        Should fall back to best bid.
        """
        data = {
            "market": "0x416316490efec1038ce09ec0184f82f1f7921876ee0594a30c783635ea6983d0",
            "asset_id": "27041836805134371913740407263212214733159750380813540071930429439405154056312",
            "timestamp": "1766106918388",
            "bids": [
                {"price": "0.001", "size": "141753.49"},
                {"price": "0.002", "size": "184042.04"},
            ],
            "asks": [
                {"price": "0.999", "size": "316626.13"},
            ],
            "event_type": "book",
            "last_trade_price": "",  # Empty - common in Polymarket
        }

        await websocket._handle_message(json.dumps([data]))

        websocket._on_price_update.assert_called_once()
        call_args = websocket._on_price_update.call_args[0][0]

        # Should use best bid (0.002 - highest bid price) as fallback
        assert call_args.price == Decimal("0.002")


class TestReconnectionBehavior:
    """Tests for reconnect and subscription persistence."""

    @pytest.mark.asyncio
    async def test_resubscribes_on_connect(self):
        """Previously subscribed tokens should be re-sent on reconnect."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(on_price_update=callback)
        ws._subscribed_tokens.update({"tok_1", "tok_2"})

        fake_ws = AsyncMock()
        with patch(
            "polymarket_bot.ingestion.websocket.websockets.connect",
            new=AsyncMock(return_value=fake_ws),
        ), patch.object(ws, "_receive_loop", new=AsyncMock()), patch.object(
            ws, "_heartbeat_loop", new=AsyncMock()
        ):
            await ws._connect()

        assert fake_ws.send.called
        sent = json.loads(fake_ws.send.call_args[0][0])
        assert set(sent["assets_ids"]) == {"tok_1", "tok_2"}

    @pytest.mark.asyncio
    async def test_schedule_reconnect_increments_counter(self):
        """Reconnect attempts should increment reconnect_count."""
        callback = AsyncMock()
        ws = PolymarketWebSocket(
            on_price_update=callback,
            initial_reconnect_delay=0.0,
        )

        with patch.object(ws, "_connect", new=AsyncMock()):
            await ws._schedule_reconnect()

        assert ws.reconnect_count == 1
