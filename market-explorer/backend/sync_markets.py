#!/usr/bin/env python3
"""
Sync markets from Polymarket Gamma API to explorer_markets table.

Usage:
    python sync_markets.py
"""

import asyncio
import os
import httpx
import asyncpg
from datetime import datetime, timezone
from dateutil import parser as dateparser

GAMMA_API = "https://gamma-api.polymarket.com"
DATABASE_URL = os.environ.get(
    "EXPLORER_DATABASE_URL",
    "postgresql://predict:predict@postgres:5432/predict"
)


def parse_date(date_str):
    """Parse date string to datetime, returning None on failure."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None


async def fetch_markets(client: httpx.AsyncClient, offset: int = 0, limit: int = 100):
    """Fetch markets from Gamma API."""
    url = f"{GAMMA_API}/markets"
    params = {
        "limit": limit,
        "offset": offset,
        "active": "true",
    }
    resp = await client.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def sync_markets():
    """Main sync function."""
    print("Connecting to database...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)

    print("Fetching markets from Polymarket...")
    async with httpx.AsyncClient() as client:
        all_markets = []
        offset = 0
        batch_size = 100

        while True:
            markets = await fetch_markets(client, offset=offset, limit=batch_size)
            if not markets:
                break
            all_markets.extend(markets)
            print(f"  Fetched {len(all_markets)} markets...")
            offset += batch_size

            # Limit for initial sync
            if len(all_markets) >= 5000:
                break

        print(f"Total markets fetched: {len(all_markets)}")

    print("Inserting into explorer_markets...")
    inserted = 0
    updated = 0

    async with pool.acquire() as conn:
        for market in all_markets:
            condition_id = market.get("conditionId") or market.get("condition_id")
            if not condition_id:
                continue

            # Parse data
            question = market.get("question", "")
            category = market.get("groupItemTitle") or market.get("category") or "Other"
            end_time_str = market.get("endDate") or market.get("end_date_iso")
            end_time = parse_date(end_time_str)
            resolved = market.get("closed", False) or market.get("resolved", False)

            # Price data
            yes_price = None
            best_bid = None
            best_ask = None

            if "outcomePrices" in market:
                try:
                    prices = market["outcomePrices"]
                    if isinstance(prices, str):
                        import json
                        prices = json.loads(prices)
                    if prices and len(prices) > 0:
                        yes_price = float(prices[0]) if prices[0] else None
                except:
                    pass

            if "bestBid" in market:
                try:
                    best_bid = float(market["bestBid"]) if market["bestBid"] else None
                except:
                    pass

            if "bestAsk" in market:
                try:
                    best_ask = float(market["bestAsk"]) if market["bestAsk"] else None
                except:
                    pass

            # Volume
            volume_24h = None
            if "volume24hr" in market:
                try:
                    volume_24h = float(market["volume24hr"]) if market["volume24hr"] else None
                except:
                    pass
            elif "volume" in market:
                try:
                    volume_24h = float(market["volume"]) if market["volume"] else None
                except:
                    pass

            # Liquidity
            liquidity = None
            if "liquidityNum" in market:
                try:
                    liquidity = float(market["liquidityNum"]) if market["liquidityNum"] else None
                except:
                    pass
            elif "liquidity" in market:
                try:
                    liquidity = float(market["liquidity"]) if market["liquidity"] else None
                except:
                    pass

            # Status
            status = "resolved" if resolved else "active"

            # Upsert
            try:
                result = await conn.execute("""
                    INSERT INTO explorer_markets (
                        condition_id, market_id, question, category, end_time,
                        resolved, status, yes_price, best_bid, best_ask,
                        volume_24h, liquidity_score, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (condition_id) DO UPDATE SET
                        question = EXCLUDED.question,
                        category = EXCLUDED.category,
                        end_time = EXCLUDED.end_time,
                        resolved = EXCLUDED.resolved,
                        status = EXCLUDED.status,
                        yes_price = EXCLUDED.yes_price,
                        best_bid = EXCLUDED.best_bid,
                        best_ask = EXCLUDED.best_ask,
                        volume_24h = EXCLUDED.volume_24h,
                        liquidity_score = EXCLUDED.liquidity_score,
                        updated_at = EXCLUDED.updated_at
                """,
                    condition_id,
                    market.get("id") or market.get("market_id"),
                    question,
                    category,
                    end_time,
                    resolved,
                    status,
                    yes_price,
                    best_bid,
                    best_ask,
                    volume_24h,
                    liquidity,
                    datetime.now(timezone.utc),
                )
                if "INSERT" in result:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                print(f"  Error inserting {condition_id}: {e}")

    await pool.close()
    print(f"Done! Inserted: {inserted}, Updated: {updated}")


if __name__ == "__main__":
    asyncio.run(sync_markets())
