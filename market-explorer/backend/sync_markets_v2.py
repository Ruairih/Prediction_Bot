#!/usr/bin/env python3
"""
Enhanced market sync from Polymarket Gamma API.
Captures ALL useful fields for a proper market explorer.

Usage:
    python sync_markets_v2.py [--active-only] [--limit N]
"""

import asyncio
import os
import sys
import httpx
import asyncpg
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from dateutil import parser as dateparser

GAMMA_API = "https://gamma-api.polymarket.com"
DATABASE_URL = os.environ.get(
    "EXPLORER_DATABASE_URL",
    "postgresql://predict:predict@postgres:5432/predict"
)


def parse_date(date_str):
    """Parse date string to datetime."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None


def safe_float(val, default=None):
    """Safely convert to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_decimal(val, max_val=9999.99):
    """Safely convert to Decimal, capping to avoid overflow."""
    if val is None:
        return None
    try:
        f = float(val)
        if f > max_val:
            f = max_val
        if f < -max_val:
            f = -max_val
        return Decimal(str(round(f, 2)))
    except (ValueError, TypeError, InvalidOperation):
        return None


def parse_outcome_prices(market):
    """Extract YES and NO prices from outcome prices.

    Returns tuple of (yes_price, no_price).
    For binary markets, index 0 is typically YES and index 1 is NO.
    """
    try:
        prices = market.get("outcomePrices")
        if not prices:
            return None, None
        if isinstance(prices, str):
            prices = json.loads(prices)
        if prices and len(prices) >= 2:
            return safe_float(prices[0]), safe_float(prices[1])
        elif prices and len(prices) == 1:
            yes_price = safe_float(prices[0])
            # For single outcome, NO price is complement
            no_price = 1.0 - yes_price if yes_price is not None else None
            return yes_price, no_price
    except:
        pass
    return None, None


def get_best_bid_ask(market):
    """Extract best bid/ask from market."""
    best_bid = safe_float(market.get("bestBid"))
    best_ask = safe_float(market.get("bestAsk"))
    return best_bid, best_ask


