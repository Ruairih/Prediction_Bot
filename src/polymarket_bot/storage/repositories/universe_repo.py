"""
Market Universe Repository for Tier 1 data.

Provides access to all markets in the system with filtering and scoring.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import (
    MarketUniverse,
    OutcomeToken,
    PriceSnapshot,
    StrategyTierRequest,
)
from polymarket_bot.storage.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


@dataclass
class MarketQuery:
    """Query parameters for market discovery."""

    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[float] = None
    max_volume: Optional[float] = None
    categories: Optional[list[str]] = None
    exclude_categories: Optional[list[str]] = None
    min_interestingness: Optional[float] = None
    max_days_to_end: Optional[float] = None
    min_days_to_end: Optional[float] = None
    min_market_age_days: Optional[float] = None
    max_market_age_days: Optional[float] = None
    tier: Optional[int] = None
    min_tier: Optional[int] = None
    include_resolved: bool = False
    binary_only: bool = False
    limit: int = 100
    offset: int = 0


class MarketUniverseRepository(BaseRepository[MarketUniverse]):
    """
    Repository for market_universe table (Tier 1).

    Provides:
    - Market discovery with flexible filtering
    - Tier management (promote/demote)
    - Interestingness scoring updates
    - Price snapshot history
    """

    table_name = "market_universe"
    model_class = MarketUniverse

    def _record_to_model(self, record) -> Optional[MarketUniverse]:
        """Convert asyncpg Record to MarketUniverse model."""
        if record is None:
            return None

        data = dict(record)

        # Parse outcomes JSONB
        outcomes_raw = data.pop("outcomes", [])
        if isinstance(outcomes_raw, str):
            outcomes_raw = json.loads(outcomes_raw)
        outcomes = [OutcomeToken(**o) for o in outcomes_raw] if outcomes_raw else []

        return MarketUniverse(outcomes=outcomes, **data)

    async def upsert(self, market: MarketUniverse) -> None:
        """Insert or update a market in the universe."""
        outcomes_json = json.dumps([o.model_dump() for o in market.outcomes])

        await self.db.execute(
            """
            INSERT INTO market_universe (
                condition_id, market_id, question, description, category,
                end_date, created_at, outcomes, outcome_count,
                price, best_bid, best_ask, spread,
                volume_24h, volume_total, liquidity, trade_count_24h,
                price_change_1h, price_change_24h,
                interestingness_score, tier, is_resolved,
                resolution_outcome, resolved_at, snapshot_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, NOW()
            )
            ON CONFLICT (condition_id) DO UPDATE SET
                market_id = COALESCE(EXCLUDED.market_id, market_universe.market_id),
                question = COALESCE(EXCLUDED.question, market_universe.question),
                description = COALESCE(EXCLUDED.description, market_universe.description),
                category = COALESCE(EXCLUDED.category, market_universe.category),
                end_date = COALESCE(EXCLUDED.end_date, market_universe.end_date),
                outcomes = COALESCE(EXCLUDED.outcomes, market_universe.outcomes),
                outcome_count = COALESCE(EXCLUDED.outcome_count, market_universe.outcome_count),
                price = EXCLUDED.price,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                spread = EXCLUDED.spread,
                volume_24h = EXCLUDED.volume_24h,
                volume_total = EXCLUDED.volume_total,
                liquidity = EXCLUDED.liquidity,
                trade_count_24h = EXCLUDED.trade_count_24h,
                price_change_1h = EXCLUDED.price_change_1h,
                price_change_24h = EXCLUDED.price_change_24h,
                interestingness_score = EXCLUDED.interestingness_score,
                is_resolved = EXCLUDED.is_resolved,
                resolution_outcome = EXCLUDED.resolution_outcome,
                resolved_at = EXCLUDED.resolved_at,
                snapshot_at = NOW()
            """,
            market.condition_id,
            market.market_id,
            market.question,
            market.description,
            market.category,
            market.end_date,
            market.created_at,
            outcomes_json,
            market.outcome_count,
            market.price,
            market.best_bid,
            market.best_ask,
            market.spread,
            market.volume_24h,
            market.volume_total,
            market.liquidity,
            market.trade_count_24h,
            market.price_change_1h,
            market.price_change_24h,
            market.interestingness_score,
            market.tier,
            market.is_resolved,
            market.resolution_outcome,
            market.resolved_at,
        )

    async def upsert_batch(self, markets: list[MarketUniverse]) -> int:
        """Batch upsert markets. Returns count of upserted rows."""
        if not markets:
            return 0

        # Build batch data
        values = []
        for m in markets:
            outcomes_json = json.dumps([o.model_dump() for o in m.outcomes])
            values.append((
                m.condition_id, m.market_id, m.question, m.description, m.category,
                m.end_date, m.created_at, outcomes_json, m.outcome_count,
                m.price, m.best_bid, m.best_ask, m.spread,
                m.volume_24h, m.volume_total, m.liquidity, m.trade_count_24h,
                m.price_change_1h, m.price_change_24h,
                m.interestingness_score, m.tier, m.is_resolved,
                m.resolution_outcome, m.resolved_at,
            ))

        # Use COPY or executemany for batch insert
        count = 0
        for v in values:
            await self.db.execute(
                """
                INSERT INTO market_universe (
                    condition_id, market_id, question, description, category,
                    end_date, created_at, outcomes, outcome_count,
                    price, best_bid, best_ask, spread,
                    volume_24h, volume_total, liquidity, trade_count_24h,
                    price_change_1h, price_change_24h,
                    interestingness_score, tier, is_resolved,
                    resolution_outcome, resolved_at, snapshot_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, NOW()
                )
                ON CONFLICT (condition_id) DO UPDATE SET
                    market_id = COALESCE(EXCLUDED.market_id, market_universe.market_id),
                    question = COALESCE(EXCLUDED.question, market_universe.question),
                    description = COALESCE(EXCLUDED.description, market_universe.description),
                    category = COALESCE(EXCLUDED.category, market_universe.category),
                    end_date = COALESCE(EXCLUDED.end_date, market_universe.end_date),
                    outcomes = COALESCE(EXCLUDED.outcomes, market_universe.outcomes),
                    outcome_count = COALESCE(EXCLUDED.outcome_count, market_universe.outcome_count),
                    price = EXCLUDED.price,
                    best_bid = EXCLUDED.best_bid,
                    best_ask = EXCLUDED.best_ask,
                    spread = EXCLUDED.spread,
                    volume_24h = EXCLUDED.volume_24h,
                    volume_total = EXCLUDED.volume_total,
                    liquidity = EXCLUDED.liquidity,
                    trade_count_24h = EXCLUDED.trade_count_24h,
                    price_change_1h = EXCLUDED.price_change_1h,
                    price_change_24h = EXCLUDED.price_change_24h,
                    interestingness_score = EXCLUDED.interestingness_score,
                    is_resolved = EXCLUDED.is_resolved,
                    resolution_outcome = EXCLUDED.resolution_outcome,
                    resolved_at = EXCLUDED.resolved_at,
                    snapshot_at = NOW()
                """,
                *v,
            )
            count += 1

        return count

    async def query(self, q: MarketQuery) -> list[MarketUniverse]:
        """Query markets with flexible filters."""
        conditions = []
        params = []
        param_idx = 1

        # Price filters
        if q.min_price is not None:
            conditions.append(f"price >= ${param_idx}")
            params.append(q.min_price)
            param_idx += 1
        if q.max_price is not None:
            conditions.append(f"price <= ${param_idx}")
            params.append(q.max_price)
            param_idx += 1

        # Volume filters
        if q.min_volume is not None:
            conditions.append(f"volume_24h >= ${param_idx}")
            params.append(q.min_volume)
            param_idx += 1
        if q.max_volume is not None:
            conditions.append(f"volume_24h <= ${param_idx}")
            params.append(q.max_volume)
            param_idx += 1

        # Category filters
        if q.categories:
            conditions.append(f"category = ANY(${param_idx})")
            params.append(q.categories)
            param_idx += 1
        if q.exclude_categories:
            conditions.append(f"category != ALL(${param_idx})")
            params.append(q.exclude_categories)
            param_idx += 1

        # Interestingness filter
        if q.min_interestingness is not None:
            conditions.append(f"interestingness_score >= ${param_idx}")
            params.append(q.min_interestingness)
            param_idx += 1

        # Time filters (using parameterized intervals)
        if q.max_days_to_end is not None:
            conditions.append(f"end_date <= NOW() + make_interval(days => ${param_idx})")
            params.append(int(q.max_days_to_end))
            param_idx += 1
        if q.min_days_to_end is not None:
            conditions.append(f"end_date >= NOW() + make_interval(days => ${param_idx})")
            params.append(int(q.min_days_to_end))
            param_idx += 1
        if q.min_market_age_days is not None:
            conditions.append(f"created_at <= NOW() - make_interval(days => ${param_idx})")
            params.append(int(q.min_market_age_days))
            param_idx += 1
        if q.max_market_age_days is not None:
            conditions.append(f"created_at >= NOW() - make_interval(days => ${param_idx})")
            params.append(int(q.max_market_age_days))
            param_idx += 1

        # Tier filters
        if q.tier is not None:
            conditions.append(f"tier = ${param_idx}")
            params.append(q.tier)
            param_idx += 1
        if q.min_tier is not None:
            conditions.append(f"tier >= ${param_idx}")
            params.append(q.min_tier)
            param_idx += 1

        # Resolution filter
        if not q.include_resolved:
            conditions.append("is_resolved = FALSE")

        # Binary-only filter
        if q.binary_only:
            conditions.append("outcome_count = 2")

        # Build query
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        query = f"""
            SELECT * FROM market_universe
            WHERE {where_clause}
            ORDER BY interestingness_score DESC, volume_24h DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([q.limit, q.offset])

        records = await self.db.fetch(query, *params)
        return self._records_to_models(records)

    async def get_by_condition_id(self, condition_id: str) -> Optional[MarketUniverse]:
        """Get a market by condition_id."""
        return await self.get_by_id(condition_id, id_column="condition_id")

    async def get_by_tier(self, tier: int, limit: int = 1000) -> list[MarketUniverse]:
        """Get all markets at a specific tier."""
        records = await self.db.fetch(
            """
            SELECT * FROM market_universe
            WHERE tier = $1 AND is_resolved = FALSE
            ORDER BY interestingness_score DESC
            LIMIT $2
            """,
            tier,
            limit,
        )
        return self._records_to_models(records)

    async def get_tier_counts(self) -> dict[int, int]:
        """Get count of markets per tier."""
        records = await self.db.fetch(
            """
            SELECT tier, COUNT(*) as count
            FROM market_universe
            WHERE is_resolved = FALSE
            GROUP BY tier
            """
        )
        return {r["tier"]: r["count"] for r in records}

    async def get_top_by_score(self, limit: int = 100) -> list[MarketUniverse]:
        """Get markets with highest interestingness scores."""
        records = await self.db.fetch(
            """
            SELECT * FROM market_universe
            WHERE is_resolved = FALSE
            ORDER BY interestingness_score DESC
            LIMIT $1
            """,
            limit,
        )
        return self._records_to_models(records)

    async def promote(
        self,
        condition_id: str,
        target_tier: int,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Promote a market to a higher tier.

        Returns True if promotion occurred.
        """
        result = await self.db.execute(
            """
            UPDATE market_universe
            SET tier = $2, tier_changed_at = NOW()
            WHERE condition_id = $1 AND tier < $2
            """,
            condition_id,
            target_tier,
        )
        if result != "UPDATE 0":
            logger.info(f"Promoted {condition_id} to tier {target_tier}: {reason}")
            return True
        return False

    async def demote(
        self,
        condition_id: str,
        target_tier: int,
    ) -> bool:
        """
        Demote a market to a lower tier.

        Respects pinned_tier - won't demote below it.
        """
        result = await self.db.execute(
            """
            UPDATE market_universe
            SET tier = $2, tier_changed_at = NOW()
            WHERE condition_id = $1
              AND tier > $2
              AND (pinned_tier IS NULL OR pinned_tier <= $2)
            """,
            condition_id,
            target_tier,
        )
        if result != "UPDATE 0":
            logger.info(f"Demoted {condition_id} to tier {target_tier}")
            return True
        return False

    async def set_pinned_tier(self, condition_id: str, pinned_tier: Optional[int]) -> None:
        """Set or clear the pinned tier for a market."""
        await self.db.execute(
            """
            UPDATE market_universe
            SET pinned_tier = $2
            WHERE condition_id = $1
            """,
            condition_id,
            pinned_tier,
        )

    async def update_interestingness_scores(self, scores: dict[str, float]) -> int:
        """Batch update interestingness scores."""
        count = 0
        for condition_id, score in scores.items():
            result = await self.db.execute(
                """
                UPDATE market_universe
                SET interestingness_score = $2,
                    score_below_threshold_since = CASE
                        WHEN $2 < 20 AND score_below_threshold_since IS NULL THEN NOW()
                        WHEN $2 >= 20 THEN NULL
                        ELSE score_below_threshold_since
                    END
                WHERE condition_id = $1
                """,
                condition_id,
                score,
            )
            if result != "UPDATE 0":
                count += 1
        return count

    async def record_strategy_signal(self, condition_id: str) -> None:
        """Record that a strategy emitted a signal for this market."""
        await self.db.execute(
            """
            UPDATE market_universe
            SET last_strategy_signal_at = NOW()
            WHERE condition_id = $1
            """,
            condition_id,
        )

    # =========================================================================
    # Price Snapshots
    # =========================================================================

    async def save_price_snapshot(self, snapshot: PriceSnapshot) -> None:
        """Save a price snapshot for change calculation."""
        await self.db.execute(
            """
            INSERT INTO price_snapshots (condition_id, snapshot_at, price, volume_24h)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (condition_id, snapshot_at) DO NOTHING
            """,
            snapshot.condition_id,
            snapshot.snapshot_at,
            snapshot.price,
            snapshot.volume_24h,
        )

    async def get_price_at_time(
        self, condition_id: str, target_time: datetime
    ) -> Optional[float]:
        """Get the price closest to a target time."""
        record = await self.db.fetchrow(
            """
            SELECT price FROM price_snapshots
            WHERE condition_id = $1 AND snapshot_at <= $2
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            condition_id,
            target_time,
        )
        return record["price"] if record else None

    async def compute_price_changes(self, condition_ids: list[str]) -> dict[str, tuple[float, float]]:
        """
        Compute 1h and 24h price changes for markets.

        Returns dict of condition_id -> (change_1h, change_24h)
        """
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)

        changes = {}
        for condition_id in condition_ids:
            current = await self.db.fetchval(
                "SELECT price FROM market_universe WHERE condition_id = $1",
                condition_id,
            )
            if current is None:
                continue

            price_1h = await self.get_price_at_time(condition_id, hour_ago)
            price_24h = await self.get_price_at_time(condition_id, day_ago)

            # Use 'is None' check, not truthiness (0.0 is a valid price)
            change_1h = (current - price_1h) if price_1h is not None else 0
            change_24h = (current - price_24h) if price_24h is not None else 0

            changes[condition_id] = (change_1h, change_24h)

        return changes

    # =========================================================================
    # Strategy Tier Requests
    # =========================================================================

    async def create_tier_request(self, request: StrategyTierRequest) -> None:
        """Create or update a strategy tier request."""
        await self.db.execute(
            """
            INSERT INTO strategy_tier_requests (
                strategy_name, condition_id, requested_tier, reason, requested_at, expires_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (strategy_name, condition_id) DO UPDATE SET
                requested_tier = GREATEST(strategy_tier_requests.requested_tier, $3),
                reason = $4,
                requested_at = $5,
                expires_at = $6
            """,
            request.strategy_name,
            request.condition_id,
            request.requested_tier,
            request.reason,
            request.requested_at,
            request.expires_at,
        )

    async def get_active_tier_requests(self, min_tier: int = 2) -> list[StrategyTierRequest]:
        """Get all non-expired tier requests at or above min_tier."""
        records = await self.db.fetch(
            """
            SELECT * FROM strategy_tier_requests
            WHERE requested_tier >= $1 AND expires_at > NOW()
            ORDER BY requested_tier DESC, requested_at DESC
            """,
            min_tier,
        )
        return [StrategyTierRequest(**dict(r)) for r in records]

    async def cleanup_expired_requests(self) -> int:
        """Delete expired tier requests."""
        result = await self.db.execute(
            "DELETE FROM strategy_tier_requests WHERE expires_at < NOW()"
        )
        # Parse "DELETE N" result
        return int(result.split()[-1]) if result else 0
