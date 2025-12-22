"""
Interestingness Scoring for Market Discovery.

Computes a strategy-agnostic score (0-100) that indicates how likely
a market is to be interesting to SOME strategy.

This is NOT a trading signal - just a prioritization metric for
determining which markets deserve closer monitoring (higher tiers).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from math import log10
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MarketMetrics:
    """Input metrics for scoring a market."""

    condition_id: str
    price: Optional[float]  # Primary outcome price (0-1)
    volume_24h: float
    liquidity: float
    trade_count_24h: int
    price_change_24h: float
    price_change_1h: float
    spread: float
    days_to_end: Optional[float]
    market_age_days: Optional[float]
    category: Optional[str]
    outcome_count: int = 2


# Category boosts based on historical predictability/profitability
CATEGORY_BOOSTS = {
    "politics": 5,
    "crypto": 3,
    "sports": 2,
    "science": 4,
    "economics": 4,
    "entertainment": 1,
    "technology": 3,
}


def compute_interestingness(m: MarketMetrics) -> float:
    """
    Compute strategy-agnostic interestingness score (0-100).

    Higher scores = more likely to be interesting to SOME strategy.
    This is NOT a trading signal, just a prioritization metric.

    Scoring breakdown:
    - Volume & Liquidity: max 25 points
    - Price Movement: max 25 points
    - Market Timing: max 20 points
    - Price Extremes: max 20 points
    - Category Boost: max 10 points
    - Spread Penalty: up to -10 points
    """
    score = 0.0

    # ═══════════════════════════════════════════════════════════════════════
    # VOLUME & LIQUIDITY (max 25 points)
    # More volume = more tradeable, more attention
    # ═══════════════════════════════════════════════════════════════════════

    # Volume score: log scale, max at $1M/day
    if m.volume_24h > 0:
        # log10(1M) = 6, so normalize by 6
        volume_score = min(15, 15 * (log10(m.volume_24h + 1) / 6))
        score += volume_score

    # Liquidity score: max at $100K
    if m.liquidity > 0:
        liquidity_score = min(10, 10 * (m.liquidity / 100_000))
        score += liquidity_score

    # ═══════════════════════════════════════════════════════════════════════
    # PRICE MOVEMENT (max 25 points)
    # Movement = something happening = potential opportunity
    # ═══════════════════════════════════════════════════════════════════════

    # 24h price change (absolute value matters)
    # 10% move = 15 pts
    change_24h_score = min(15, abs(m.price_change_24h) * 150)
    score += change_24h_score

    # 1h price change (recent momentum)
    # 5% move = 10 pts
    change_1h_score = min(10, abs(m.price_change_1h) * 200)
    score += change_1h_score

    # ═══════════════════════════════════════════════════════════════════════
    # MARKET TIMING (max 20 points)
    # New markets and near-resolution markets are interesting
    # ═══════════════════════════════════════════════════════════════════════

    # New market bonus (< 7 days old)
    if m.market_age_days is not None and m.market_age_days < 7:
        new_market_score = 10 * (1 - m.market_age_days / 7)
        score += new_market_score

    # Near resolution bonus (< 14 days to end)
    if m.days_to_end is not None and m.days_to_end < 14:
        resolution_score = 10 * (1 - m.days_to_end / 14)
        score += resolution_score

    # ═══════════════════════════════════════════════════════════════════════
    # PRICE EXTREMES (max 20 points)
    # Extreme prices (near 0 or 1) are interesting to different strategies
    # ═══════════════════════════════════════════════════════════════════════

    if m.price is not None:
        # High probability (>90%) - interesting for high_prob strategies
        if m.price > 0.90:
            high_prob_score = 10 * ((m.price - 0.90) / 0.10)
            score += high_prob_score

        # Low probability (<10%) - interesting for moonshot strategies
        if m.price < 0.10:
            low_prob_score = 10 * ((0.10 - m.price) / 0.10)
            score += low_prob_score

        # Mid-range with high volume (competitive/uncertain) - interesting for arb
        if 0.40 < m.price < 0.60 and m.volume_24h > 50_000:
            uncertainty_score = 5
            score += uncertainty_score

    # ═══════════════════════════════════════════════════════════════════════
    # SPREAD PENALTY (max -10 points)
    # Wide spreads make trading expensive
    # ═══════════════════════════════════════════════════════════════════════

    if m.spread > 0.05:  # > 5% spread
        spread_penalty = min(10, (m.spread - 0.05) * 100)
        score -= spread_penalty

    # ═══════════════════════════════════════════════════════════════════════
    # CATEGORY BOOST (max 10 points)
    # Some categories historically more predictable/profitable
    # ═══════════════════════════════════════════════════════════════════════

    if m.category:
        category_lower = m.category.lower()
        boost = CATEGORY_BOOSTS.get(category_lower, 0)
        score += boost

    # ═══════════════════════════════════════════════════════════════════════
    # MULTI-OUTCOME PENALTY
    # Multi-outcome markets are harder to trade, slight penalty
    # ═══════════════════════════════════════════════════════════════════════

    if m.outcome_count > 2:
        score -= 5

    # Clamp to 0-100
    return max(0, min(100, score))


def get_tier_recommendation(score: float) -> int:
    """
    Get recommended tier based on interestingness score.

    Score Range | Tier | Description
    0-20        | 1    | Low activity, metadata only
    20-40       | 1    | Worth watching but not tracking
    40-60       | 2    | Track price history
    60-80       | 2    | High potential, close monitoring
    80-100      | 3    | Active monitoring with full data
    """
    if score >= 80:
        return 3
    elif score >= 40:
        return 2
    else:
        return 1


def score_market_batch(
    markets: list[MarketMetrics],
) -> dict[str, tuple[float, int]]:
    """
    Score a batch of markets.

    Returns dict of condition_id -> (score, recommended_tier)
    """
    results = {}
    for m in markets:
        score = compute_interestingness(m)
        tier = get_tier_recommendation(score)
        results[m.condition_id] = (score, tier)
    return results
