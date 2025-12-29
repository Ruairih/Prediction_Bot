"""
Tests for ScoreService - unified model scoring.

Tests cover:
1. Score computation logic
2. Cache behavior (memory + PostgreSQL)
3. Legacy fallback to ScoreBridge
4. get_or_compute flow
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from polymarket_bot.core.score_service import (
    ScoreService,
    ScoreResult,
    MarketData,
    BackgroundScorer,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=None)
    db.fetch = AsyncMock(return_value=[])
    return db


@pytest.fixture
def score_service(mock_db):
    """ScoreService with mocked dependencies."""
    return ScoreService(mock_db, use_legacy_fallback=False)


@pytest.fixture
def score_service_with_legacy(mock_db):
    """ScoreService with legacy fallback enabled."""
    return ScoreService(mock_db, use_legacy_fallback=True)


@pytest.fixture
def market_data():
    """Sample market data for scoring."""
    return MarketData(
        condition_id="0xtest123",
        token_id="tok_yes_abc",
        question="Will BTC hit $100k by end of 2025?",
        category="Crypto",
        price=0.95,
        spread=0.02,
        liquidity=50000.0,
        volume_24h=100000.0,
        time_to_end_hours=168.0,  # 7 days
        outcome="Yes",
    )


@pytest.fixture
def low_quality_market():
    """Market data for low-quality market."""
    return MarketData(
        condition_id="0xbad456",
        token_id="tok_bad",
        question="Random low quality market",
        category=None,
        price=0.50,
        spread=0.25,  # 25% spread - terrible
        liquidity=1000.0,  # Low liquidity
        volume_24h=500.0,
        time_to_end_hours=2000.0,  # Far out
        outcome="Yes",
    )


# =============================================================================
# Score Computation Tests
# =============================================================================


class TestScoreComputation:
    """Tests for the score computation algorithm."""

    def test_high_price_high_quality_scores_well(self, score_service, market_data):
        """High price + good liquidity + tight spread = high score."""
        score = score_service.compute_score(market_data)

        # Should be high (>= 0.85)
        assert score >= 0.85
        assert score <= 1.0

    def test_low_price_scores_lower(self, score_service, market_data):
        """Lower prices should result in lower scores."""
        market_data.price = 0.50  # Much lower price

        score = score_service.compute_score(market_data)

        # Should be lower than high price case
        assert score < 0.85

    def test_wide_spread_reduces_score(self, score_service, market_data):
        """Wide spreads should penalize the score."""
        tight_spread = MarketData(**{**market_data.__dict__, "spread": 0.01})
        wide_spread = MarketData(**{**market_data.__dict__, "spread": 0.20})

        tight_score = score_service.compute_score(tight_spread)
        wide_score = score_service.compute_score(wide_spread)

        assert tight_score > wide_score

    def test_low_liquidity_reduces_score(self, score_service, market_data):
        """Low liquidity should reduce score."""
        high_liq = MarketData(**{**market_data.__dict__, "liquidity": 100000.0})
        low_liq = MarketData(**{**market_data.__dict__, "liquidity": 1000.0})

        high_score = score_service.compute_score(high_liq)
        low_score = score_service.compute_score(low_liq)

        assert high_score > low_score

    def test_optimal_time_range_scores_best(self, score_service, market_data):
        """1-7 days to end should score best."""
        optimal = MarketData(**{**market_data.__dict__, "time_to_end_hours": 72.0})  # 3 days
        too_soon = MarketData(**{**market_data.__dict__, "time_to_end_hours": 2.0})  # 2 hours
        too_far = MarketData(**{**market_data.__dict__, "time_to_end_hours": 2000.0})  # 83 days

        optimal_score = score_service.compute_score(optimal)
        soon_score = score_service.compute_score(too_soon)
        far_score = score_service.compute_score(too_far)

        assert optimal_score >= soon_score
        assert optimal_score >= far_score

    def test_category_affects_score(self, score_service, market_data):
        """Different categories should affect score."""
        politics = MarketData(**{**market_data.__dict__, "category": "Politics"})
        unknown = MarketData(**{**market_data.__dict__, "category": "Unknown"})

        politics_score = score_service.compute_score(politics)
        unknown_score = score_service.compute_score(unknown)

        # Politics is historically more predictable
        assert politics_score >= unknown_score

    def test_low_quality_market_scores_low(self, score_service, low_quality_market):
        """Low quality market should score low."""
        score = score_service.compute_score(low_quality_market)

        # Should be below threshold
        assert score < 0.85

    def test_score_clamped_to_0_1(self, score_service, market_data):
        """Score should always be between 0 and 1."""
        # Even with extreme values
        market_data.price = 0.99
        market_data.liquidity = 1_000_000
        market_data.spread = 0.001

        score = score_service.compute_score(market_data)
        assert 0.0 <= score <= 1.0

        # And with terrible values
        market_data.price = 0.01
        market_data.liquidity = 0
        market_data.spread = 0.99

        score = score_service.compute_score(market_data)
        assert 0.0 <= score <= 1.0


# =============================================================================
# Get Score Tests
# =============================================================================


class TestGetScore:
    """Tests for score retrieval."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_score(self, score_service):
        """Returns None when no score exists."""
        await score_service.initialize()

        result = await score_service.get_score("tok_unknown", "0xunknown")

        assert result.score is None
        assert result.source == "none"

    @pytest.mark.asyncio
    async def test_memory_cache_hit(self, score_service):
        """Returns cached score from memory."""
        await score_service.initialize()

        # Pre-populate memory cache using condition_id as key (primary cache key)
        now = datetime.now(timezone.utc)
        score_service._memory_cache["0xtest"] = (0.95, "test-v1", now)

        result = await score_service.get_score("tok_cached", "0xtest")

        assert result.score == 0.95
        assert result.source == "memory"
        assert result.version == "test-v1"

    @pytest.mark.asyncio
    async def test_postgres_cache_hit(self, mock_db, score_service):
        """Returns score from PostgreSQL cache."""
        await score_service.initialize()

        # Mock the repository
        from polymarket_bot.storage.models import MarketScoresCache

        mock_cache = MagicMock(spec=MarketScoresCache)
        mock_cache.model_score = 0.92
        score_service._score_cache_repo.get_by_condition = AsyncMock(
            return_value=mock_cache
        )

        result = await score_service.get_score("tok_test", "0xcondition")

        assert result.score == 0.92
        assert result.source == "cache"

    @pytest.mark.asyncio
    async def test_legacy_fallback(self, score_service_with_legacy):
        """Falls back to legacy SQLite when PostgreSQL cache misses."""
        await score_service_with_legacy.initialize()

        # Mock the legacy bridge
        mock_bridge = MagicMock()
        mock_bridge.is_available.return_value = True
        mock_bridge.get_score.return_value = (0.88, "logit-v1")
        score_service_with_legacy._legacy_bridge = mock_bridge

        result = await score_service_with_legacy.get_score("tok_legacy", "0xcond")

        assert result.score == 0.88
        assert result.source == "legacy"
        assert result.version == "logit-v1"


