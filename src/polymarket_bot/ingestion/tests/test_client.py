"""
Tests for Polymarket REST API client.

These tests verify:
- Market data parsing with camelCase API fields
- Token ID extraction from clobTokenIds JSON string
- Outcome and price parsing from JSON strings
- Closed market filtering
- G1 stale trade filtering
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json

from polymarket_bot.ingestion.client import PolymarketRestClient
from polymarket_bot.ingestion.models import Market, TokenInfo, OutcomeType


class TestMarketParsing:
    """Tests for _parse_market method."""

    @pytest.fixture
    def client(self):
        """Create a REST client instance."""
        return PolymarketRestClient()

    def test_parses_condition_id_from_camel_case(self, client):
        """
        Polymarket API returns conditionId in camelCase.
        Parser should handle this correctly.
        """
        data = {
            "conditionId": "0xe3b423dfad8c22ff75c9899c4e8176f628cf4ad4caa00481764d320e7415f7a9",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.condition_id == "0xe3b423dfad8c22ff75c9899c4e8176f628cf4ad4caa00481764d320e7415f7a9"

    def test_parses_token_ids_from_json_string(self, client):
        """
        clobTokenIds is a JSON string array, not a native array.
        Parser should decode and extract token IDs.
        """
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "clobTokenIds": '["53135072462907880191400140706440867753044989936304433583131786753949599718775", "60869871469376321574904667328762911501870754872924453995477779862968218702336"]',
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.75", "0.25"]',
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert len(market.tokens) == 2
        assert market.tokens[0].token_id == "53135072462907880191400140706440867753044989936304433583131786753949599718775"
        assert market.tokens[1].token_id == "60869871469376321574904667328762911501870754872924453995477779862968218702336"

    def test_parses_outcomes_from_json_string(self, client):
        """outcomes field is a JSON string array."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "clobTokenIds": '["token1", "token2"]',
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.60", "0.40"]',
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.tokens[0].outcome == OutcomeType.YES
        assert market.tokens[1].outcome == OutcomeType.NO

    def test_parses_prices_from_json_string(self, client):
        """outcomePrices field is a JSON string array."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "clobTokenIds": '["token1", "token2"]',
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.65", "0.35"]',
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.tokens[0].price == Decimal("0.65")
        assert market.tokens[1].price == Decimal("0.35")

    def test_parses_end_date_with_timezone(self, client):
        """endDate should be parsed with timezone."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T23:59:59Z",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.end_date.year == 2025
        assert market.end_date.month == 12
        assert market.end_date.day == 31

    def test_parses_end_date_iso_format(self, client):
        """endDateIso should be handled (date only format)."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDateIso": "2026-02-28",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.end_date.year == 2026
        assert market.end_date.month == 2
        assert market.end_date.day == 28

    def test_handles_empty_token_arrays(self, client):
        """Empty token arrays should result in empty tokens list."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert len(market.tokens) == 0

    def test_handles_missing_fields_gracefully(self, client):
        """Missing optional fields should not crash parser."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.condition_id == "0xabc123"
        assert market.question == "Test market?"
        assert len(market.tokens) == 0

    def test_parses_category(self, client):
        """Category field should be extracted."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "category": "crypto",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.category == "crypto"

    def test_parses_volume(self, client):
        """Volume field should be extracted as Decimal."""
        data = {
            "conditionId": "0xabc123",
            "question": "Test market?",
            "slug": "test-market",
            "endDate": "2025-12-31T00:00:00Z",
            "volume": "12345.67",
            "clobTokenIds": "[]",
            "outcomes": "[]",
            "outcomePrices": "[]",
            "active": True,
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.volume == Decimal("12345.67")


class TestRealAPIResponse:
    """Tests using actual Polymarket API response format."""

    @pytest.fixture
    def client(self):
        """Create a REST client instance."""
        return PolymarketRestClient()

    def test_parses_real_api_response(self, client):
        """
        Test parsing with actual Polymarket API response structure.
        This is the exact format returned by the Gamma API.
        """
        data = {
            "id": "12345",
            "question": "US recession in 2025?",
            "conditionId": "0x5a542fe246448e58671948b2f28bb746d7694172ad3c57b28d5cf86126834cf0",
            "slug": "us-recession-in-2025",
            "twitterCardImage": "https://example.com/image.png",
            "endDate": "2026-02-28T00:00:00Z",
            "category": "economics",
            "liquidity": "50000",
            "image": "https://example.com/market.png",
            "description": "Market description here...",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.35", "0.65"]',
            "volume": "29221.475077",
            "active": True,
            "marketType": "normal",
            "closed": False,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2025-12-19T00:00:00Z",
            "volume24hr": 1500.5,
            "clobTokenIds": '["11283302747327789018087926846254253631780904936940686956275996205259552151441", "51657657151055530627321198005838882818455292318658915621742481565942363716363"]',
            "endDateIso": "2026-02-28",
        }

        market = client._parse_market(data)

        assert market is not None
        assert market.condition_id == "0x5a542fe246448e58671948b2f28bb746d7694172ad3c57b28d5cf86126834cf0"
        assert market.question == "US recession in 2025?"
        assert market.slug == "us-recession-in-2025"
        assert market.category == "economics"
        assert market.volume == Decimal("29221.475077")
        assert market.active is True

        # Check tokens
        assert len(market.tokens) == 2
        assert market.tokens[0].token_id == "11283302747327789018087926846254253631780904936940686956275996205259552151441"
        assert market.tokens[0].outcome == OutcomeType.YES
        assert market.tokens[0].price == Decimal("0.35")
        assert market.tokens[1].token_id == "51657657151055530627321198005838882818455292318658915621742481565942363716363"
        assert market.tokens[1].outcome == OutcomeType.NO
        assert market.tokens[1].price == Decimal("0.65")


class TestGetMarketsFiltering:
    """Tests for get_markets method filtering."""

    @pytest.fixture
    def client(self):
        """Create a REST client instance."""
        return PolymarketRestClient()

    @pytest.mark.asyncio
    async def test_adds_closed_false_when_active_only(self, client):
        """
        When active_only=True, should add closed=false parameter.
        This ensures we only get markets with actual trading activity.
        """
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []

            await client.get_markets(active_only=True)

            # Check that closed=false was included in params
            call_args = mock_request.call_args
            params = call_args[1].get('params', call_args[0][2] if len(call_args[0]) > 2 else {})
            assert params.get("closed") == "false"
            assert params.get("active") == "true"

    @pytest.mark.asyncio
    async def test_does_not_add_closed_when_not_active_only(self, client):
        """When active_only=False, should not filter by closed status."""
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []

            await client.get_markets(active_only=False)

            # Check that closed filter was not included
            call_args = mock_request.call_args
            params = call_args[1].get('params', call_args[0][2] if len(call_args[0]) > 2 else {})
            assert "closed" not in params
            assert "active" not in params


class TestG1TradeFiltering:
    """Tests for G1 stale trade filtering in get_trades."""

    @pytest.fixture
    def client(self):
        """Create a REST client instance."""
        return PolymarketRestClient()

    @pytest.mark.asyncio
    async def test_filters_stale_trades_by_default(self, client):
        """
        G1 BUG: API returns "recent" trades that may be months old.
        get_trades should filter by timestamp by default.
        """
        import time
        now = time.time()

        # Mock response with fresh and stale trades
        mock_trades = [
            {
                "id": "fresh_trade",
                "price": "0.75",
                "size": "100",
                "side": "BUY",
                "timestamp": int((now - 60) * 1000),  # 1 minute ago - fresh
            },
            {
                "id": "stale_trade",
                "price": "0.95",
                "size": "50",
                "timestamp": int((now - 86400 * 60) * 1000),  # 60 days ago - stale!
            },
        ]

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_trades

            trades = await client.get_trades("token_123", max_age_seconds=300)

            # Only fresh trade should be returned
            assert len(trades) == 1
            assert trades[0].id == "fresh_trade"

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_trades_stale(self, client):
        """Should return empty list when all trades are too old."""
        import time
        now = time.time()

        mock_trades = [
            {
                "id": "stale_1",
                "price": "0.50",
                "size": "100",
                "side": "BUY",
                "timestamp": int((now - 86400 * 30) * 1000),  # 30 days ago
            },
            {
                "id": "stale_2",
                "price": "0.60",
                "size": "200",
                "side": "SELL",
                "timestamp": int((now - 86400 * 60) * 1000),  # 60 days ago
            },
        ]

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_trades

            trades = await client.get_trades("token_123", max_age_seconds=300)

            assert len(trades) == 0

    @pytest.mark.asyncio
    async def test_configurable_max_age(self, client):
        """max_age_seconds should be configurable."""
        import time
        now = time.time()

        mock_trades = [
            {
                "id": "trade_1",
                "price": "0.50",
                "size": "100",
                "side": "BUY",
                "timestamp": int((now - 600) * 1000),  # 10 minutes ago
            },
        ]

        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_trades

            # With 5 minute max age, should filter out
            trades_strict = await client.get_trades("token_123", max_age_seconds=300)
            assert len(trades_strict) == 0

            # With 15 minute max age, should include
            trades_lenient = await client.get_trades("token_123", max_age_seconds=900)
            assert len(trades_lenient) == 1
