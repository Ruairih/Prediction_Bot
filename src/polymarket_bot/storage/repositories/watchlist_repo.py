"""
Watchlist and scoring repositories.

Handles:
- trade_watchlist: Tokens being watched for trading
- market_scores_cache: Cached model scores
- score_history: Historical score tracking
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import (
    MarketScoresCache,
    ScoreHistory,
    TradeWatchlistItem,
)
from polymarket_bot.storage.repositories.base import BaseRepository


class TradeWatchlistRepository(BaseRepository[TradeWatchlistItem]):
    """Repository for trade watchlist."""

    table_name = "trade_watchlist"
    model_class = TradeWatchlistItem

    async def create(self, item: TradeWatchlistItem) -> TradeWatchlistItem:
        """Add item to watchlist."""
        query = """
            INSERT INTO trade_watchlist
            (token_id, market_id, condition_id, question, trigger_price, trigger_size,
             trigger_timestamp, initial_score, current_score, time_to_end_hours,
             last_scored_at, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (token_id) DO UPDATE
            SET market_id = $2,
                condition_id = $3,
                question = $4,
                trigger_price = $5,
                trigger_size = $6,
                trigger_timestamp = $7,
                current_score = $9,
                time_to_end_hours = $10,
                last_scored_at = $11,
                status = $12,
                updated_at = $14
            RETURNING *
        """
        now = int(datetime.utcnow().timestamp())
        record = await self.db.fetchrow(
            query,
            item.token_id,
            item.market_id,
            item.condition_id,
            item.question,
            item.trigger_price,
            item.trigger_size,
            item.trigger_timestamp,
            item.initial_score,
            item.current_score,
            item.time_to_end_hours,
            item.last_scored_at,
            item.status,
            item.created_at or now,
            now,
        )
        return self._record_to_model(record)

    async def get_watching(self) -> list[TradeWatchlistItem]:
        """Get items currently being watched."""
        query = """
            SELECT * FROM trade_watchlist
            WHERE status = 'watching'
            ORDER BY current_score DESC
        """
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_by_status(self, status: str) -> list[TradeWatchlistItem]:
        """Get items by status."""
        query = """
            SELECT * FROM trade_watchlist
            WHERE status = $1
            ORDER BY updated_at DESC
        """
        records = await self.db.fetch(query, status)
        return self._records_to_models(records)

    async def update_score(
        self, token_id: str, score: float, time_to_end_hours: float
    ) -> Optional[TradeWatchlistItem]:
        """Update score for a watched item."""
        now = int(datetime.utcnow().timestamp())
        query = """
            UPDATE trade_watchlist
            SET current_score = $2,
                time_to_end_hours = $3,
                last_scored_at = $4,
                updated_at = $4
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id, score, time_to_end_hours, now)
        return self._record_to_model(record)

    async def promote(self, token_id: str) -> Optional[TradeWatchlistItem]:
        """Promote item from watching to promoted (ready to trade)."""
        now = int(datetime.utcnow().timestamp())
        query = """
            UPDATE trade_watchlist
            SET status = 'promoted', updated_at = $2
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id, now)
        return self._record_to_model(record)

    async def mark_traded(self, token_id: str) -> Optional[TradeWatchlistItem]:
        """Mark item as traded."""
        now = int(datetime.utcnow().timestamp())
        query = """
            UPDATE trade_watchlist
            SET status = 'traded', updated_at = $2
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id, now)
        return self._record_to_model(record)

    async def mark_expired(self, token_id: str) -> Optional[TradeWatchlistItem]:
        """Mark item as expired."""
        now = int(datetime.utcnow().timestamp())
        query = """
            UPDATE trade_watchlist
            SET status = 'expired', updated_at = $2
            WHERE token_id = $1
            RETURNING *
        """
        record = await self.db.fetchrow(query, token_id, now)
        return self._record_to_model(record)