# =============================================================================
# Compute and Cache Tests
# =============================================================================


class TestComputeAndCache:
    """Tests for compute_and_cache."""

    @pytest.mark.asyncio
    async def test_computes_and_caches_score(self, mock_db, market_data):
        """Computes score and caches in PostgreSQL."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()

        # Mock the repository upsert
        service._score_cache_repo.upsert = AsyncMock()

        result = await service.compute_and_cache(market_data)

        assert result.score is not None
        assert result.score >= 0.80  # High quality market
        assert result.source == "computed"
        assert result.version == "postgres-v1"

        # Should have called upsert
        service._score_cache_repo.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_memory_cache(self, mock_db, market_data):
        """Computed score should be in memory cache (keyed by condition_id)."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()
        service._score_cache_repo.upsert = AsyncMock()

        await service.compute_and_cache(market_data)

        # Memory cache now uses condition_id as key for consistency with PostgreSQL
        cache_key = market_data.condition_id or market_data.token_id
        assert cache_key in service._memory_cache
        cached_score, _, _ = service._memory_cache[cache_key]
        assert cached_score >= 0.80


# =============================================================================
# Get or Compute Tests
# =============================================================================


class TestGetOrCompute:
    """Tests for get_or_compute."""

    @pytest.mark.asyncio
    async def test_returns_existing_score(self, mock_db, market_data):
        """Returns existing score without recomputing."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()

        # Pre-populate cache using condition_id as key (consistent with new behavior)
        now = datetime.now(timezone.utc)
        cache_key = market_data.condition_id or market_data.token_id
        service._memory_cache[cache_key] = (0.93, "cached", now)

        result = await service.get_or_compute(
            token_id=market_data.token_id,
            condition_id=market_data.condition_id,
            market_data=market_data,
        )

        assert result.score == 0.93
        assert result.source == "memory"

    @pytest.mark.asyncio
    async def test_computes_when_no_existing_score(self, mock_db, market_data):
        """Computes new score when none exists."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()
        service._score_cache_repo.upsert = AsyncMock()

        result = await service.get_or_compute(
            token_id=market_data.token_id,
            condition_id=market_data.condition_id,
            market_data=market_data,
        )

        assert result.score is not None
        assert result.source == "computed"

    @pytest.mark.asyncio
    async def test_returns_none_without_market_data(self, mock_db):
        """Returns None when no score exists and no market data provided."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()

        result = await service.get_or_compute(
            token_id="tok_unknown",
            condition_id="0xunknown",
            market_data=None,
        )

        assert result.score is None
        assert result.source == "none"


# =============================================================================
# Weather Detection Tests (G6)
# =============================================================================


class TestWeatherDetection:
    """Tests for G6-safe weather detection."""

    def test_rainbow_six_not_weather(self, score_service):
        """Rainbow Six Siege should NOT be detected as weather (G6)."""
        assert score_service._is_weather("Will Team A win Rainbow Six Siege?") == 0

    def test_actual_weather_detected(self, score_service):
        """Actual weather markets should be detected."""
        assert score_service._is_weather("Will it rain in NYC tomorrow?") == 1
        assert score_service._is_weather("Hurricane makes landfall?") == 1
        assert score_service._is_weather("Will there be a storm in Texas?") == 1

    def test_case_insensitive(self, score_service):
        """Weather detection should be case insensitive."""
        assert score_service._is_weather("RAIN in NYC") == 1
        assert score_service._is_weather("Rain in NYC") == 1


# =============================================================================
# Stats Tests
# =============================================================================


class TestStats:
    """Tests for service statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_before_init(self, mock_db):
        """Stats should work before initialization."""
        service = ScoreService(mock_db)
        stats = service.get_stats()

        assert stats["initialized"] is False
        assert stats["memory_cache_size"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_after_init(self, mock_db):
        """Stats should reflect initialization."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()

        stats = service.get_stats()

        assert stats["initialized"] is True
        assert stats["use_legacy_fallback"] is False

    @pytest.mark.asyncio
    async def test_stats_track_cache_size(self, mock_db, market_data):
        """Stats should track memory cache size."""
        service = ScoreService(mock_db, use_legacy_fallback=False)
        await service.initialize()
        service._score_cache_repo.upsert = AsyncMock()

        await service.compute_and_cache(market_data)

        stats = service.get_stats()
        assert stats["memory_cache_size"] == 1


# =============================================================================
# Background Scorer Tests
# =============================================================================


class TestBackgroundScorer:
    """Tests for BackgroundScorer."""

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_db):
        """Background scorer can start and stop cleanly."""
        service = ScoreService(mock_db)
        await service.initialize()

        scorer = BackgroundScorer(service, mock_db, interval_seconds=1)

        await scorer.start()
        assert scorer._running is True
        assert scorer._task is not None

        await scorer.stop()
        assert scorer._running is False

    @pytest.mark.asyncio
    async def test_does_not_double_start(self, mock_db):
        """Calling start twice doesn't create multiple tasks."""
        service = ScoreService(mock_db)
        await service.initialize()

        scorer = BackgroundScorer(service, mock_db, interval_seconds=1)

        await scorer.start()
        first_task = scorer._task

        await scorer.start()  # Second start
        assert scorer._task is first_task  # Same task

        await scorer.stop()
