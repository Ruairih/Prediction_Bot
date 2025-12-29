#!/usr/bin/env python3
"""
Event sync from Polymarket Gamma API.
Syncs event-level aggregated data and links markets to their parent events.

Usage:
    python sync_events.py [--limit N]
"""

import asyncio
import os
import sys
import httpx
import asyncpg
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


def safe_decimal(val, default=None):
    """Safely convert to Decimal."""
    if val is None:
        return default
    try:
        f = float(val)
        return Decimal(str(round(f, 2)))
    except (ValueError, TypeError, InvalidOperation):
        return default


async def fetch_events(client: httpx.AsyncClient, offset: int = 0, limit: int = 100, active_only: bool = False):
    """Fetch events from Gamma API with pagination."""
    params = {
        "limit": limit,
        "offset": offset,
        "order": "volume",  # Sort by total volume
        "ascending": "false",
    }
    if active_only:
        params["active"] = "true"

    resp = await client.get(f"{GAMMA_API}/events", params=params, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_all_events(client: httpx.AsyncClient, limit: int = None, active_only: bool = False):
    """Fetch all events with pagination."""
    all_events = []
    offset = 0
    page_size = 100
    max_events = limit or 999999

    while len(all_events) < max_events:
        events = await fetch_events(client, offset, page_size, active_only)
        if not events:
            break

        all_events.extend(events)
        print(f"  Fetched {len(all_events)} events so far...")

        if len(events) < page_size:
            break
        offset += page_size

        # Small delay to be nice to the API
        await asyncio.sleep(0.1)

    return all_events[:max_events] if limit else all_events


async def sync_events(limit: int = None, active_only: bool = False):
    """Main sync function."""
    print(f"Starting event sync at {datetime.now(timezone.utc).isoformat()}")
    print(f"Database: {DATABASE_URL.split('@')[-1]}")

    sync_start = datetime.now(timezone.utc)

    async with httpx.AsyncClient() as client:
        print("Fetching events from Polymarket API...")
        events = await fetch_all_events(client, limit, active_only)
        print(f"Fetched {len(events)} events total")

    if not events:
        print("No events fetched!")
        return

    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        events_synced = 0
        markets_linked = 0

        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue

            # Extract event data
            title = event.get("title", "")
            slug = event.get("slug", "")
            description = event.get("description", "")
            category = event.get("category", "")
            image = event.get("image", "")
            icon = event.get("icon", "")
            start_date = parse_date(event.get("startDate"))
            end_date = parse_date(event.get("endDate"))

            # Aggregated metrics
            volume = safe_decimal(event.get("volume"))
            volume_24h = safe_decimal(event.get("volume24hr"))
            volume_7d = safe_decimal(event.get("volume1wk"))
            liquidity = safe_decimal(event.get("liquidity"))
            open_interest = safe_decimal(event.get("openInterest"))

            # Get markets in this event
            markets = event.get("markets", [])
            market_count = len(markets)
            active_market_count = sum(1 for m in markets if m.get("active") and not m.get("closed"))

            # Status
            active = event.get("active", True)
            closed = event.get("closed", False)
            featured = event.get("featured", False)

            # Upsert event
            await conn.execute("""
                INSERT INTO explorer_events (
                    event_id, title, slug, description, category,
                    image, icon, start_date, end_date,
                    volume, volume_24h, volume_7d, liquidity, open_interest,
                    market_count, active_market_count,
                    active, closed, featured, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, NOW())
                ON CONFLICT (event_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    slug = EXCLUDED.slug,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    image = EXCLUDED.image,
                    icon = EXCLUDED.icon,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    volume = EXCLUDED.volume,
                    volume_24h = EXCLUDED.volume_24h,
                    volume_7d = EXCLUDED.volume_7d,
                    liquidity = EXCLUDED.liquidity,
                    open_interest = EXCLUDED.open_interest,
                    market_count = EXCLUDED.market_count,
                    active_market_count = EXCLUDED.active_market_count,
                    active = EXCLUDED.active,
                    closed = EXCLUDED.closed,
                    featured = EXCLUDED.featured,
                    updated_at = NOW()
            """, event_id, title, slug, description, category,
                image, icon, start_date, end_date,
                volume, volume_24h, volume_7d, liquidity, open_interest,
                market_count, active_market_count,
                active, closed, featured)

            events_synced += 1

            # Link markets to this event
            for market in markets:
                condition_id = market.get("conditionId")
                if condition_id:
                    result = await conn.execute("""
                        UPDATE explorer_markets
                        SET event_id = $1
                        WHERE condition_id = $2
                          AND (event_id IS NULL OR event_id = '' OR event_id != $1)
                    """, event_id, condition_id)
                    if "UPDATE 1" in result:
                        markets_linked += 1

            if events_synced % 100 == 0:
                print(f"  Synced {events_synced} events, linked {markets_linked} markets...")

        print(f"\nSync complete!")
        print(f"  Events synced: {events_synced}")
        print(f"  Markets linked to events: {markets_linked}")

        # Show top events by volume
        print("\nTop 10 events by total volume:")
        rows = await conn.fetch("""
            SELECT title, volume, market_count, category
            FROM explorer_events
            ORDER BY volume DESC NULLS LAST
            LIMIT 10
        """)
        for row in rows:
            vol = float(row["volume"] or 0) / 1e6
            print(f"  ${vol:8.1f}M | {row['market_count']:3d} mkts | {row['category'] or 'N/A':15} | {row['title'][:50]}")

    finally:
        await conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of events to sync")
    parser.add_argument("--active-only", action="store_true", help="Only sync active events")
    args = parser.parse_args()

    asyncio.run(sync_events(limit=args.limit, active_only=args.active_only))