def normalize_category(market):
    """Normalize category from various fields.

    This function consolidates granular categories into broader parent categories
    for better filtering UX. For example, "Donald Trump", "Joe Biden", "Democratic Party"
    all get mapped to "Politics".
    """
    import re

    question = market.get("question", "")

    # Get raw category from API
    raw_cat = market.get("groupItemTitle") or market.get("category") or ""

    # Try to infer from tags if no category
    if not raw_cat or raw_cat == "Other":
        tags = market.get("tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                tags = []
        if tags:
            raw_cat = tags[0].get("label", "") if isinstance(tags[0], dict) else str(tags[0])

    # Normalize to parent categories
    # Check if raw category or question indicates Politics
    politics_categories = [
        "trump", "biden", "harris", "obama", "clinton", "pence", "vance",
        "newsom", "desantis", "haley", "ramaswamy", "vivek",
        "democrat", "republican", "gop", "dnc", "rnc",
        "democratic party", "republican party",
        "us-current-affairs", "us current affairs",
        "election", "presidential", "governor", "senate", "congress",
        "politics", "political",
        "walz", "shapiro", "whitmer", "pritzker", "buttigieg",
        "aoc", "pelosi", "mccarthy", "schumer", "mcconnell",
    ]

    raw_cat_lower = raw_cat.lower()
    question_lower = question.lower()

    # Check if category name suggests politics
    for pol_term in politics_categories:
        if pol_term in raw_cat_lower:
            return "Politics"

    # Check question for political context
    if re.search(r'\b(Trump|Biden|Harris|election|Congress|Senate|House|governor|president|presidential|Republican|Democrat|GOP|vote|ballot|nominee|nomination|primary|caucus|electoral|White House|Capitol|impeach|pardon|veto|administration)\b', question, re.IGNORECASE):
        return "Politics"

    # Sports detection - check both category and question
    sports_categories = ["nba", "nfl", "mlb", "nhl", "mls", "ufc", "mma", "atp", "wta",
                        "premier league", "champions league", "la liga", "bundesliga",
                        "playoffs", "championship", "super bowl", "world series", "stanley cup"]

    for sport_term in sports_categories:
        if sport_term in raw_cat_lower:
            return "Sports"

    sports_teams = r'\b(vs\.|versus|Lakers|Celtics|Warriors|Bulls|Heat|Knicks|Nets|76ers|Clippers|Mavericks|Suns|Bucks|Nuggets|Grizzlies|Pelicans|Hawks|Cavaliers|Raptors|Pacers|Hornets|Magic|Pistons|Wizards|Kings|Spurs|Rockets|Thunder|Timberwolves|Trail Blazers|Jazz|Chiefs|Eagles|Cowboys|Bills|49ers|Dolphins|Lions|Ravens|Bengals|Commanders|Jets|Patriots|Steelers|Chargers|Broncos|Raiders|Browns|Colts|Texans|Jaguars|Titans|Packers|Vikings|Bears|Saints|Falcons|Panthers|Buccaneers|Cardinals|Seahawks|Rams|Giants|Yankees|Dodgers|Mets|Red Sox|Cubs|Braves|Phillies|Astros|Padres|Guardians|Mariners|Rangers|Orioles|Rays|Blue Jays|Twins|White Sox|Brewers|Cardinals|Reds|Pirates|Marlins|Nationals|Rockies|Diamondbacks|Giants|Athletics|Angels|Tigers|Royals|Maple Leafs|Bruins|Rangers|Hurricanes|Panthers|Lightning|Senators|Canadiens|Sabres|Red Wings|Penguins|Flyers|Capitals|Devils|Islanders|Blue Jackets|Jets|Wild|Avalanche|Stars|Predators|Blues|Blackhawks|Kraken|Flames|Oilers|Canucks|Golden Knights|Coyotes|Ducks|Kings|Sharks|NHL|NFL|NBA|MLB|Premier League|Champions League|UFC|MMA|ATP|WTA|O/U \d)\b'
    if re.search(sports_teams, question, re.IGNORECASE):
        return "Sports"

    # Crypto detection
    crypto_terms = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol",
                    "xrp", "dogecoin", "doge", "altcoin", "defi", "nft", "blockchain"]
    for crypto_term in crypto_terms:
        if crypto_term in raw_cat_lower or crypto_term in question_lower:
            return "Crypto"

    # If we have a specific category that's not "Other", keep it
    if raw_cat and raw_cat not in ["Other", ""]:
        return raw_cat

    return "Other"


async def fetch_all_markets(client: httpx.AsyncClient, active_only: bool = False, limit: int = None):
    """Fetch all markets from Gamma API with full data."""
    all_markets = []
    offset = 0
    batch_size = 100

    while True:
        params = {
            "limit": batch_size,
            "offset": offset,
        }
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"

        try:
            resp = await client.get(f"{GAMMA_API}/markets", params=params, timeout=30.0)
            resp.raise_for_status()
            markets = resp.json()
        except Exception as e:
            print(f"Error fetching at offset {offset}: {e}")
            break

        if not markets:
            break

        all_markets.extend(markets)
        print(f"  Fetched {len(all_markets)} markets...")
        offset += batch_size

        if limit and len(all_markets) >= limit:
            all_markets = all_markets[:limit]
            break

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)

    return all_markets


async def ensure_schema(conn):
    """Ensure explorer_markets has all required columns."""
    # Add missing columns if they don't exist
    columns_to_add = [
        ("volume", "DECIMAL(18,2)"),
        ("volume_num", "DECIMAL(18,2)"),
        ("volume_7d", "DECIMAL(18,2)"),
        ("liquidity", "DECIMAL(18,2)"),
        ("liquidity_num", "DECIMAL(18,2)"),
        ("active", "BOOLEAN DEFAULT true"),
        ("closed", "BOOLEAN DEFAULT false"),
        ("spread", "DECIMAL(6,4)"),
        ("last_trade_price", "DECIMAL(6,4)"),
        ("market_slug", "TEXT"),
        ("event_slug", "TEXT"),
        ("tokens_json", "JSONB"),
    ]

    for col_name, col_type in columns_to_add:
        try:
            await conn.execute(f"ALTER TABLE explorer_markets ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        except Exception as e:
            # Column might already exist with different type
            pass

    # Add full-text search index if not exists
    try:
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_explorer_markets_question_search
            ON explorer_markets USING gin(to_tsvector('english', question))
        """)
    except:
        pass

    # Add index on active + volume for fast queries
    try:
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_explorer_markets_active_volume
            ON explorer_markets (active, volume_num DESC NULLS LAST)
        """)
    except:
        pass


