"""
TDD: Tests for repository layer.
Write tests FIRST, then implement repositories to make them pass.

These tests use an in-memory mock to test repository logic.
Integration tests will test actual PostgreSQL.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

from explorer.models.market import (
    Market,
    MarketStatus,
    PriceData,
    LiquidityData,
)
from explorer.db.repositories import (
    MarketRepository,
    MarketFilter,
    SortOrder,
    PaginatedResult,
)


@pytest.fixture
def sample_markets() -> list[Market]:
    """Create sample markets for testing."""
    now = datetime.now(timezone.utc)
    return [
        Market(
            condition_id="0x001",
            question="Will Bitcoin hit $150k by end of 2025?",
            category="crypto",
            end_time=now + timedelta(days=365),
            price=PriceData(
                yes_price=Decimal("0.42"),
                no_price=Decimal("0.58"),
                best_bid=Decimal("0.41"),
                best_ask=Decimal("0.43"),
            ),
            liquidity=LiquidityData(
                volume_24h=Decimal("125000"),
                volume_7d=Decimal("800000"),
                open_interest=Decimal("1500000"),
                liquidity_score=Decimal("85"),
            ),
        ),
        Market(
            condition_id="0x002",
            question="Will Trump win 2028 election?",
            category="politics",
            end_time=now + timedelta(days=1000),
            price=PriceData(
                yes_price=Decimal("0.31"),
                no_price=Decimal("0.69"),
                best_bid=Decimal("0.30"),
                best_ask=Decimal("0.32"),
            ),
            liquidity=LiquidityData(
                volume_24h=Decimal("89000"),
                volume_7d=Decimal("500000"),
                open_interest=Decimal("900000"),
                liquidity_score=Decimal("72"),
            ),
        ),
        Market(
            condition_id="0x003",
            question="Will ETH hit $10k?",
            category="crypto",
            end_time=now + timedelta(days=180),
            price=PriceData(
                yes_price=Decimal("0.18"),
                no_price=Decimal("0.82"),
                best_bid=Decimal("0.17"),
                best_ask=Decimal("0.19"),
            ),
            liquidity=LiquidityData(
                volume_24h=Decimal("45000"),
                volume_7d=Decimal("200000"),
                open_interest=Decimal("400000"),
                liquidity_score=Decimal("55"),
            ),
        ),
        Market(
            condition_id="0x004",
            question="Will Lakers win NBA championship?",
            category="sports",
            end_time=now + timedelta(days=200),
            resolved=True,
            status=MarketStatus.RESOLVED,
            outcome="NO",
            price=PriceData(
                yes_price=Decimal("0.00"),
                no_price=Decimal("1.00"),
                best_bid=None,
                best_ask=None,
            ),
            liquidity=LiquidityData(
                volume_24h=Decimal("0"),
                volume_7d=Decimal("150000"),
                open_interest=Decimal("300000"),
                liquidity_score=Decimal("0"),
            ),
        ),
    ]


class TestMarketFilter:
    """Test the MarketFilter dataclass."""

    def test_filter_creation_defaults(self):
        """MarketFilter should have sensible defaults."""
        filter = MarketFilter()

        assert filter.categories is None
        assert filter.status is None
        assert filter.min_price is None
        assert filter.max_price is None
        assert filter.min_volume_24h is None
        assert filter.min_liquidity_score is None
        assert filter.search_query is None
        assert filter.resolved is None

    def test_filter_with_values(self):
        """MarketFilter should accept all filter values."""
        filter = MarketFilter(
            categories=["crypto", "politics"],
            status=[MarketStatus.ACTIVE],
            min_price=Decimal("0.10"),
            max_price=Decimal("0.90"),
            min_volume_24h=Decimal("10000"),
            min_liquidity_score=Decimal("50"),
            search_query="bitcoin",
            resolved=False,
        )

        assert filter.categories == ["crypto", "politics"]
        assert filter.min_price == Decimal("0.10")
        assert filter.search_query == "bitcoin"


class TestSortOrder:
    """Test the SortOrder dataclass."""

    def test_sort_order_defaults(self):
        """SortOrder should default to volume_24h descending."""
        sort = SortOrder()

        assert sort.field == "volume_24h"
        assert sort.descending is True

    def test_sort_order_custom(self):
        """SortOrder should accept custom field and direction."""
        sort = SortOrder(field="yes_price", descending=False)

        assert sort.field == "yes_price"
        assert sort.descending is False


class TestPaginatedResult:
    """Test the PaginatedResult dataclass."""

    def test_paginated_result(self):
        """PaginatedResult should contain items and metadata."""
        result = PaginatedResult(
            items=[{"id": 1}, {"id": 2}],
            total=100,
            page=1,
            page_size=10,
            total_pages=10,
        )

        assert len(result.items) == 2
        assert result.total == 100
        assert result.total_pages == 10
        assert result.has_next is True
        assert result.has_prev is False

    def test_paginated_result_last_page(self):
        """PaginatedResult should know when on last page."""
        result = PaginatedResult(
            items=[{"id": 99}, {"id": 100}],
            total=100,
            page=10,
            page_size=10,
            total_pages=10,
        )

        assert result.has_next is False
        assert result.has_prev is True


class TestMarketRepository:
    """Test the MarketRepository."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        return AsyncMock()

    @pytest.fixture
    def repo(self, mock_db):
        """Create a repository with mock db."""
        return MarketRepository(mock_db)

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_db, sample_markets):
        """get_by_id should return market when found."""
        # Setup mock to return a market row
        mock_db.fetchrow.return_value = {
            "condition_id": "0x001",
            "question": "Will Bitcoin hit $150k?",
            "category": "crypto",
            "resolved": False,
            "status": "active",
            "yes_price": Decimal("0.42"),
            "no_price": Decimal("0.58"),
            "best_bid": Decimal("0.41"),
            "best_ask": Decimal("0.43"),
            "volume_24h": Decimal("125000"),
            "volume_7d": Decimal("800000"),
            "open_interest": Decimal("1500000"),
            "liquidity_score": Decimal("85"),
            "end_time": datetime.now(timezone.utc),
        }

        market = await repo.get_by_id("0x001")

        assert market is not None
        assert market.condition_id == "0x001"
        assert market.question == "Will Bitcoin hit $150k?"
        mock_db.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_db):
        """get_by_id should return None when not found."""
        mock_db.fetchrow.return_value = None

        market = await repo.get_by_id("0xnonexistent")

        assert market is None

    @pytest.mark.asyncio
    async def test_list_markets_no_filter(self, repo, mock_db):
        """list_markets should return all markets without filter."""
        mock_db.fetch.return_value = [
            {
                "condition_id": "0x001",
                "question": "Market 1?",
                "category": "crypto",
                "resolved": False,
                "status": "active",
                "yes_price": Decimal("0.50"),
                "no_price": Decimal("0.50"),
                "best_bid": Decimal("0.49"),
                "best_ask": Decimal("0.51"),
                "volume_24h": Decimal("100000"),
                "volume_7d": Decimal("500000"),
                "open_interest": Decimal("1000000"),
                "liquidity_score": Decimal("80"),
                "end_time": datetime.now(timezone.utc),
            },
        ]
        mock_db.fetchval.return_value = 1  # total count

        result = await repo.list_markets()

        assert len(result.items) == 1
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_markets_with_category_filter(self, repo, mock_db):
        """list_markets should filter by category."""
        mock_db.fetch.return_value = []
        mock_db.fetchval.return_value = 0

        filter = MarketFilter(categories=["crypto"])
        await repo.list_markets(market_filter=filter)

        # Verify the query included category filter
        call_args = mock_db.fetch.call_args
        assert call_args is not None
        query = call_args[0][0]
        assert "category" in query.lower()

    @pytest.mark.asyncio
    async def test_list_markets_with_price_filter(self, repo, mock_db):
        """list_markets should filter by price range."""
        mock_db.fetch.return_value = []
        mock_db.fetchval.return_value = 0

        filter = MarketFilter(
            min_price=Decimal("0.20"),
            max_price=Decimal("0.80"),
        )
        await repo.list_markets(market_filter=filter)

        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        assert "yes_price" in query.lower()

    @pytest.mark.asyncio
    async def test_list_markets_with_search(self, repo, mock_db):
        """list_markets should search by question text."""
        mock_db.fetch.return_value = []
        mock_db.fetchval.return_value = 0

        filter = MarketFilter(search_query="bitcoin")
        await repo.list_markets(market_filter=filter)

        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        # Should use ILIKE or full-text search
        assert "question" in query.lower() or "search" in query.lower()

    @pytest.mark.asyncio
    async def test_list_markets_pagination(self, repo, mock_db):
        """list_markets should support pagination."""
        mock_db.fetch.return_value = []
        mock_db.fetchval.return_value = 100

        result = await repo.list_markets(page=3, page_size=20)

        assert result.page == 3
        assert result.page_size == 20
        assert result.total == 100
        assert result.total_pages == 5

        # Verify OFFSET was used
        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        assert "offset" in query.lower() or "limit" in query.lower()

    @pytest.mark.asyncio
    async def test_list_markets_sorting(self, repo, mock_db):
        """list_markets should support custom sorting."""
        mock_db.fetch.return_value = []
        mock_db.fetchval.return_value = 0

        sort = SortOrder(field="liquidity_score", descending=True)
        await repo.list_markets(sort=sort)

        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        assert "order by" in query.lower()
        assert "liquidity_score" in query.lower()

    @pytest.mark.asyncio
    async def test_get_categories(self, repo, mock_db):
        """get_categories should return distinct categories with counts."""
        mock_db.fetch.return_value = [
            {"category": "crypto", "count": 150},
            {"category": "politics", "count": 80},
            {"category": "sports", "count": 45},
        ]

        categories = await repo.get_categories()

        assert len(categories) == 3
        assert categories["crypto"] == 150
        assert categories["politics"] == 80

    @pytest.mark.asyncio
    async def test_search_markets(self, repo, mock_db):
        """search_markets should search question and description."""
        mock_db.fetch.return_value = [
            {
                "condition_id": "0x001",
                "question": "Will Bitcoin hit $150k?",
                "category": "crypto",
                "resolved": False,
                "status": "active",
                "yes_price": Decimal("0.42"),
                "no_price": Decimal("0.58"),
                "best_bid": Decimal("0.41"),
                "best_ask": Decimal("0.43"),
                "volume_24h": Decimal("125000"),
                "volume_7d": Decimal("800000"),
                "open_interest": Decimal("1500000"),
                "liquidity_score": Decimal("85"),
                "end_time": datetime.now(timezone.utc),
            },
        ]

        results = await repo.search_markets("bitcoin")

        assert len(results) == 1
        assert "bitcoin" in results[0].question.lower()

    @pytest.mark.asyncio
    async def test_get_volume_leaders(self, repo, mock_db):
        """get_volume_leaders should return top markets by volume."""
        mock_db.fetch.return_value = [
            {
                "condition_id": "0x001",
                "question": "Top volume market?",
                "category": "crypto",
                "resolved": False,
                "status": "active",
                "yes_price": Decimal("0.50"),
                "no_price": Decimal("0.50"),
                "best_bid": Decimal("0.49"),
                "best_ask": Decimal("0.51"),
                "volume_24h": Decimal("500000"),
                "volume_7d": Decimal("2000000"),
                "open_interest": Decimal("5000000"),
                "liquidity_score": Decimal("95"),
                "end_time": datetime.now(timezone.utc),
            },
        ]

        leaders = await repo.get_volume_leaders(limit=10)

        assert len(leaders) == 1
        mock_db.fetch.assert_called_once()
        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        assert "order by" in query.lower()
        assert "volume" in query.lower()

    @pytest.mark.asyncio
    async def test_get_by_event_id(self, repo, mock_db):
        """get_by_event_id should return all markets for an event."""
        mock_db.fetch.return_value = [
            {
                "condition_id": "0x001",
                "event_id": "event_123",
                "question": "Related market 1?",
                "category": "politics",
                "resolved": False,
                "status": "active",
                "yes_price": Decimal("0.50"),
                "no_price": Decimal("0.50"),
                "best_bid": Decimal("0.49"),
                "best_ask": Decimal("0.51"),
                "volume_24h": Decimal("100000"),
                "volume_7d": Decimal("500000"),
                "open_interest": Decimal("1000000"),
                "liquidity_score": Decimal("80"),
                "end_time": datetime.now(timezone.utc),
            },
            {
                "condition_id": "0x002",
                "event_id": "event_123",
                "question": "Related market 2?",
                "category": "politics",
                "resolved": False,
                "status": "active",
                "yes_price": Decimal("0.30"),
                "no_price": Decimal("0.70"),
                "best_bid": Decimal("0.29"),
                "best_ask": Decimal("0.31"),
                "volume_24h": Decimal("80000"),
                "volume_7d": Decimal("400000"),
                "open_interest": Decimal("800000"),
                "liquidity_score": Decimal("75"),
                "end_time": datetime.now(timezone.utc),
            },
        ]

        markets = await repo.get_by_event_id("event_123")

        assert len(markets) == 2
        call_args = mock_db.fetch.call_args
        query = call_args[0][0]
        assert "event_id" in query.lower()
