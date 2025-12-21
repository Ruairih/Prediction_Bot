#!/usr/bin/env python3
"""
Populate the database with market data from Polymarket.

This script fetches:
- Active markets from the Gamma API
- Token metadata
- Recent trades

Usage:
    DATABASE_URL=... python scripts/populate_markets.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, "/workspace/src")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Populate database with market data."""
    from polymarket_bot.storage import Database, DatabaseConfig
    from polymarket_bot.ingestion import PolymarketRestClient

    # Get database URL
    database_url = os.environ.get("DATABASE_URL", "postgresql://predict:predict@postgres:5432/predict")

    logger.info("=" * 60)
    logger.info("POLYMARKET DATA POPULATION")
    logger.info("=" * 60)

    # Initialize database
    db_config = DatabaseConfig(url=database_url)
    db = Database(db_config)
    await db.initialize()
    logger.info("Database connected")

    # Initialize REST client
    async with PolymarketRestClient() as client:
        logger.info("REST client initialized")

        # Fetch active markets directly from API to get full data
        logger.info("Fetching active markets...")
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://gamma-api.polymarket.com/markets",
                params={"limit": 100, "active": "true"}
            ) as resp:
                raw_markets = await resp.json()
        logger.info(f"Fetched {len(raw_markets)} active markets")

        # Insert into stream_watchlist
        watchlist_count = 0
        token_meta_count = 0

        for market in raw_markets:
            try:
                # Insert market into stream_watchlist
                # Market uses condition_id as the primary identifier
                # Parse raw API format
                condition_id = market.get("conditionId", "")
                question = market.get("question", "")
                slug = market.get("slug", "")
                category = market.get("category", "")
                volume = float(market.get("volumeNum", 0) or 0)
                liquidity = float(market.get("liquidityNum", 0) or 0)
                end_date = market.get("endDateIso") or market.get("endDate")

                # Parse outcome prices
                outcome_prices_str = market.get("outcomePrices", "[]")
                try:
                    outcome_prices = json.loads(outcome_prices_str) if isinstance(outcome_prices_str, str) else outcome_prices_str
                except:
                    outcome_prices = [0, 0]

                best_bid = float(outcome_prices[0]) if outcome_prices else None
                best_ask = float(outcome_prices[1]) if len(outcome_prices) > 1 else None

                await db.execute("""
                    INSERT INTO stream_watchlist
                    (market_id, question, slug, category, best_bid, best_ask,
                     liquidity, volume, end_date, generated_at, condition_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (market_id) DO UPDATE SET
                        question = EXCLUDED.question,
                        best_bid = EXCLUDED.best_bid,
                        best_ask = EXCLUDED.best_ask,
                        liquidity = EXCLUDED.liquidity,
                        volume = EXCLUDED.volume,
                        generated_at = EXCLUDED.generated_at
                """,
                    condition_id,
                    question,
                    slug,
                    category,
                    best_bid,
                    best_ask,
                    liquidity,
                    volume,
                    end_date,
                    datetime.now(timezone.utc).isoformat(),
                    condition_id,
                )
                watchlist_count += 1

                # Parse token IDs and outcomes
                clob_token_ids_str = market.get("clobTokenIds", "[]")
                outcomes_str = market.get("outcomes", "[]")

                try:
                    token_ids = json.loads(clob_token_ids_str) if isinstance(clob_token_ids_str, str) else clob_token_ids_str
                    outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                except:
                    token_ids = []
                    outcomes = []

                # Insert token metadata for each token
                for idx, token_id in enumerate(token_ids):
                    outcome = outcomes[idx] if idx < len(outcomes) else "Unknown"
                    await db.execute("""
                        INSERT INTO polymarket_token_meta
                        (token_id, condition_id, market_id, outcome_index, outcome, question, fetched_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (token_id) DO UPDATE SET
                            question = EXCLUDED.question,
                            fetched_at = EXCLUDED.fetched_at
                    """,
                        token_id,
                        condition_id,
                        condition_id,
                        idx,
                        outcome,
                        question,
                        datetime.now(timezone.utc).isoformat(),
                    )
                    token_meta_count += 1

            except Exception as e:
                logger.warning(f"Error inserting market {market.condition_id}: {e}")
                continue

        logger.info(f"Inserted {watchlist_count} markets into stream_watchlist")
        logger.info(f"Inserted {token_meta_count} tokens into polymarket_token_meta")

        # Fetch some sample trades for high-volume markets
        logger.info("Fetching sample trades...")
        trades_count = 0

        for market in raw_markets[:20]:  # Just first 20 markets
            # Parse token IDs from raw market data
            clob_token_ids_str = market.get("clobTokenIds", "[]")
            outcomes_str = market.get("outcomes", "[]")
            try:
                token_ids = json.loads(clob_token_ids_str) if isinstance(clob_token_ids_str, str) else clob_token_ids_str
                outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
            except:
                continue

            condition_id = market.get("conditionId", "")

            for idx, token_id in enumerate(token_ids):
                outcome = outcomes[idx] if idx < len(outcomes) else "Unknown"
                outcome_index = idx
                try:
                    trades = await client.get_recent_trades(
                        token_id,
                        max_age_seconds=3600,  # Last hour
                        limit=50,
                    )

                    for trade in trades:
                        trade_id = trade.id
                        ts = trade.timestamp
                        if isinstance(ts, datetime):
                            ts_ms = int(ts.timestamp() * 1000)
                        else:
                            ts_ms = int(ts)

                        await db.execute("""
                            INSERT INTO polymarket_trades
                            (condition_id, trade_id, token_id, price, size, side,
                             timestamp, outcome, outcome_index)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (condition_id, trade_id) DO NOTHING
                        """,
                            condition_id,
                            trade_id,
                            token_id,
                            float(trade.price),
                            float(trade.size),
                            trade.side.value if hasattr(trade.side, 'value') else str(trade.side),
                            ts_ms,
                            outcome,
                            outcome_index,
                        )
                        trades_count += 1

                except Exception as e:
                    logger.debug(f"Error fetching trades for {token_id}: {e}")
                    continue

        logger.info(f"Inserted {trades_count} trades into polymarket_trades")

    # Close database
    await db.close()

    logger.info("=" * 60)
    logger.info("Data population complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