class MarketScoresCacheRepository(BaseRepository[MarketScoresCache]):
    """Repository for cached market scores."""

    table_name = "market_scores_cache"
    model_class = MarketScoresCache

    async def upsert(self, cache: MarketScoresCache) -> MarketScoresCache:
        """Insert or update cached scores."""
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO market_scores_cache
            (condition_id, market_id, question, category, best_bid, best_ask,
             spread_pct, liquidity, volume, end_date, time_to_end_hours,
             model_score, passes_filters, filter_rejections,
             is_weather, is_crypto, is_politics, is_sports, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            ON CONFLICT (condition_id) DO UPDATE
            SET market_id = $2,
                question = $3,
                category = $4,
                best_bid = $5,
                best_ask = $6,
                spread_pct = $7,
                liquidity = $8,
                volume = $9,
                end_date = $10,
                time_to_end_hours = $11,
                model_score = $12,
                passes_filters = $13,
                filter_rejections = $14,
                is_weather = $15,
                is_crypto = $16,
                is_politics = $17,
                is_sports = $18,
                updated_at = $19
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            cache.condition_id,
            cache.market_id,
            cache.question,
            cache.category,
            cache.best_bid,
            cache.best_ask,
            cache.spread_pct,
            cache.liquidity,
            cache.volume,
            cache.end_date,
            cache.time_to_end_hours,
            cache.model_score,
            cache.passes_filters,
            cache.filter_rejections,
            cache.is_weather,
            cache.is_crypto,
            cache.is_politics,
            cache.is_sports,
            now,
        )
        return self._record_to_model(record)

    async def get_by_condition(self, condition_id: str) -> Optional[MarketScoresCache]:
        """Get cached score for a condition."""
        query = "SELECT * FROM market_scores_cache WHERE condition_id = $1"
        record = await self.db.fetchrow(query, condition_id)
        return self._record_to_model(record)

    async def get_passing(self, limit: int = 100) -> list[MarketScoresCache]:
        """Get markets that pass filters."""
        query = """
            SELECT * FROM market_scores_cache
            WHERE passes_filters = 1
            ORDER BY model_score DESC
            LIMIT $1
        """
        records = await self.db.fetch(query, limit)
        return self._records_to_models(records)

    async def get_by_category_flags(
        self,
        is_weather: Optional[bool] = None,
        is_crypto: Optional[bool] = None,
        is_politics: Optional[bool] = None,
        is_sports: Optional[bool] = None,
    ) -> list[MarketScoresCache]:
        """Get markets by category flags."""
        conditions = []
        params = []
        param_idx = 1

        if is_weather is not None:
            conditions.append(f"is_weather = ${param_idx}")
            params.append(1 if is_weather else 0)
            param_idx += 1
        if is_crypto is not None:
            conditions.append(f"is_crypto = ${param_idx}")
            params.append(1 if is_crypto else 0)
            param_idx += 1
        if is_politics is not None:
            conditions.append(f"is_politics = ${param_idx}")
            params.append(1 if is_politics else 0)
            param_idx += 1
        if is_sports is not None:
            conditions.append(f"is_sports = ${param_idx}")
            params.append(1 if is_sports else 0)
            param_idx += 1

        if not conditions:
            return await self.get_passing()

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT * FROM market_scores_cache
            WHERE {where_clause}
            ORDER BY model_score DESC
        """
        records = await self.db.fetch(query, *params)
        return self._records_to_models(records)


class ScoreHistoryRepository(BaseRepository[ScoreHistory]):
    """Repository for score history."""

    table_name = "score_history"
    model_class = ScoreHistory

    async def create(self, history: ScoreHistory) -> ScoreHistory:
        """Add a score history entry."""
        query = """
            INSERT INTO score_history
            (token_id, score, time_to_end_hours, scored_at)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            history.token_id,
            history.score,
            history.time_to_end_hours,
            history.scored_at,
        )
        return self._record_to_model(record)

    async def get_by_token(
        self, token_id: str, limit: int = 100
    ) -> list[ScoreHistory]:
        """Get score history for a token."""
        query = """
            SELECT * FROM score_history
            WHERE token_id = $1
            ORDER BY scored_at DESC
            LIMIT $2
        """
        records = await self.db.fetch(query, token_id, limit)
        return self._records_to_models(records)

    async def get_recent(self, since_timestamp: int) -> list[ScoreHistory]:
        """Get recent score history entries."""
        query = """
            SELECT * FROM score_history
            WHERE scored_at >= $1
            ORDER BY scored_at DESC
        """
        records = await self.db.fetch(query, since_timestamp)
        return self._records_to_models(records)

    async def cleanup_old(self, days: int = 30) -> int:
        """Delete old score history. Returns count deleted."""
        cutoff = int(datetime.utcnow().timestamp()) - (days * 86400)
        result = await self.db.execute(
            "DELETE FROM score_history WHERE scored_at < $1", cutoff
        )
        return int(result.split()[-1]) if result else 0
