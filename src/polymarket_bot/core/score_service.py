"""
Score Service - Unified scoring service for model_score.

This service replaces the fragmented scoring architecture:
- Old: ScoreBridge (read-only from legacy SQLite, no new scores)
- New: Unified service using PostgreSQL as primary store

Key capabilities:
1. Computes scores for NEW markets (not just legacy)
2. Uses PostgreSQL market_scores_cache as primary store
3. Falls back to ScoreBridge for legacy tokens
4. Provides background scoring for continuous updates

The scoring formula combines:
- Price proximity to threshold (higher price = higher confidence)
- Liquidity (more liquid = more tradeable)
- Time to resolution (moderate time = more predictable)
- Category factors (some categories more predictable)
- Spread (tighter spread = better execution)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from .score_bridge import ScoreBridge, get_score_bridge

if TYPE_CHECKING:
    from polymarket_bot.storage.database import Database
    from polymarket_bot.storage.models import MarketScoresCache

logger = logging.getLogger(__name__)

# Scoring configuration
DEFAULT_SCORE_VERSION = "postgres-v1"


@dataclass
class ScoreResult:
    """Result of a score lookup/computation."""

    score: Optional[float]
    version: Optional[str]
    source: str  # "computed", "cache", "legacy", "none"
    computed_at: Optional[datetime] = None


@dataclass
class MarketData:
    """Input data for score computation."""

    condition_id: str
    token_id: str
    question: str
    category: Optional[str]
    price: float  # Current best bid or mid price
    spread: Optional[float]  # Bid-ask spread (0-1)
    liquidity: Optional[float]  # Total liquidity in $
    volume_24h: Optional[float]  # 24h volume in $
    time_to_end_hours: Optional[float]  # Hours until resolution
    outcome: Optional[str] = None  # "Yes" or "No"


class ScoreService:
    """
    Unified scoring service for model_score.

    Provides a single interface for getting scores, whether from:
    - PostgreSQL cache (primary)
    - Computed on-demand (for new markets)
    - Legacy SQLite (fallback for old tokens)

    Usage:
        service = ScoreService(db)
        await service.initialize()

        # Get score for a token
        result = await service.get_score(token_id, condition_id)
        if result.score:
            print(f"Score: {result.score} from {result.source}")

        # Or compute for new market
        result = await service.compute_and_cache(market_data)
    """

    def __init__(
        self,
        db: "Database",
        use_legacy_fallback: bool = True,
        score_threshold: float = 0.85,  # Minimum score to be interesting
        price_weight: float = 0.35,  # Weight of price in score
        liquidity_weight: float = 0.20,
        time_weight: float = 0.15,
        spread_weight: float = 0.15,
        category_weight: float = 0.15,
    ):
        self._db = db
        self._use_legacy_fallback = use_legacy_fallback
        self._score_threshold = score_threshold

        # Score weights (must sum to 1.0)
        self._price_weight = price_weight
        self._liquidity_weight = liquidity_weight
        self._time_weight = time_weight
        self._spread_weight = spread_weight
        self._category_weight = category_weight

        # Lazy-loaded components
        self._score_cache_repo: Optional["MarketScoresCacheRepository"] = None
        self._legacy_bridge: Optional[ScoreBridge] = None
        self._initialized = False

        # In-memory cache for hot tokens
        self._memory_cache: dict[str, tuple[float, str, datetime]] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    async def initialize(self) -> None:
        """Initialize the service and repositories."""
        if self._initialized:
            return

        from polymarket_bot.storage.repositories.watchlist_repo import (
            MarketScoresCacheRepository,
        )

        self._score_cache_repo = MarketScoresCacheRepository(self._db)

        if self._use_legacy_fallback:
            self._legacy_bridge = get_score_bridge()

        self._initialized = True
        logger.info(
            f"ScoreService initialized (legacy_fallback={self._use_legacy_fallback})"
        )

    async def get_score(
        self,
        token_id: str,
        condition_id: Optional[str] = None,
    ) -> ScoreResult:
        """
        Get score for a token, checking all sources.

        Priority:
        1. Memory cache (hot path) - keyed by condition_id for consistency
        2. PostgreSQL cache
        3. Legacy SQLite (if enabled and configured)
        4. None (no score available)

        Args:
            token_id: Token ID to look up
            condition_id: Optional condition ID for cache lookup (preferred)

        Returns:
            ScoreResult with score, version, and source
        """
        if not self._initialized:
            await self.initialize()

        # Use condition_id as primary cache key for consistency with PostgreSQL
        cache_key = condition_id or token_id

        # 1. Check memory cache
        if cache_key in self._memory_cache:
            score, version, cached_at = self._memory_cache[cache_key]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < self._cache_ttl_seconds:
                return ScoreResult(
                    score=score,
                    version=version,
                    source="memory",
                    computed_at=cached_at,
                )
            # Expired, remove from cache
            del self._memory_cache[cache_key]

        # 2. Check PostgreSQL cache
        if condition_id and self._score_cache_repo:
            try:
                cache = await self._score_cache_repo.get_by_condition(condition_id)
                if cache and cache.model_score is not None:
                    # Update memory cache
                    now = datetime.now(timezone.utc)
                    self._memory_cache[cache_key] = (
                        cache.model_score,
                        DEFAULT_SCORE_VERSION,
                        now,
                    )
                    return ScoreResult(
                        score=cache.model_score,
                        version=DEFAULT_SCORE_VERSION,
                        source="cache",
                        computed_at=now,
                    )
            except Exception as e:
                logger.warning(f"PostgreSQL cache lookup failed for {condition_id[:16]}...: {e}")

        # 3. Check legacy SQLite (only if explicitly enabled)
        if self._use_legacy_fallback and self._legacy_bridge and self._legacy_bridge.is_available():
            score, version = self._legacy_bridge.get_score(token_id)
            if score is not None:
                logger.debug(f"Score from legacy SQLite for {token_id[:16]}...")
                # Update memory cache
                now = datetime.now(timezone.utc)
                self._memory_cache[cache_key] = (score, version or "legacy", now)
                return ScoreResult(
                    score=score,
                    version=version,
                    source="legacy",
                    computed_at=now,
                )

        # 4. No score found
        return ScoreResult(score=None, version=None, source="none")

    def compute_score(self, market: MarketData) -> float:
        """
        Compute a model score for a market.

        The score represents confidence that this market will resolve
        in the expected direction (for high-prob-yes: that Yes wins).

        Score formula:
        - Price component: Higher price = higher implicit confidence
        - Liquidity component: More liquid = more reliable price discovery
        - Time component: 1-30 days optimal (not too soon, not too far)
        - Spread component: Tighter spread = better price quality
        - Category component: Some categories more predictable

        Returns:
            Score between 0.0 and 1.0
        """
        score = 0.0

        # 1. PRICE COMPONENT (0-1)
        # Higher price = market agrees event is likely
        # For high-prob-yes strategy, we want prices near 1.0
        if market.price >= 0.95:
            # At or above threshold - high confidence
            price_score = 0.9 + (min(market.price, 0.99) - 0.95) * 2.0
        elif market.price >= 0.90:
            # Approaching threshold
            price_score = 0.7 + (market.price - 0.90) * 4.0
        elif market.price >= 0.80:
            price_score = 0.5 + (market.price - 0.80) * 2.0
        else:
            price_score = market.price * 0.625  # Linear scale up to 0.5

        score += price_score * self._price_weight

        # 2. LIQUIDITY COMPONENT (0-1)
        # More liquidity = more reliable price discovery
        if market.liquidity:
            if market.liquidity >= 100_000:
                liq_score = 1.0
            elif market.liquidity >= 50_000:
                liq_score = 0.9
            elif market.liquidity >= 20_000:
                liq_score = 0.8
            elif market.liquidity >= 10_000:
                liq_score = 0.7
            elif market.liquidity >= 5_000:
                liq_score = 0.6
            else:
                liq_score = 0.5 * (market.liquidity / 5_000)
        else:
            liq_score = 0.5  # Unknown liquidity

        score += liq_score * self._liquidity_weight

        # 3. TIME COMPONENT (0-1)
        # Sweet spot: 1-30 days (24-720 hours)
        # Too soon: Might be manipulation
        # Too far: Too much uncertainty
        if market.time_to_end_hours is not None:
            hours = market.time_to_end_hours
            if 24 <= hours <= 168:  # 1-7 days
                time_score = 1.0  # Optimal
            elif 168 < hours <= 720:  # 7-30 days
                time_score = 0.9
            elif 6 <= hours < 24:  # 6-24 hours
                time_score = 0.7  # Bit risky
            elif hours > 720:  # > 30 days
                # Decay for very long markets
                time_score = 0.8 * (720 / min(hours, 2160))
            else:  # < 6 hours
                time_score = 0.5  # High risk
        else:
            time_score = 0.6  # Unknown timing

        score += time_score * self._time_weight

        # 4. SPREAD COMPONENT (0-1)
        # Tighter spread = better price quality
        if market.spread is not None:
            if market.spread <= 0.01:  # 1%
                spread_score = 1.0
            elif market.spread <= 0.02:  # 2%
                spread_score = 0.95
            elif market.spread <= 0.05:  # 5%
                spread_score = 0.85
            elif market.spread <= 0.10:  # 10%
                spread_score = 0.7
            elif market.spread <= 0.20:  # 20%
                spread_score = 0.5
            else:
                spread_score = 0.3  # Wide spread = risky
        else:
            spread_score = 0.6  # Unknown spread

        score += spread_score * self._spread_weight

        # 5. CATEGORY COMPONENT (0-1)
        # Some categories more predictable historically
        category = (market.category or "").lower()
        category_scores = {
            "politics": 0.9,  # Generally predictable near resolution
            "crypto": 0.8,
            "economics": 0.85,
            "science": 0.9,
            "sports": 0.75,  # Can be volatile
            "entertainment": 0.7,
            "technology": 0.8,
        }
        category_score = category_scores.get(category, 0.7)

        score += category_score * self._category_weight

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))

    async def compute_and_cache(
        self,
        market: MarketData,
    ) -> ScoreResult:
        """
        Compute score for a market and cache it.

        This is the primary method for scoring NEW markets that
        don't exist in the legacy system.

        IMPORTANT: Always returns a computed score even if caching fails.
        This ensures scoring is resilient to transient DB errors.

        Args:
            market: Market data for scoring

        Returns:
            ScoreResult with computed score
        """
        if not self._initialized:
            await self.initialize()

        score = self.compute_score(market)
        now = datetime.now(timezone.utc)

        # Update PostgreSQL cache (best-effort - don't fail scoring on cache errors)
        if self._score_cache_repo and market.condition_id:
            try:
                from polymarket_bot.storage.models import MarketScoresCache

                cache = MarketScoresCache(
                    condition_id=market.condition_id,
                    market_id=None,
                    question=market.question,
                    category=market.category,
                    best_bid=market.price,
                    best_ask=market.price + (market.spread or 0.02),
                    spread_pct=market.spread,
                    liquidity=market.liquidity,
                    volume=market.volume_24h,
                    end_date=None,
                    time_to_end_hours=market.time_to_end_hours,
                    model_score=score,
                    passes_filters=1 if score >= self._score_threshold else 0,
                    filter_rejections=None,
                    is_weather=self._is_weather(market.question),
                    is_crypto=self._is_category(market.category, "crypto"),
                    is_politics=self._is_category(market.category, "politics"),
                    is_sports=self._is_category(market.category, "sports"),
                    updated_at=now.isoformat(),
                )
                await self._score_cache_repo.upsert(cache)
            except Exception as e:
                # Log but don't fail - score is still valid
                logger.warning(
                    f"Failed to cache score for {market.condition_id[:16]}...: {e}"
                )

        # Update memory cache using condition_id as key (consistent with PostgreSQL)
        cache_key = market.condition_id or market.token_id
        self._memory_cache[cache_key] = (score, DEFAULT_SCORE_VERSION, now)

        logger.debug(
            f"Computed score {score:.3f} for {market.condition_id[:16]}..."
        )

        return ScoreResult(
            score=score,
            version=DEFAULT_SCORE_VERSION,
            source="computed",
            computed_at=now,
        )

    async def get_or_compute(
        self,
        token_id: str,
        condition_id: str,
        market_data: Optional[MarketData] = None,
    ) -> ScoreResult:
        """
        Get existing score or compute a new one.

        This is the recommended method for getting scores:
        1. First tries to get cached/legacy score
        2. If not found and market_data provided, computes new score
        3. Returns None if no score and no data to compute

        Args:
            token_id: Token ID
            condition_id: Condition ID
            market_data: Optional market data for computing new score

        Returns:
            ScoreResult (may have None score if not computable)
        """
        # Try to get existing score
        result = await self.get_score(token_id, condition_id)

        if result.score is not None:
            return result

        # No existing score - compute if we have data
        if market_data is not None:
            return await self.compute_and_cache(market_data)

        return result  # No score, source="none"

    def _is_weather(self, question: str) -> int:
        """Check if question is about weather (G6-safe)."""
        import re

        # Word-boundary pattern to avoid Rainbow Six bug
        pattern = r"\b(rain|snow|hurricane|storm|weather|tornado|flood|drought)\b"
        return 1 if re.search(pattern, question.lower()) else 0

    def _is_category(self, category: Optional[str], target: str) -> int:
        """Check if category matches target."""
        if not category:
            return 0
        return 1 if category.lower() == target.lower() else 0

    def get_stats(self) -> dict:
        """Get service statistics."""
        return {
            "initialized": self._initialized,
            "memory_cache_size": len(self._memory_cache),
            "cache_ttl_seconds": self._cache_ttl_seconds,
            "use_legacy_fallback": self._use_legacy_fallback,
            "legacy_available": (
                self._legacy_bridge.is_available()
                if self._legacy_bridge
                else False
            ),
            "score_threshold": self._score_threshold,
        }


class BackgroundScorer:
    """
    Background worker that scores markets continuously.

    This ensures:
    1. New markets get scores proactively
    2. Existing scores are refreshed as market conditions change
    3. Time-based components update as resolution approaches

    Usage:
        scorer = BackgroundScorer(score_service, db)
        await scorer.start()
        # ... runs in background ...
        await scorer.stop()
    """

    def __init__(
        self,
        score_service: ScoreService,
        db: "Database",
        interval_seconds: int = 300,  # 5 minutes
        batch_size: int = 100,
        stale_threshold_seconds: int = 3600,  # Re-score after 1 hour
    ):
        self._score_service = score_service
        self._db = db
        self._interval = interval_seconds
        self._batch_size = batch_size
        self._stale_threshold = stale_threshold_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background scoring."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"BackgroundScorer started (interval={self._interval}s, batch={self._batch_size})"
        )

    async def stop(self) -> None:
        """Stop background scoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BackgroundScorer stopped")

    async def _run_loop(self) -> None:
        """Main scoring loop."""
        while self._running:
            try:
                # Sleep first to let startup complete
                await asyncio.sleep(self._interval)

                if not self._running:
                    break

                # Score markets that need it
                scored = await self._score_batch()
                if scored > 0:
                    logger.info(f"BackgroundScorer: Scored {scored} markets")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"BackgroundScorer error: {e}")
                await asyncio.sleep(60)  # Back off on error

    async def _score_batch(self) -> int:
        """
        Score a batch of markets that need scoring.

        Targets:
        1. Markets in pipeline candidates (actively being watched)
        2. Markets with stale scores (> 1 hour old)
        3. High-price markets approaching threshold
        """
        scored = 0

        try:
            # 1. Re-score pipeline candidates (most important)
            scored += await self._rescore_candidates()

            # 2. Re-score stale entries in market_scores_cache
            scored += await self._rescore_stale()

            # 3. Score new high-probability markets from watchlist
            scored += await self._score_watchlist_markets()

        except Exception as e:
            logger.warning(f"BackgroundScorer batch error: {e}")

        return scored

    async def _rescore_candidates(self) -> int:
        """Re-score markets currently in the pipeline."""
        query = """
            SELECT DISTINCT pc.condition_id, pc.token_id,
                   tm.question, sw.category, pc.price,
                   sw.liquidity, sw.volume,
                   EXTRACT(EPOCH FROM (sw.end_date::timestamp - NOW())) / 3600 as time_to_end_hours,
                   pc.outcome
            FROM polymarket_candidates pc
            LEFT JOIN polymarket_token_meta tm ON pc.token_id = tm.token_id
            LEFT JOIN stream_watchlist sw ON tm.market_id = sw.market_id
            WHERE pc.status = 'pending'
            ORDER BY pc.price DESC
            LIMIT $1
        """

        try:
            rows = await self._db.fetch(query, self._batch_size)
        except Exception:
            return 0

        scored = 0
        for row in rows:
            try:
                market_data = MarketData(
                    condition_id=row.get("condition_id", ""),
                    token_id=row.get("token_id", ""),
                    question=row.get("question", ""),
                    category=row.get("category"),
                    price=float(row.get("price", 0) or 0),
                    spread=None,
                    liquidity=row.get("liquidity"),
                    volume_24h=row.get("volume"),
                    time_to_end_hours=row.get("time_to_end_hours"),
                    outcome=row.get("outcome"),
                )

                await self._score_service.compute_and_cache(market_data)
                scored += 1

            except Exception as e:
                logger.debug(f"Failed to score candidate: {e}")

        return scored

    async def _rescore_stale(self) -> int:
        """Re-score entries with stale scores."""
        # Find entries that haven't been updated recently
        query = """
            SELECT condition_id, market_id, question, category,
                   best_bid as price, spread_pct as spread,
                   liquidity, volume, time_to_end_hours
            FROM market_scores_cache
            WHERE updated_at < NOW() - INTERVAL '%s seconds'
              AND model_score IS NOT NULL
            ORDER BY model_score DESC
            LIMIT $1
        """ % self._stale_threshold

        try:
            rows = await self._db.fetch(query, self._batch_size // 2)
        except Exception:
            return 0

        scored = 0
        for row in rows:
            try:
                # Need to get token_id from condition_id
                token_query = """
                    SELECT token_id FROM polymarket_token_meta
                    WHERE condition_id = $1
                    LIMIT 1
                """
                token_row = await self._db.fetchrow(token_query, row.get("condition_id"))
                token_id = token_row.get("token_id") if token_row else row.get("condition_id", "")

                market_data = MarketData(
                    condition_id=row.get("condition_id", ""),
                    token_id=token_id,
                    question=row.get("question", ""),
                    category=row.get("category"),
                    price=float(row.get("price", 0) or 0),
                    spread=row.get("spread"),
                    liquidity=row.get("liquidity"),
                    volume_24h=row.get("volume"),
                    time_to_end_hours=row.get("time_to_end_hours"),
                    outcome=None,
                )

                await self._score_service.compute_and_cache(market_data)
                scored += 1

            except Exception as e:
                logger.debug(f"Failed to rescore stale entry: {e}")

        return scored

    async def _score_watchlist_markets(self) -> int:
        """Score markets on the trade watchlist that lack scores."""
        query = """
            SELECT tw.token_id, tw.condition_id, tw.question,
                   tw.trigger_price as price, tw.time_to_end_hours,
                   sw.category, sw.liquidity, sw.volume
            FROM trade_watchlist tw
            LEFT JOIN polymarket_token_meta tm ON tw.token_id = tm.token_id
            LEFT JOIN stream_watchlist sw ON tm.market_id = sw.market_id
            LEFT JOIN market_scores_cache msc ON tw.condition_id = msc.condition_id
            WHERE tw.status = 'watching'
              AND msc.model_score IS NULL
            LIMIT $1
        """

        try:
            rows = await self._db.fetch(query, self._batch_size // 4)
        except Exception:
            return 0

        scored = 0
        for row in rows:
            try:
                market_data = MarketData(
                    condition_id=row.get("condition_id", ""),
                    token_id=row.get("token_id", ""),
                    question=row.get("question", ""),
                    category=row.get("category"),
                    price=float(row.get("price", 0) or 0),
                    spread=None,
                    liquidity=row.get("liquidity"),
                    volume_24h=row.get("volume"),
                    time_to_end_hours=row.get("time_to_end_hours"),
                    outcome=None,
                )

                await self._score_service.compute_and_cache(market_data)
                scored += 1

            except Exception as e:
                logger.debug(f"Failed to score watchlist entry: {e}")

        return scored


# Module-level singleton for convenience
_default_service: Optional[ScoreService] = None


async def get_score_service(db: "Database") -> ScoreService:
    """Get or create the default score service."""
    global _default_service
    if _default_service is None:
        _default_service = ScoreService(db)
        await _default_service.initialize()
    return _default_service
