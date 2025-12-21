"""
Market repository for market data and metadata.

Handles:
- stream_watchlist: Markets from streaming watchlist
- polymarket_resolutions: Market resolution data
- polymarket_token_meta: Token metadata cache
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from polymarket_bot.storage.database import Database
from polymarket_bot.storage.models import (
    PolymarketResolution,
    PolymarketTokenMeta,
    StreamWatchlistItem,
)
from polymarket_bot.storage.repositories.base import BaseRepository


class StreamWatchlistRepository(BaseRepository[StreamWatchlistItem]):
    """Repository for streaming watchlist markets."""

    table_name = "stream_watchlist"
    model_class = StreamWatchlistItem

    async def upsert(self, item: StreamWatchlistItem) -> StreamWatchlistItem:
        """Insert or update a watchlist item."""
        query = """
            INSERT INTO stream_watchlist
            (market_id, question, slug, category, best_bid, best_ask,
             liquidity, volume, end_date, generated_at, condition_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (market_id) DO UPDATE
            SET question = $2,
                slug = $3,
                category = $4,
                best_bid = $5,
                best_ask = $6,
                liquidity = $7,
                volume = $8,
                end_date = $9,
                generated_at = $10,
                condition_id = $11
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            item.market_id,
            item.question,
            item.slug,
            item.category,
            item.best_bid,
            item.best_ask,
            item.liquidity,
            item.volume,
            item.end_date,
            item.generated_at,
            item.condition_id,
        )
        return self._record_to_model(record)

    async def get_all(self) -> list[StreamWatchlistItem]:
        """Get all watchlist items."""
        query = "SELECT * FROM stream_watchlist ORDER BY generated_at DESC"
        records = await self.db.fetch(query)
        return self._records_to_models(records)

    async def get_by_category(self, category: str) -> list[StreamWatchlistItem]:
        """Get watchlist items by category."""
        query = """
            SELECT * FROM stream_watchlist
            WHERE category = $1
            ORDER BY volume DESC
        """
        records = await self.db.fetch(query, category)
        return self._records_to_models(records)

    async def clear(self) -> int:
        """Clear all watchlist items. Returns count deleted."""
        result = await self.db.execute("DELETE FROM stream_watchlist")
        return int(result.split()[-1]) if result else 0


class ResolutionRepository(BaseRepository[PolymarketResolution]):
    """Repository for market resolutions."""

    table_name = "polymarket_resolutions"
    model_class = PolymarketResolution

    async def upsert(self, resolution: PolymarketResolution) -> PolymarketResolution:
        """Insert or update a resolution."""
        query = """
            INSERT INTO polymarket_resolutions
            (condition_id, winning_outcome_index, winning_outcome, resolved_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (condition_id) DO UPDATE
            SET winning_outcome_index = $2,
                winning_outcome = $3,
                resolved_at = $4
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            resolution.condition_id,
            resolution.winning_outcome_index,
            resolution.winning_outcome,
            resolution.resolved_at,
        )
        return self._record_to_model(record)

    async def get_by_condition(self, condition_id: str) -> Optional[PolymarketResolution]:
        """Get resolution for a condition."""
        query = "SELECT * FROM polymarket_resolutions WHERE condition_id = $1"
        record = await self.db.fetchrow(query, condition_id)
        return self._record_to_model(record)

    async def is_resolved(self, condition_id: str) -> bool:
        """Check if a market is resolved."""
        query = "SELECT 1 FROM polymarket_resolutions WHERE condition_id = $1"
        result = await self.db.fetchval(query, condition_id)
        return result is not None

    async def get_recent(self, limit: int = 100) -> list[PolymarketResolution]:
        """Get recently resolved markets."""
        query = """
            SELECT * FROM polymarket_resolutions
            WHERE resolved_at IS NOT NULL
            ORDER BY resolved_at DESC
            LIMIT $1
        """
        records = await self.db.fetch(query, limit)
        return self._records_to_models(records)


class TokenMetaRepository(BaseRepository[PolymarketTokenMeta]):
    """Repository for token metadata cache."""

    table_name = "polymarket_token_meta"
    model_class = PolymarketTokenMeta

    async def upsert(self, meta: PolymarketTokenMeta) -> PolymarketTokenMeta:
        """Insert or update token metadata."""
        query = """
            INSERT INTO polymarket_token_meta
            (token_id, condition_id, market_id, outcome_index, outcome, question, fetched_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (token_id) DO UPDATE
            SET condition_id = $2,
                market_id = $3,
                outcome_index = $4,
                outcome = $5,
                question = $6,
                fetched_at = $7
            RETURNING *
        """
        record = await self.db.fetchrow(
            query,
            meta.token_id,
            meta.condition_id,
            meta.market_id,
            meta.outcome_index,
            meta.outcome,
            meta.question,
            meta.fetched_at,
        )
        return self._record_to_model(record)

    async def get_by_token(self, token_id: str) -> Optional[PolymarketTokenMeta]:
        """Get metadata for a token."""
        query = "SELECT * FROM polymarket_token_meta WHERE token_id = $1"
        record = await self.db.fetchrow(query, token_id)
        return self._record_to_model(record)

    async def get_by_condition(self, condition_id: str) -> list[PolymarketTokenMeta]:
        """Get all tokens for a condition."""
        query = """
            SELECT * FROM polymarket_token_meta
            WHERE condition_id = $1
            ORDER BY outcome_index
        """
        records = await self.db.fetch(query, condition_id)
        return self._records_to_models(records)

    async def get_condition_id(self, token_id: str) -> Optional[str]:
        """Get condition_id for a token (common lookup)."""
        query = "SELECT condition_id FROM polymarket_token_meta WHERE token_id = $1"
        return await self.db.fetchval(query, token_id)