async def upsert_market(conn, market):
    """Upsert a single market with all fields."""
    condition_id = market.get("conditionId") or market.get("condition_id")
    if not condition_id:
        return False

    # Parse all fields
    question = market.get("question", "")[:500]  # Truncate if too long
    description = market.get("description")  # Market description/terms
    if description:
        description = description[:2000]  # Limit length
    market_id = market.get("id") or market.get("market_id")

    # Event ID is in the events array, NOT a flat eventId field
    # API returns: {"events": [{"id": "16092", ...}]}
    event_id = None
    events = market.get("events")
    if events and isinstance(events, list) and len(events) > 0:
        event_id = events[0].get("id")
    # Fallback to legacy fields (some old APIs may use these)
    if not event_id:
        event_id = market.get("eventId") or market.get("event_id")

    category = normalize_category(market)
    end_time = parse_date(market.get("endDate") or market.get("end_date_iso"))

    # Status
    active = market.get("active", True)
    if isinstance(active, str):
        active = active.lower() == "true"
    closed = market.get("closed", False)
    if isinstance(closed, str):
        closed = closed.lower() == "true"
    resolved = closed or market.get("resolved", False)

    # Determine status string
    if resolved or closed:
        status = "resolved"
    else:
        status = "active"

    # Prices - extract both YES and NO
    yes_price, no_price = parse_outcome_prices(market)
    best_bid, best_ask = get_best_bid_ask(market)

    # Calculate spread
    spread = None
    if best_bid is not None and best_ask is not None:
        spread = best_ask - best_bid

    # Volume - use volume24hr specifically (NOT lifetime volume fields)
    # The API's "volume" and "volumeNum" are LIFETIME totals, not 24h
    volume_24h = safe_decimal(
        market.get("volume24hr"),
        max_val=999999999.99
    )

    # 7-day volume from API
    volume_7d = safe_decimal(
        market.get("volume1wk"),
        max_val=999999999.99
    )

    # Keep lifetime volume separate (volumeNum is total all-time volume)
    volume_num = safe_decimal(
        market.get("volumeNum") or market.get("volume"),
        max_val=999999999.99
    )

    # Liquidity
    liquidity = safe_decimal(
        market.get("liquidity") or
        market.get("liquidityNum"),
        max_val=999999999.99
    )
    liquidity_num = safe_decimal(
        market.get("liquidityNum") or
        market.get("liquidity"),
        max_val=999999999.99
    )

    # Open interest from API
    open_interest = safe_decimal(
        market.get("openInterest") or market.get("open_interest"),
        max_val=999999999.99
    )

    # Slugs for URLs
    market_slug = market.get("slug") or market.get("market_slug")
    event_slug = market.get("eventSlug") or market.get("event_slug")

    # Store tokens as JSON for reference
    tokens = market.get("tokens") or market.get("clobTokenIds")
    tokens_json = json.dumps(tokens) if tokens else None

    try:
        await conn.execute("""
            INSERT INTO explorer_markets (
                condition_id, market_id, event_id, question, description, category,
                end_time, resolved, status, yes_price, no_price, best_bid, best_ask,
                volume_24h, volume_7d, open_interest, liquidity_score, updated_at,
                volume, volume_num, liquidity, liquidity_num,
                active, closed, spread, market_slug, event_slug, tokens_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28
            )
            ON CONFLICT (condition_id) DO UPDATE SET
                question = EXCLUDED.question,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                end_time = EXCLUDED.end_time,
                resolved = EXCLUDED.resolved,
                status = EXCLUDED.status,
                yes_price = EXCLUDED.yes_price,
                no_price = EXCLUDED.no_price,
                best_bid = EXCLUDED.best_bid,
                best_ask = EXCLUDED.best_ask,
                volume_24h = EXCLUDED.volume_24h,
                volume_7d = EXCLUDED.volume_7d,
                open_interest = EXCLUDED.open_interest,
                liquidity_score = EXCLUDED.liquidity_score,
                volume = EXCLUDED.volume,
                volume_num = EXCLUDED.volume_num,
                liquidity = EXCLUDED.liquidity,
                liquidity_num = EXCLUDED.liquidity_num,
                active = EXCLUDED.active,
                closed = EXCLUDED.closed,
                spread = EXCLUDED.spread,
                market_slug = EXCLUDED.market_slug,
                event_slug = EXCLUDED.event_slug,
                tokens_json = EXCLUDED.tokens_json,
                updated_at = EXCLUDED.updated_at
        """,
            condition_id,
            market_id,
            event_id,
            question,
            description,
            category,
            end_time,
            resolved,
            status,
            yes_price,
            no_price,
            best_bid,
            best_ask,
            volume_24h,  # Real 24h volume from API
            volume_7d,   # Real 7d volume from API
            open_interest,
            liquidity_num,  # liquidity_score
            datetime.now(timezone.utc),
            volume_24h,  # Also store in volume column for compatibility
            volume_num,  # Lifetime volume
            liquidity,
            liquidity_num,
            active,
            closed,
            spread,
            market_slug,
            event_slug,
            tokens_json,
        )
        return True
    except Exception as e:
        print(f"  Error upserting {condition_id[:20]}...: {e}")
        return False


