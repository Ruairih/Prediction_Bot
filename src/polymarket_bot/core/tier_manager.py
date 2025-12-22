"""
Tier Manager - Handles market tier promotion and demotion.

Manages the flow of markets between tiers:
- Tier 1 (Universe): All markets, metadata only
- Tier 2 (History): Interesting markets, price candles
- Tier 3 (Trades): Active markets, full trade data

Respects:
- Capacity limits per tier
- Pinned tiers (manual overrides)
- Hysteresis to prevent churn
- Strategy requests
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from polymarket_bot.core.scoring import MarketMetrics, compute_interestingness
from polymarket_bot.storage.models import MarketUniverse, StrategyTierRequest

if TYPE_CHECKING:
    from polymarket_bot.storage.repositories.universe_repo import MarketUniverseRepository
    from polymarket_bot.storage.repositories.position_repo import PositionRepository
    from polymarket_bot.storage.repositories.order_repo import LiveOrderRepository

logger = logging.getLogger(__name__)


@dataclass
class TierLimits:
    """Capacity limits for each tier."""

    tier_2_max: int = 2000
    tier_3_max: int = 300


@dataclass
class TierThresholds:
    """Score thresholds for tier transitions."""

    # Promotion thresholds
    promote_to_tier_2_score: float = 40.0
    promote_to_tier_3_score: float = 80.0

    # Demotion thresholds (lower than promotion = hysteresis)
    demote_from_tier_3_score: float = 60.0
    demote_from_tier_2_score: float = 20.0

    # Time thresholds for demotion
    tier_3_inactivity_hours: int = 24
    tier_2_low_score_days: int = 7


@dataclass
class TierStats:
    """Statistics from a promotion cycle."""

    promoted_to_tier_2: int = 0
    promoted_to_tier_3: int = 0
    demoted_to_tier_2: int = 0
    demoted_to_tier_1: int = 0
    scores_updated: int = 0
    requests_processed: int = 0


class TierManager:
    """
    Manages market tier promotions and demotions.

    Key principles:
    1. Deterministic selection (by score, not random)
    2. Capacity enforcement (won't exceed limits)
    3. Hysteresis (promotion threshold > demotion threshold)
    4. Respect manual overrides (pinned_tier)
    """

    def __init__(
        self,
        universe_repo: "MarketUniverseRepository",
        position_repo: Optional["PositionRepository"] = None,
        order_repo: Optional["LiveOrderRepository"] = None,
        limits: Optional[TierLimits] = None,
        thresholds: Optional[TierThresholds] = None,
    ):
        self.universe_repo = universe_repo
        self.position_repo = position_repo
        self.order_repo = order_repo
        self.limits = limits or TierLimits()
        self.thresholds = thresholds or TierThresholds()

    async def run_promotion_cycle(self) -> TierStats:
        """
        Run full promotion/demotion cycle.

        Called every 15 minutes by background task.
        """
        stats = TierStats()

        # 1. Process strategy tier requests first
        stats.requests_processed = await self._process_tier_requests()

        # 2. Promote from Tier 1 → Tier 2
        stats.promoted_to_tier_2 = await self._promote_to_tier_2()

        # 3. Promote from Tier 2 → Tier 3
        stats.promoted_to_tier_3 = await self._promote_to_tier_3()

        # 4. Demote inactive Tier 3 → Tier 2
        stats.demoted_to_tier_2 = await self._demote_from_tier_3()

        # 5. Demote low-score Tier 2 → Tier 1
        stats.demoted_to_tier_1 = await self._demote_from_tier_2()

        # 6. Clean up expired requests
        await self.universe_repo.cleanup_expired_requests()

        logger.info(
            f"Tier cycle complete: +{stats.promoted_to_tier_2} T2, "
            f"+{stats.promoted_to_tier_3} T3, "
            f"-{stats.demoted_to_tier_2} from T3, "
            f"-{stats.demoted_to_tier_1} from T2"
        )

        return stats

    async def _process_tier_requests(self) -> int:
        """Process strategy tier requests, respecting tier capacity."""
        requests = await self.universe_repo.get_active_tier_requests()
        tier_counts = await self.universe_repo.get_tier_counts()

        # Track how many slots available per tier
        tier_2_available = self.limits.tier_2_max - tier_counts.get(2, 0)
        tier_3_available = self.limits.tier_3_max - tier_counts.get(3, 0)

        count = 0
        # Sort by tier descending so Tier 3 requests are processed first
        sorted_requests = sorted(requests, key=lambda r: -r.requested_tier)

        for req in sorted_requests:
            # Check capacity
            if req.requested_tier == 3 and tier_3_available <= 0:
                continue
            if req.requested_tier == 2 and tier_2_available <= 0:
                continue

            promoted = await self.universe_repo.promote(
                req.condition_id,
                req.requested_tier,
                reason=f"Strategy request: {req.reason}",
            )
            if promoted:
                count += 1
                if req.requested_tier == 3:
                    tier_3_available -= 1
                elif req.requested_tier == 2:
                    tier_2_available -= 1

        return count

    async def _promote_to_tier_2(self) -> int:
        """Promote high-scoring Tier 1 markets to Tier 2."""
        from polymarket_bot.storage.repositories.universe_repo import MarketQuery

        # Get current tier 2 count
        tier_counts = await self.universe_repo.get_tier_counts()
        current_tier_2 = tier_counts.get(2, 0)
        available_slots = max(0, self.limits.tier_2_max - current_tier_2)

        if available_slots == 0:
            return 0

        # Find candidates: Tier 1 markets with score >= threshold
        candidates = await self.universe_repo.query(
            MarketQuery(
                tier=1,
                min_interestingness=self.thresholds.promote_to_tier_2_score,
                limit=available_slots,
            )
        )

        count = 0
        for market in candidates:
            promoted = await self.universe_repo.promote(
                market.condition_id,
                target_tier=2,
                reason=f"Score {market.interestingness_score:.1f} >= {self.thresholds.promote_to_tier_2_score}",
            )
            if promoted:
                count += 1

        return count

    async def _promote_to_tier_3(self) -> int:
        """Promote high-priority Tier 2 markets to Tier 3."""
        tier_counts = await self.universe_repo.get_tier_counts()
        current_tier_3 = tier_counts.get(3, 0)
        available_slots = max(0, self.limits.tier_3_max - current_tier_3)

        if available_slots == 0:
            return 0

        # Get condition_ids with open positions
        position_conditions = set()
        if self.position_repo:
            open_positions = await self.position_repo.get_open()
            position_conditions = {p.condition_id for p in open_positions if p.condition_id}

        # Get condition_ids with pending orders
        order_conditions = set()
        if self.order_repo:
            active_orders = await self.order_repo.get_active()
            order_conditions = {o.condition_id for o in active_orders if o.condition_id}

        # Priority 1: Markets with positions or orders (must be Tier 3)
        must_promote = position_conditions | order_conditions
        count = 0

        for condition_id in must_promote:
            if count >= available_slots:
                break
            promoted = await self.universe_repo.promote(
                condition_id,
                target_tier=3,
                reason="Has open position or order",
            )
            if promoted:
                count += 1
                available_slots -= 1

        if available_slots <= 0:
            return count

        # Priority 2: High-score markets
        from polymarket_bot.storage.repositories.universe_repo import MarketQuery

        candidates = await self.universe_repo.query(
            MarketQuery(
                tier=2,
                min_interestingness=self.thresholds.promote_to_tier_3_score,
                limit=available_slots,
            )
        )

        for market in candidates:
            if market.condition_id in must_promote:
                continue  # Already promoted
            promoted = await self.universe_repo.promote(
                market.condition_id,
                target_tier=3,
                reason=f"Score {market.interestingness_score:.1f} >= {self.thresholds.promote_to_tier_3_score}",
            )
            if promoted:
                count += 1

        return count

    async def _demote_from_tier_3(self) -> int:
        """Demote inactive Tier 3 markets to Tier 2."""
        # Get condition_ids with open positions (can't demote these)
        protected_conditions = set()
        if self.position_repo:
            open_positions = await self.position_repo.get_open()
            protected_conditions.update(p.condition_id for p in open_positions if p.condition_id)

        if self.order_repo:
            active_orders = await self.order_repo.get_active()
            protected_conditions.update(o.condition_id for o in active_orders if o.condition_id)

        # Find Tier 3 markets that are inactive
        tier_3_markets = await self.universe_repo.get_by_tier(3)
        inactivity_threshold = datetime.utcnow() - timedelta(
            hours=self.thresholds.tier_3_inactivity_hours
        )

        count = 0
        for market in tier_3_markets:
            # Skip protected markets
            if market.condition_id in protected_conditions:
                continue

            # Skip pinned markets
            if market.pinned_tier and market.pinned_tier >= 3:
                continue

            # Check if inactive
            last_signal = market.last_strategy_signal_at
            if last_signal and last_signal >= inactivity_threshold:
                continue

            # Check if score dropped below demotion threshold
            if market.interestingness_score >= self.thresholds.demote_from_tier_3_score:
                continue

            # Demote
            demoted = await self.universe_repo.demote(
                market.condition_id,
                target_tier=2,
            )
            if demoted:
                count += 1

        return count

    async def _demote_from_tier_2(self) -> int:
        """Demote low-score Tier 2 markets to Tier 1."""
        # Find Tier 2 markets with low score for extended period
        tier_2_markets = await self.universe_repo.get_by_tier(2)
        low_score_threshold = datetime.utcnow() - timedelta(
            days=self.thresholds.tier_2_low_score_days
        )

        count = 0
        for market in tier_2_markets:
            # Skip pinned markets
            if market.pinned_tier and market.pinned_tier >= 2:
                continue

            # Check score
            if market.interestingness_score >= self.thresholds.demote_from_tier_2_score:
                continue

            # Check if low score for long enough
            if market.score_below_threshold_since is None:
                continue
            if market.score_below_threshold_since > low_score_threshold:
                continue

            # Demote
            demoted = await self.universe_repo.demote(
                market.condition_id,
                target_tier=1,
            )
            if demoted:
                count += 1

        return count

    async def request_tier(
        self,
        strategy_name: str,
        condition_id: str,
        tier: int,
        reason: str,
        ttl_hours: int = 1,
    ) -> None:
        """
        Strategy requests a market be promoted to a specific tier.

        The request expires after ttl_hours to prevent stale promotions.
        """
        request = StrategyTierRequest(
            strategy_name=strategy_name,
            condition_id=condition_id,
            requested_tier=tier,
            reason=reason,
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
        )
        await self.universe_repo.create_tier_request(request)
        logger.debug(f"Tier request: {strategy_name} wants {condition_id} at tier {tier}")

    async def update_scores_for_markets(self, markets: list[MarketUniverse]) -> int:
        """Update interestingness scores for a batch of markets."""
        scores = {}

        for m in markets:
            metrics = MarketMetrics(
                condition_id=m.condition_id,
                price=m.price,
                volume_24h=m.volume_24h,
                liquidity=m.liquidity,
                trade_count_24h=m.trade_count_24h,
                price_change_24h=m.price_change_24h,
                price_change_1h=m.price_change_1h,
                spread=m.spread or 0,
                days_to_end=m.days_to_end,
                market_age_days=m.market_age_days,
                category=m.category,
                outcome_count=m.outcome_count,
            )
            scores[m.condition_id] = compute_interestingness(metrics)

        return await self.universe_repo.update_interestingness_scores(scores)
