"""
TDD: Tests for FastAPI endpoints.
Write tests FIRST, then implement endpoints to make them pass.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from explorer.db.repositories import MarketRepository, PaginatedResult
from explorer.models.market import (
    Market,
    MarketStatus,
    PriceData,
    LiquidityData,
)


@pytest.fixture
def sample_market() -> Market:
    """Create a sample market for testing."""
    return Market(
        condition_id="0x001",
        question="Will Bitcoin hit $150k by end of 2025?",
        category="crypto",
        end_time=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
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
    )


@pytest.fixture
def mock_repo():
    """Create a mock repository."""
    return AsyncMock(spec=MarketRepository)


def create_test_app(mock_repo: MarketRepository) -> FastAPI:
    """Create a test app without lifespan (no DB connection).

    This avoids the production lifespan that connects to the database.
    """
    from explorer import __version__
    from explorer.api.main import (
        health_check,
        list_markets,
        get_market_by_id,
        search_markets,
        get_categories,
        get_volume_leaders,
        get_event_markets,
        get_market_repo,
        set_market_repo,
        HealthResponse,
        PaginatedMarketsResponse,
        MarketResponse,
    )

    # Create a fresh app without lifespan
    test_app = FastAPI(title="Test App", version=__version__)

    # Set the mock repo
    set_market_repo(mock_repo)

    # Override dependency
    test_app.dependency_overrides[get_market_repo] = lambda: mock_repo

    # Register routes manually
    test_app.get("/health", response_model=HealthResponse)(health_check)
    test_app.get("/api/markets", response_model=PaginatedMarketsResponse)(list_markets)
    test_app.get("/api/markets/search")(search_markets)
    test_app.get("/api/markets/leaders/volume")(get_volume_leaders)
    test_app.get("/api/markets/{condition_id}", response_model=MarketResponse)(get_market_by_id)
    test_app.get("/api/categories")(get_categories)
    test_app.get("/api/events/{event_id}/markets")(get_event_markets)

    return test_app


@pytest.fixture
def client(mock_repo):
    """Create a test client with mocked repository."""
    test_app = create_test_app(mock_repo)
    with TestClient(test_app) as client:
        yield client


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check(self, client):
        """GET /health should return OK status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestMarketsEndpoints:
    """Test the /api/markets endpoints."""

    def test_list_markets_success(self, client, mock_repo, sample_market):
        """GET /api/markets should return paginated markets."""
        mock_repo.list_markets.return_value = PaginatedResult(
            items=[sample_market],
            total=1,
            page=1,
            page_size=50,
            total_pages=1,
        )

        response = client.get("/api/markets")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["condition_id"] == "0x001"

    def test_list_markets_with_filters(self, client, mock_repo, sample_market):
        """GET /api/markets should accept filter parameters."""
        mock_repo.list_markets.return_value = PaginatedResult(
            items=[sample_market],
            total=1,
            page=1,
            page_size=50,
            total_pages=1,
        )

        response = client.get(
            "/api/markets",
            params={
                "categories": "crypto,politics",
                "min_price": 0.20,
                "max_price": 0.80,
                "search": "bitcoin",
            },
        )

        assert response.status_code == 200
        # Verify filter was passed to repository
        mock_repo.list_markets.assert_called_once()
        call_kwargs = mock_repo.list_markets.call_args[1]
        assert call_kwargs["market_filter"].categories == ["crypto", "politics"]
        assert call_kwargs["market_filter"].search_query == "bitcoin"

    def test_list_markets_pagination(self, client, mock_repo, sample_market):
        """GET /api/markets should support pagination."""
        mock_repo.list_markets.return_value = PaginatedResult(
            items=[sample_market],
            total=100,
            page=3,
            page_size=20,
            total_pages=5,
        )

        response = client.get(
            "/api/markets",
            params={"page": 3, "page_size": 20},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 3
        assert data["page_size"] == 20
        assert data["total"] == 100
        assert data["total_pages"] == 5

    def test_list_markets_sorting(self, client, mock_repo, sample_market):
        """GET /api/markets should support sorting."""
        mock_repo.list_markets.return_value = PaginatedResult(
            items=[sample_market],
            total=1,
            page=1,
            page_size=50,
            total_pages=1,
        )

        response = client.get(
            "/api/markets",
            params={"sort_by": "liquidity_score", "sort_desc": "true"},
        )

        assert response.status_code == 200
        call_kwargs = mock_repo.list_markets.call_args[1]
        assert call_kwargs["sort"].field == "liquidity_score"
        assert call_kwargs["sort"].descending is True

    def test_list_markets_invalid_page(self, client, mock_repo):
        """GET /api/markets should reject invalid page."""
        response = client.get("/api/markets", params={"page": 0})

        assert response.status_code == 422  # Validation error

    def test_get_market_by_id_found(self, client, mock_repo, sample_market):
        """GET /api/markets/{id} should return market when found."""
        mock_repo.get_by_id.return_value = sample_market

        response = client.get("/api/markets/0x001")

        assert response.status_code == 200
        data = response.json()
        assert data["condition_id"] == "0x001"
        assert data["question"] == "Will Bitcoin hit $150k by end of 2025?"
        assert data["price"]["yes_price"] == "0.42"

    def test_get_market_by_id_not_found(self, client, mock_repo):
        """GET /api/markets/{id} should return 404 when not found."""
        mock_repo.get_by_id.return_value = None

        response = client.get("/api/markets/0xnonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestSearchEndpoint:
    """Test the search endpoint."""

    def test_search_markets(self, client, mock_repo, sample_market):
        """GET /api/markets/search should search by query."""
        mock_repo.search_markets.return_value = [sample_market]

        response = client.get("/api/markets/search", params={"q": "bitcoin"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["condition_id"] == "0x001"
        mock_repo.search_markets.assert_called_once_with("bitcoin", limit=20)

    def test_search_markets_with_limit(self, client, mock_repo, sample_market):
        """GET /api/markets/search should respect limit parameter."""
        mock_repo.search_markets.return_value = [sample_market]

        response = client.get(
            "/api/markets/search",
            params={"q": "bitcoin", "limit": 5},
        )

        assert response.status_code == 200
        mock_repo.search_markets.assert_called_once_with("bitcoin", limit=5)

    def test_search_markets_empty_query(self, client, mock_repo):
        """GET /api/markets/search should reject empty query."""
        response = client.get("/api/markets/search", params={"q": ""})

        assert response.status_code == 422


class TestCategoriesEndpoint:
    """Test the categories endpoint."""

    def test_get_categories(self, client, mock_repo):
        """GET /api/categories should return categories with counts."""
        mock_repo.get_categories.return_value = {
            "crypto": 150,
            "politics": 80,
            "sports": 45,
        }

        response = client.get("/api/categories")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data["crypto"] == 150
        assert data["politics"] == 80

    def test_get_categories_with_resolved_false(self, client, mock_repo):
        """GET /api/categories?resolved=false should filter by active markets."""
        mock_repo.get_categories.return_value = {
            "crypto": 100,
            "politics": 50,
        }

        response = client.get("/api/categories", params={"resolved": "false"})

        assert response.status_code == 200
        mock_repo.get_categories.assert_called_once_with(resolved=False)

    def test_get_categories_with_resolved_true(self, client, mock_repo):
        """GET /api/categories?resolved=true should filter by resolved markets."""
        mock_repo.get_categories.return_value = {
            "crypto": 50,
            "politics": 30,
        }

        response = client.get("/api/categories", params={"resolved": "true"})

        assert response.status_code == 200
        mock_repo.get_categories.assert_called_once_with(resolved=True)


class TestVolumeLeadersEndpoint:
    """Test the volume leaders endpoint."""

    def test_get_volume_leaders(self, client, mock_repo, sample_market):
        """GET /api/markets/leaders/volume should return top markets."""
        mock_repo.get_volume_leaders.return_value = [sample_market]

        response = client.get("/api/markets/leaders/volume")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        mock_repo.get_volume_leaders.assert_called_once()

    def test_get_volume_leaders_with_category(self, client, mock_repo, sample_market):
        """GET /api/markets/leaders/volume should filter by category."""
        mock_repo.get_volume_leaders.return_value = [sample_market]

        response = client.get(
            "/api/markets/leaders/volume",
            params={"category": "crypto", "limit": 5},
        )

        assert response.status_code == 200
        mock_repo.get_volume_leaders.assert_called_once_with(
            limit=5, category="crypto"
        )


class TestEventMarketsEndpoint:
    """Test the event markets endpoint."""

    def test_get_event_markets(self, client, mock_repo, sample_market):
        """GET /api/events/{id}/markets should return related markets."""
        mock_repo.get_by_event_id.return_value = [sample_market]

        response = client.get("/api/events/event_123/markets")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        mock_repo.get_by_event_id.assert_called_once_with("event_123")


class TestMarketResponseSchema:
    """Test that market responses have correct schema."""

    def test_market_response_includes_computed_fields(
        self, client, mock_repo, sample_market
    ):
        """Market response should include computed fields like spread."""
        mock_repo.get_by_id.return_value = sample_market

        response = client.get("/api/markets/0x001")

        assert response.status_code == 200
        data = response.json()

        # Should have price data with computed spread
        assert "price" in data
        assert "spread" in data["price"]
        assert data["price"]["spread"] == "0.02"  # 0.43 - 0.41

        # Should have liquidity data
        assert "liquidity" in data
        assert data["liquidity"]["volume_24h"] == "125000"

    def test_market_response_handles_null_price(self, client, mock_repo):
        """Market response should handle markets without price data."""
        market = Market(
            condition_id="0x002",
            question="No price market?",
            price=None,
            liquidity=None,
        )
        mock_repo.get_by_id.return_value = market

        response = client.get("/api/markets/0x002")

        assert response.status_code == 200
        data = response.json()
        assert data["price"] is None
        assert data["liquidity"] is None