async def sync_markets(active_only: bool = False, limit: int = None):
    """Main sync function."""
    print("Connecting to database...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    # Record sync start time to detect stale markets
    sync_start = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        print("Ensuring schema...")
        await ensure_schema(conn)

    print(f"Fetching markets from Polymarket (active_only={active_only})...")
    async with httpx.AsyncClient() as client:
        all_markets = await fetch_all_markets(client, active_only=active_only, limit=limit)

    print(f"Total markets fetched: {len(all_markets)}")

    print("Upserting into explorer_markets...")
    success = 0
    failed = 0

    async with pool.acquire() as conn:
        for market in all_markets:
            if await upsert_market(conn, market):
                success += 1
            else:
                failed += 1

        # Mark markets NOT seen in this sync as stale (closed)
        # Only if we fetched active markets (otherwise we'd mark everything as stale)
        if active_only:
            print("Marking unseen markets as stale...")
            stale_result = await conn.execute("""
                UPDATE explorer_markets
                SET status = 'stale',
                    active = false
                WHERE updated_at < $1
                  AND status = 'active'
                  AND active = true
            """, sync_start)
            stale_count = int(stale_result.split()[-1]) if stale_result else 0
            print(f"  Marked {stale_count} markets as stale")

    await pool.close()

    # Print stats
    print(f"\nSync complete!")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")

    # Print data quality
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE active = true) as active_count,
                COUNT(*) FILTER (WHERE volume_num > 0) as with_volume,
                COUNT(*) FILTER (WHERE liquidity_num > 0) as with_liquidity,
                COUNT(*) FILTER (WHERE yes_price IS NOT NULL) as with_price
            FROM explorer_markets
        """)
        print(f"\nData quality:")
        print(f"  Total markets: {stats['total']}")
        print(f"  Active: {stats['active_count']}")
        print(f"  With volume: {stats['with_volume']}")
        print(f"  With liquidity: {stats['with_liquidity']}")
        print(f"  With price: {stats['with_price']}")
    await pool.close()


if __name__ == "__main__":
    active_only = "--active-only" in sys.argv
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    asyncio.run(sync_markets(active_only=active_only, limit=limit))
