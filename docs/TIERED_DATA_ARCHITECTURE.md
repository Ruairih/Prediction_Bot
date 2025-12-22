# Tiered Data Architecture Specification

> **Status:** PROPOSED
> **Author:** Architecture Review
> **Date:** 2025-12-22
> **Priority:** HIGH - Enables multi-strategy support

---

## Executive Summary

The current bot architecture filters markets at ingestion time based on a single strategy's criteria (high probability >95¢). This prevents other strategies from discovering opportunities and creates a tight coupling between data ingestion and strategy logic.

This specification proposes a **3-tier data architecture** that:
1. Captures metadata for ALL markets (discovery layer)
2. Stores price history for "interesting" markets (analysis layer)
3. Maintains full trade data only for active markets (execution layer)

**Result:** Any strategy can discover any market, while storage remains manageable (~60-100GB vs 1-3TB/year for full mirror).

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Architecture Overview](#architecture-overview)
3. [Tier 1: Market Universe](#tier-1-market-universe)
4. [Tier 2: Price History](#tier-2-price-history)
5. [Tier 3: Trade Data](#tier-3-trade-data)
6. [Interestingness Scoring](#interestingness-scoring)
7. [Promotion Pipeline](#promotion-pipeline)
8. [Strategy Integration](#strategy-integration)
9. [Database Schema](#database-schema)
10. [API Changes](#api-changes)
11. [Migration Plan](#migration-plan)
12. [Storage Estimates](#storage-estimates)
13. [Implementation Phases](#implementation-phases)
14. [Testing Requirements](#testing-requirements)
15. [Rollback Plan](#rollback-plan)

---

## Problem Statement

### Current State

```
Polymarket (10,000+ markets)
         │
         ▼
    ┌─────────────────────┐
    │  Strategy Filter    │  ← "Only markets > 95¢"
    │  (HARDCODED)        │
    └─────────────────────┘
         │
         ▼ (265 markets pass)
    ┌─────────────────────┐
    │  Ingest Trades      │
    └─────────────────────┘
         │
         ▼
    ┌─────────────────────┐
    │  PostgreSQL         │  53 GB, 38.8M trades
    └─────────────────────┘
```

### Problems

1. **Strategy Lock-in:** Only one strategy's criteria decides what data exists
2. **Discovery Blindness:** Can't find opportunities outside current filter
3. **No Flexibility:** Adding new strategy requires re-ingesting historical data
4. **Wasted Opportunity:** Markets that become interesting later have no history

### Examples of Missed Opportunities

| Strategy Type | Criteria | Currently Visible? |
|---------------|----------|-------------------|
| High Probability | >95¢ | YES (current) |
| Low Probability Moonshots | <10¢ | NO |
| Momentum/Breakout | Price moved >20% in 24h | NO |
| New Market Mispricing | Market age <3 days | NO |
| High Volume Liquid | Volume >$100K/day | PARTIAL |
| Category Specific | Politics, Crypto, Sports | PARTIAL |
| Arbitrage | Cross-market spreads | NO |

---

## Architecture Overview

### Proposed State

```
Polymarket (10,000+ markets)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: MARKET UNIVERSE                                    │
│  ───────────────────────────────────────────────────────    │
│  ALL 10,000+ markets                                        │
│  Metadata + Price Snapshots (every 5-15 min)                │
│  Storage: ~500 MB                                           │
│  Purpose: ANY strategy can discover ANY market              │
└─────────────────────────────────────────────────────────────┘
         │
         │ Interestingness Score > threshold
         ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: PRICE HISTORY                                      │
│  ───────────────────────────────────────────────────────    │
│  ~2,000-3,000 "interesting" markets                         │
│  OHLCV Candles (1min, 5min, 1hr, 1day)                     │
│  Storage: ~10-20 GB                                         │
│  Purpose: Strategies can analyze patterns/trends            │
└─────────────────────────────────────────────────────────────┘
         │
         │ Strategy requests OR active position
         ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: TRADE DATA                                         │
│  ───────────────────────────────────────────────────────    │
│  ~200-500 active/watched markets                            │
│  Full trade-by-trade history                                │
│  Real-time orderbook snapshots                              │
│  Storage: ~30-60 GB                                         │
│  Purpose: Precise execution timing                          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  STRATEGIES (pluggable, query any tier)                     │
│  ───────────────────────────────────────────────────────    │
│  • high_prob_yes (current)                                  │
│  • low_prob_moonshot (new)                                  │
│  • momentum_breakout (new)                                  │
│  • category_specialist (new)                                │
│  • arbitrage_scanner (new)                                  │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                      INGESTION PIPELINE                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Every 5 min]                                                   │
│      │                                                           │
│      ▼                                                           │
│  ┌────────────────────┐    ┌─────────────────────────────────┐  │
│  │ Polymarket REST    │───▶│ market_universe (ALL markets)   │  │
│  │ /markets endpoint  │    │ Update metadata + price snapshot│  │
│  └────────────────────┘    └─────────────────────────────────┘  │
│                                       │                          │
│  [Every 15 min]                       │                          │
│      │                                ▼                          │
│      │                       ┌─────────────────────┐             │
│      │                       │ Compute Interest-   │             │
│      │                       │ ingness Scores      │             │
│      │                       └─────────────────────┘             │
│      │                                │                          │
│      │                                ▼                          │
│      │                       ┌─────────────────────┐             │
│      │                       │ Promote/Demote      │             │
│      │                       │ Markets to Tiers    │             │
│      │                       └─────────────────────┘             │
│      │                                │                          │
│      ▼                                ▼                          │
│  ┌────────────────────┐    ┌─────────────────────────────────┐  │
│  │ Polymarket REST    │───▶│ price_candles (Tier 2 markets)  │  │
│  │ /prices endpoint   │    │ Aggregate to OHLCV candles      │  │
│  └────────────────────┘    └─────────────────────────────────┘  │
│                                                                  │
│  [Real-time WebSocket]                                           │
│      │                                                           │
│      ▼                                                           │
│  ┌────────────────────┐    ┌─────────────────────────────────┐  │
│  │ Polymarket WS      │───▶│ polymarket_trades (Tier 3 only) │  │
│  │ Trade stream       │    │ Full trade data                 │  │
│  └────────────────────┘    └─────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Tier 1: Market Universe

### Purpose

- **Complete visibility:** Every market on Polymarket is known to the system
- **Strategy discovery:** Any strategy can scan all markets for opportunities
- **Lightweight:** Only metadata and price snapshots, not trade history

### Data Captured

| Field | Type | Update Frequency | Source |
|-------|------|------------------|--------|
| condition_id | TEXT | Once (immutable) | API |
| market_id | TEXT | Once | API |
| question | TEXT | Once | API |
| description | TEXT | Once | API |
| category | TEXT | Once | API |
| end_date | TIMESTAMP | Once | API |
| created_at | TIMESTAMP | Once | API |
| tokens | JSONB | Once | API (YES/NO token IDs) |
| yes_price | REAL | Every 5 min | API |
| no_price | REAL | Every 5 min | API |
| spread | REAL | Every 5 min | Computed |
| best_bid | REAL | Every 5 min | API |
| best_ask | REAL | Every 5 min | API |
| volume_24h | REAL | Every 5 min | API |
| volume_total | REAL | Every 5 min | API |
| liquidity | REAL | Every 5 min | API |
| trade_count_24h | INTEGER | Every 15 min | Computed |
| price_change_1h | REAL | Every 5 min | Computed |
| price_change_24h | REAL | Every 5 min | Computed |
| interestingness_score | REAL | Every 15 min | Computed |
| tier | INTEGER | Every 15 min | Computed (1, 2, or 3) |
| is_resolved | BOOLEAN | Every 5 min | API |
| resolution_outcome | TEXT | On resolution | API |
| snapshot_at | TIMESTAMP | Every 5 min | System |

### Storage Estimate

```
Fields per market: ~2 KB (with indexes)
Markets: 10,000
Total: ~20 MB base + ~30 MB indexes = ~50 MB

With 30-day snapshot history (optional):
  50 MB × 30 days = 1.5 GB

Recommended: Keep only latest snapshot, archive daily summaries
Final estimate: ~100-200 MB
```

### Update Process

```python
async def update_market_universe():
    """
    Runs every 5 minutes.
    Fetches ALL markets from Polymarket and updates universe table.
    """
    # 1. Fetch all markets from API (paginated)
    markets = await polymarket_client.get_all_markets(limit=10000)

    # 2. Batch upsert to market_universe
    for batch in chunk(markets, size=500):
        await db.execute_many("""
            INSERT INTO market_universe (
                condition_id, market_id, question, category,
                end_date, yes_price, no_price, spread,
                volume_24h, liquidity, snapshot_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (condition_id) DO UPDATE SET
                yes_price = EXCLUDED.yes_price,
                no_price = EXCLUDED.no_price,
                spread = EXCLUDED.spread,
                volume_24h = EXCLUDED.volume_24h,
                liquidity = EXCLUDED.liquidity,
                snapshot_at = NOW()
        """, batch)

    # 3. Mark resolved markets
    await mark_resolved_markets()

    # 4. Compute price changes
    await compute_price_changes()
```

---

## Tier 2: Price History

### Purpose

- **Pattern analysis:** Strategies can analyze price trends without full trade data
- **Backtesting:** Test strategy ideas on historical candle data
- **Efficient storage:** OHLCV candles are 100-1000x smaller than raw trades

### Promotion Criteria (Tier 1 → Tier 2)

A market is promoted to Tier 2 if ANY of:

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| Volume 24h | > $10,000 | Liquid enough to trade |
| Price change 24h | > 5% | Something happening |
| Interestingness score | > 40 | Composite metric |
| Market age | < 7 days | New markets often mispriced |
| Days to resolution | < 14 | Action happening soon |
| Strategy request | Any strategy | Explicit interest |
| Manual watchlist | Added by user | Human judgment |

### Data Captured

```sql
-- Candle data at multiple resolutions
CREATE TABLE price_candles (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    resolution TEXT NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
    bucket_start TIMESTAMP NOT NULL,

    -- OHLCV
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    trade_count INTEGER NOT NULL,

    -- Computed
    vwap REAL,  -- Volume-weighted average price

    PRIMARY KEY (condition_id, token_id, resolution, bucket_start)
);

-- Retention policy
-- 1m candles: 7 days
-- 5m candles: 30 days
-- 1h candles: 90 days
-- 1d candles: Forever
```

### Storage Estimate

```
Per market (YES token only):
  1m candles: 1440/day × 7 days = 10,080 rows × 50 bytes = 500 KB
  5m candles: 288/day × 30 days = 8,640 rows × 50 bytes = 430 KB
  1h candles: 24/day × 90 days = 2,160 rows × 50 bytes = 108 KB
  1d candles: 365/year × 50 bytes = 18 KB

Per market total: ~1 MB

Tier 2 markets: 2,000
Total: ~2 GB raw + indexes = ~5 GB
```

### Candle Aggregation Process

```python
async def aggregate_candles(condition_id: str, token_id: str):
    """
    Aggregate trades into OHLCV candles.
    Called after trade ingestion for Tier 3 markets,
    or from API price history for Tier 2 markets.
    """
    resolutions = ['1m', '5m', '15m', '1h', '4h', '1d']

    for resolution in resolutions:
        interval = parse_interval(resolution)

        await db.execute("""
            INSERT INTO price_candles (
                condition_id, token_id, resolution, bucket_start,
                open_price, high_price, low_price, close_price,
                volume, trade_count, vwap
            )
            SELECT
                $1, $2, $3,
                time_bucket($4, timestamp) as bucket,
                first(price, timestamp) as open,
                max(price) as high,
                min(price) as low,
                last(price, timestamp) as close,
                sum(size * price) as volume,
                count(*) as trades,
                sum(size * price) / sum(size) as vwap
            FROM polymarket_trades
            WHERE condition_id = $1 AND token_id = $2
              AND timestamp > $5
            GROUP BY bucket
            ON CONFLICT DO UPDATE SET
                high_price = GREATEST(price_candles.high_price, EXCLUDED.high_price),
                low_price = LEAST(price_candles.low_price, EXCLUDED.low_price),
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                trade_count = EXCLUDED.trade_count
        """, condition_id, token_id, resolution, interval, last_processed)
```

---

## Tier 3: Trade Data

### Purpose

- **Execution precision:** Exact trade timing, size, orderbook depth
- **G5 protection:** Verify orderbook before execution (Gotcha #5)
- **Slippage analysis:** Understand market microstructure

### Promotion Criteria (Tier 2 → Tier 3)

| Criterion | Description |
|-----------|-------------|
| Strategy signal | Strategy emits BUY/SELL signal |
| Active position | Already holding position in market |
| Pending order | Have open order in market |
| Manual promotion | User explicitly adds to watchlist |
| High conviction | Interestingness score > 80 |

### Data Captured

Uses existing `polymarket_trades` table:

```sql
-- Already exists, no changes needed
CREATE TABLE polymarket_trades (
    condition_id TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    token_id TEXT,
    price REAL,
    size REAL,
    side TEXT,
    timestamp BIGINT,
    raw_json TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    PRIMARY KEY (condition_id, trade_id)
);

-- NEW: Orderbook snapshots for Tier 3 markets
CREATE TABLE orderbook_snapshots (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,

    -- Top of book
    best_bid REAL,
    best_ask REAL,
    spread REAL,

    -- Depth (top 10 levels)
    bids JSONB,  -- [{price: 0.95, size: 1000}, ...]
    asks JSONB,  -- [{price: 0.96, size: 500}, ...]

    -- Aggregate metrics
    bid_depth_10pct REAL,  -- Total size within 10% of best bid
    ask_depth_10pct REAL,

    PRIMARY KEY (condition_id, token_id, snapshot_at)
);
```

### Storage Estimate

```
Tier 3 markets: 300
Trades per market: ~10,000/day (active markets)
Trade row size: ~1 KB

Daily: 300 × 10,000 × 1 KB = 3 GB/day
With 30-day retention: 90 GB

Orderbook snapshots (every 1 min):
  300 markets × 1440 snapshots × 2 KB = 860 MB/day
  With 7-day retention: 6 GB

Total Tier 3: ~100 GB
```

### Retention Policy

```sql
-- Tier 3 trade data retention
-- Keep 30 days for active markets
-- Archive to cold storage (S3/GCS) after 30 days
-- Keep candle aggregates forever

CREATE OR REPLACE FUNCTION cleanup_old_trades()
RETURNS void AS $$
BEGIN
    -- Move old trades to archive
    INSERT INTO polymarket_trades_archive
    SELECT * FROM polymarket_trades
    WHERE timestamp < extract(epoch from now() - interval '30 days');

    -- Delete from main table
    DELETE FROM polymarket_trades
    WHERE timestamp < extract(epoch from now() - interval '30 days');

    -- Clean orderbook snapshots (7 days)
    DELETE FROM orderbook_snapshots
    WHERE snapshot_at < now() - interval '7 days';
END;
$$ LANGUAGE plpgsql;
```

---

## Interestingness Scoring

### Philosophy

Instead of each strategy defining what's "interesting," we compute a **strategy-agnostic interestingness score** that captures general signals of opportunity.

### Scoring Algorithm

```python
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta

@dataclass
class MarketMetrics:
    condition_id: str
    yes_price: float
    volume_24h: float
    liquidity: float
    trade_count_24h: int
    price_change_24h: float
    price_change_1h: float
    spread: float
    days_to_end: Optional[float]
    market_age_days: float
    category: str

def compute_interestingness(m: MarketMetrics) -> float:
    """
    Compute strategy-agnostic interestingness score (0-100).

    Higher scores = more likely to be interesting to SOME strategy.
    This is NOT a trading signal, just a prioritization metric.
    """
    score = 0.0

    # ═══════════════════════════════════════════════════════════
    # VOLUME & LIQUIDITY (max 25 points)
    # More volume = more tradeable, more attention
    # ═══════════════════════════════════════════════════════════

    # Volume score: log scale, max at $1M/day
    if m.volume_24h > 0:
        volume_score = min(15, 15 * (log10(m.volume_24h + 1) / 6))  # 6 = log10(1M)
        score += volume_score

    # Liquidity score: max at $100K
    if m.liquidity > 0:
        liquidity_score = min(10, 10 * (m.liquidity / 100_000))
        score += liquidity_score

    # ═══════════════════════════════════════════════════════════
    # PRICE MOVEMENT (max 25 points)
    # Movement = something happening = potential opportunity
    # ═══════════════════════════════════════════════════════════

    # 24h price change (absolute value matters)
    change_24h_score = min(15, abs(m.price_change_24h) * 150)  # 10% move = 15 pts
    score += change_24h_score

    # 1h price change (recent momentum)
    change_1h_score = min(10, abs(m.price_change_1h) * 200)  # 5% move = 10 pts
    score += change_1h_score

    # ═══════════════════════════════════════════════════════════
    # MARKET TIMING (max 20 points)
    # New markets and near-resolution markets are interesting
    # ═══════════════════════════════════════════════════════════

    # New market bonus (< 7 days old)
    if m.market_age_days < 7:
        new_market_score = 10 * (1 - m.market_age_days / 7)
        score += new_market_score

    # Near resolution bonus (< 14 days to end)
    if m.days_to_end is not None and m.days_to_end < 14:
        resolution_score = 10 * (1 - m.days_to_end / 14)
        score += resolution_score

    # ═══════════════════════════════════════════════════════════
    # PRICE EXTREMES (max 20 points)
    # Extreme prices (near 0 or 1) are interesting to different strategies
    # ═══════════════════════════════════════════════════════════

    # High probability (>90%) - interesting for high_prob strategies
    if m.yes_price > 0.90:
        high_prob_score = 10 * ((m.yes_price - 0.90) / 0.10)
        score += high_prob_score

    # Low probability (<10%) - interesting for moonshot strategies
    if m.yes_price < 0.10:
        low_prob_score = 10 * ((0.10 - m.yes_price) / 0.10)
        score += low_prob_score

    # Mid-range with high volume (competitive/uncertain)
    if 0.40 < m.yes_price < 0.60 and m.volume_24h > 50_000:
        uncertainty_score = 5
        score += uncertainty_score

    # ═══════════════════════════════════════════════════════════
    # SPREAD PENALTY (max -10 points)
    # Wide spreads make trading expensive
    # ═══════════════════════════════════════════════════════════

    if m.spread > 0.05:  # > 5% spread
        spread_penalty = min(10, (m.spread - 0.05) * 100)
        score -= spread_penalty

    # ═══════════════════════════════════════════════════════════
    # CATEGORY BOOST (max 10 points)
    # Some categories historically more predictable/profitable
    # ═══════════════════════════════════════════════════════════

    category_boosts = {
        'politics': 5,
        'crypto': 3,
        'sports': 2,
        'science': 4,
        'economics': 4,
    }
    score += category_boosts.get(m.category.lower(), 0)

    # Clamp to 0-100
    return max(0, min(100, score))
```

### Score Interpretation

| Score Range | Tier Recommendation | Description |
|-------------|---------------------|-------------|
| 0-20 | Tier 1 only | Low activity, skip for now |
| 20-40 | Tier 1, maybe 2 | Worth watching |
| 40-60 | Tier 2 | Track price history |
| 60-80 | Tier 2, consider 3 | High potential |
| 80-100 | Tier 3 | Active monitoring |

---

## Promotion Pipeline

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   PROMOTION PIPELINE                            │
│                   (runs every 15 minutes)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   TIER 1    │────▶│   TIER 2    │────▶│   TIER 3    │       │
│  │  Universe   │     │  History    │     │   Trades    │       │
│  │ 10,000 mkts │     │ 2,000 mkts  │     │  300 mkts   │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│         │                  │                   │                │
│         │   score > 40     │   signal OR       │                │
│         │   OR manual      │   position OR     │                │
│         │   OR new         │   manual          │                │
│         ▼                  ▼                   ▼                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  DEMOTION RULES                          │   │
│  │  • Tier 3 → 2: No position, no signal for 24h           │   │
│  │  • Tier 2 → 1: Score < 20 for 7 days                    │   │
│  │  • Never demote: Manual watchlist items                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation

```python
class TierManager:
    """
    Manages market tier promotions and demotions.
    """

    TIER_1_LIMIT = 15000  # Max markets in universe
    TIER_2_LIMIT = 3000   # Max markets with price history
    TIER_3_LIMIT = 500    # Max markets with full trades

    async def run_promotion_cycle(self):
        """
        Run full promotion/demotion cycle.
        Called every 15 minutes by background task.
        """
        async with self.db.transaction():
            # 1. Update interestingness scores
            await self._update_scores()

            # 2. Promote from Tier 1 → Tier 2
            await self._promote_to_tier_2()

            # 3. Promote from Tier 2 → Tier 3
            await self._promote_to_tier_3()

            # 4. Demote inactive markets
            await self._demote_inactive()

            # 5. Update WebSocket subscriptions
            await self._sync_subscriptions()

    async def _promote_to_tier_2(self):
        """Promote interesting markets to Tier 2."""
        await self.db.execute("""
            UPDATE market_universe
            SET tier = 2, promoted_at = NOW()
            WHERE tier = 1
              AND (
                  interestingness_score >= 40
                  OR market_age_days < 7
                  OR manual_watchlist = true
                  OR condition_id IN (
                      SELECT DISTINCT condition_id
                      FROM strategy_requests
                      WHERE requested_tier >= 2
                  )
              )
            LIMIT $1
        """, self.TIER_2_LIMIT)

    async def _promote_to_tier_3(self):
        """Promote to Tier 3 based on strategy signals."""
        await self.db.execute("""
            UPDATE market_universe
            SET tier = 3, promoted_at = NOW()
            WHERE tier = 2
              AND (
                  -- Has active position
                  condition_id IN (
                      SELECT condition_id FROM positions WHERE status = 'open'
                  )
                  -- Or has pending order
                  OR condition_id IN (
                      SELECT condition_id FROM orders WHERE status IN ('pending', 'open')
                  )
                  -- Or strategy requested it
                  OR condition_id IN (
                      SELECT condition_id FROM strategy_requests
                      WHERE requested_tier = 3
                        AND requested_at > NOW() - INTERVAL '1 hour'
                  )
                  -- Or very high score
                  OR interestingness_score >= 80
                  -- Or manual promotion
                  OR manual_tier_3 = true
              )
            LIMIT $1
        """, self.TIER_3_LIMIT)

    async def _demote_inactive(self):
        """Demote markets that no longer need high tiers."""
        # Tier 3 → Tier 2: No activity for 24h
        await self.db.execute("""
            UPDATE market_universe
            SET tier = 2
            WHERE tier = 3
              AND manual_tier_3 = false
              AND condition_id NOT IN (
                  SELECT condition_id FROM positions WHERE status = 'open'
              )
              AND condition_id NOT IN (
                  SELECT condition_id FROM orders WHERE status IN ('pending', 'open')
              )
              AND last_strategy_signal < NOW() - INTERVAL '24 hours'
        """)

        # Tier 2 → Tier 1: Low score for 7 days
        await self.db.execute("""
            UPDATE market_universe
            SET tier = 1
            WHERE tier = 2
              AND manual_watchlist = false
              AND interestingness_score < 20
              AND promoted_at < NOW() - INTERVAL '7 days'
        """)

    async def request_tier(
        self,
        strategy_name: str,
        condition_id: str,
        tier: int,
        reason: str
    ):
        """
        Strategy requests a market be promoted to a specific tier.
        """
        await self.db.execute("""
            INSERT INTO strategy_requests (
                strategy_name, condition_id, requested_tier, reason, requested_at
            ) VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (strategy_name, condition_id) DO UPDATE SET
                requested_tier = GREATEST(strategy_requests.requested_tier, $3),
                reason = $4,
                requested_at = NOW()
        """, strategy_name, condition_id, tier, reason)
```

---

## Strategy Integration

### Updated Strategy Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

class Tier(Enum):
    UNIVERSE = 1   # Metadata only
    HISTORY = 2    # Price candles
    TRADES = 3     # Full trade data

@dataclass
class MarketQuery:
    """Query parameters for market discovery."""
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[float] = None
    categories: Optional[List[str]] = None
    min_interestingness: Optional[float] = None
    max_days_to_end: Optional[float] = None
    min_market_age_days: Optional[float] = None
    max_market_age_days: Optional[float] = None
    limit: int = 100

@dataclass
class TierRequest:
    """Request to promote market to specific tier."""
    condition_id: str
    tier: Tier
    reason: str

class Strategy(ABC):
    """
    Base strategy interface.

    Strategies can:
    1. Query market_universe for discovery (Tier 1)
    2. Request markets be promoted to higher tiers
    3. Receive price updates for Tier 2+ markets
    4. Evaluate and emit signals
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name."""
        pass

    @property
    def default_query(self) -> MarketQuery:
        """
        Default query for market discovery.
        Override to customize which markets this strategy scans.
        """
        return MarketQuery()

    async def discover_markets(
        self,
        universe: 'MarketUniverseRepository'
    ) -> List[TierRequest]:
        """
        Scan market universe and request tier promotions.

        Called periodically (every 15 min) to discover new opportunities.
        Returns list of markets that should be promoted for closer monitoring.
        """
        return []

    @abstractmethod
    def evaluate(self, context: 'StrategyContext') -> 'Signal':
        """
        Evaluate a market and return trading signal.

        Called when price updates arrive for Tier 2+ markets.
        """
        pass
```

### Example: Multi-Strategy Implementation

```python
class HighProbabilityStrategy(Strategy):
    """Original strategy: buy markets >95¢."""

    @property
    def name(self) -> str:
        return "high_prob_yes"

    @property
    def default_query(self) -> MarketQuery:
        return MarketQuery(
            min_price=0.93,  # Start watching at 93¢
            min_volume=5000,
            max_days_to_end=90,
        )

    async def discover_markets(self, universe) -> List[TierRequest]:
        requests = []

        # Find markets approaching our threshold
        markets = await universe.query(self.default_query)

        for m in markets:
            if m.yes_price >= 0.95:
                # Ready to trade - need full data
                requests.append(TierRequest(
                    condition_id=m.condition_id,
                    tier=Tier.TRADES,
                    reason="Price >= 95¢, ready for execution"
                ))
            elif m.yes_price >= 0.93:
                # Getting close - track price history
                requests.append(TierRequest(
                    condition_id=m.condition_id,
                    tier=Tier.HISTORY,
                    reason="Price >= 93¢, monitoring approach"
                ))

        return requests


class MoonshotStrategy(Strategy):
    """New strategy: buy low probability with high upside."""

    @property
    def name(self) -> str:
        return "moonshot"

    @property
    def default_query(self) -> MarketQuery:
        return MarketQuery(
            max_price=0.10,  # < 10¢
            min_volume=10000,  # Must have liquidity
            min_market_age_days=1,  # Not brand new (avoid spam)
            max_days_to_end=30,  # Resolves soon
        )

    async def discover_markets(self, universe) -> List[TierRequest]:
        requests = []
        markets = await universe.query(self.default_query)

        for m in markets:
            # Look for underpriced markets with catalysts
            if m.price_change_24h > 0.02:  # Moving up
                requests.append(TierRequest(
                    condition_id=m.condition_id,
                    tier=Tier.HISTORY,
                    reason=f"Low prob ({m.yes_price:.0%}) with momentum"
                ))

        return requests


class MomentumStrategy(Strategy):
    """New strategy: trade breakouts and momentum."""

    @property
    def name(self) -> str:
        return "momentum"

    @property
    def default_query(self) -> MarketQuery:
        return MarketQuery(
            min_volume=50000,
            min_interestingness=50,  # Use the score!
        )

    async def discover_markets(self, universe) -> List[TierRequest]:
        requests = []

        # Find markets with significant price movement
        markets = await universe.query(MarketQuery(
            min_volume=20000,
        ))

        for m in markets:
            # Big 24h move
            if abs(m.price_change_24h) > 0.10:
                requests.append(TierRequest(
                    condition_id=m.condition_id,
                    tier=Tier.HISTORY,
                    reason=f"24h move: {m.price_change_24h:+.1%}"
                ))
            # Big 1h move (more urgent)
            elif abs(m.price_change_1h) > 0.05:
                requests.append(TierRequest(
                    condition_id=m.condition_id,
                    tier=Tier.TRADES,
                    reason=f"1h move: {m.price_change_1h:+.1%}"
                ))

        return requests
```

---

## Database Schema

### New Tables

```sql
-- ═══════════════════════════════════════════════════════════════════
-- TIER 1: Market Universe
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE market_universe (
    -- Identity
    condition_id TEXT PRIMARY KEY,
    market_id TEXT,

    -- Metadata (immutable)
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,
    end_date TIMESTAMP,
    created_at TIMESTAMP,

    -- Tokens
    yes_token_id TEXT,
    no_token_id TEXT,

    -- Price snapshot (updated every 5 min)
    yes_price REAL,
    no_price REAL,
    spread REAL,
    best_bid REAL,
    best_ask REAL,

    -- Volume metrics
    volume_24h REAL DEFAULT 0,
    volume_total REAL DEFAULT 0,
    liquidity REAL DEFAULT 0,
    trade_count_24h INTEGER DEFAULT 0,

    -- Price changes (computed)
    price_change_1h REAL DEFAULT 0,
    price_change_24h REAL DEFAULT 0,

    -- Scoring
    interestingness_score REAL DEFAULT 0,

    -- Tier management
    tier INTEGER DEFAULT 1 CHECK (tier IN (1, 2, 3)),
    promoted_at TIMESTAMP,
    manual_watchlist BOOLEAN DEFAULT FALSE,
    manual_tier_3 BOOLEAN DEFAULT FALSE,

    -- Resolution
    is_resolved BOOLEAN DEFAULT FALSE,
    resolution_outcome TEXT,
    resolved_at TIMESTAMP,

    -- Timestamps
    snapshot_at TIMESTAMP DEFAULT NOW(),
    created_in_db_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_universe_tier ON market_universe(tier);
CREATE INDEX idx_universe_score ON market_universe(interestingness_score DESC);
CREATE INDEX idx_universe_category ON market_universe(category);
CREATE INDEX idx_universe_yes_price ON market_universe(yes_price);
CREATE INDEX idx_universe_volume ON market_universe(volume_24h DESC);
CREATE INDEX idx_universe_end_date ON market_universe(end_date);
CREATE INDEX idx_universe_not_resolved ON market_universe(is_resolved) WHERE NOT is_resolved;

-- ═══════════════════════════════════════════════════════════════════
-- TIER 2: Price Candles
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE price_candles (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    resolution TEXT NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
    bucket_start TIMESTAMP NOT NULL,

    -- OHLCV
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    vwap REAL,

    PRIMARY KEY (condition_id, token_id, resolution, bucket_start),

    FOREIGN KEY (condition_id) REFERENCES market_universe(condition_id)
);

-- Indexes for candle queries
CREATE INDEX idx_candles_lookup ON price_candles(condition_id, token_id, resolution, bucket_start DESC);
CREATE INDEX idx_candles_recent ON price_candles(bucket_start DESC);

-- ═══════════════════════════════════════════════════════════════════
-- TIER 3: Orderbook Snapshots
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE orderbook_snapshots (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,

    -- Top of book
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    mid_price REAL,

    -- Depth
    bids JSONB,  -- [{price, size}, ...]
    asks JSONB,

    -- Aggregate metrics
    bid_depth_1pct REAL,
    bid_depth_5pct REAL,
    ask_depth_1pct REAL,
    ask_depth_5pct REAL,

    PRIMARY KEY (condition_id, token_id, snapshot_at)
);

CREATE INDEX idx_orderbook_recent ON orderbook_snapshots(condition_id, token_id, snapshot_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- Strategy Requests
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE strategy_requests (
    strategy_name TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    requested_tier INTEGER NOT NULL,
    reason TEXT,
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (strategy_name, condition_id)
);

CREATE INDEX idx_requests_tier ON strategy_requests(requested_tier, requested_at DESC);

-- ═══════════════════════════════════════════════════════════════════
-- Price Change History (for computing changes)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE price_snapshots (
    condition_id TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,
    yes_price REAL,
    volume_24h REAL,

    PRIMARY KEY (condition_id, snapshot_at)
);

-- Keep 24 hours of snapshots for change calculation
CREATE INDEX idx_snapshots_recent ON price_snapshots(snapshot_at DESC);
```

### Migration Script

```sql
-- Migration: Add tiered data architecture
-- Run this AFTER backing up the database

BEGIN;

-- 1. Create new tables (see schema above)
-- ...

-- 2. Populate market_universe from existing data
INSERT INTO market_universe (
    condition_id,
    question,
    yes_token_id,
    no_token_id,
    tier,
    created_in_db_at
)
SELECT DISTINCT
    condition_id,
    'Unknown (migration)', -- Will be updated by first API fetch
    token_id,
    NULL,
    CASE
        WHEN condition_id IN (SELECT DISTINCT condition_id FROM polymarket_trades)
        THEN 3  -- Has trade data = Tier 3
        ELSE 1
    END,
    NOW()
FROM polymarket_token_meta
ON CONFLICT DO NOTHING;

-- 3. Set existing watched markets to Tier 2+
UPDATE market_universe
SET tier = 2, manual_watchlist = TRUE
WHERE condition_id IN (
    SELECT condition_id FROM stream_watchlist
);

-- 4. Set markets with positions to Tier 3
UPDATE market_universe
SET tier = 3
WHERE condition_id IN (
    SELECT condition_id FROM positions WHERE status = 'open'
);

COMMIT;
```

---

## API Changes

### New Endpoints (internal)

```python
# Market Universe Repository
class MarketUniverseRepository:

    async def query(self, q: MarketQuery) -> List[MarketSnapshot]:
        """Query market universe with filters."""

    async def get_by_tier(self, tier: int) -> List[str]:
        """Get all condition_ids at a specific tier."""

    async def get_interestingness_leaders(self, limit: int = 100) -> List[MarketSnapshot]:
        """Get markets with highest interestingness scores."""

    async def promote(self, condition_id: str, tier: int, reason: str):
        """Promote market to higher tier."""

    async def demote(self, condition_id: str, tier: int):
        """Demote market to lower tier."""

# Price History Repository
class PriceHistoryRepository:

    async def get_candles(
        self,
        condition_id: str,
        resolution: str,
        start: datetime,
        end: datetime
    ) -> List[Candle]:
        """Get OHLCV candles for a market."""

    async def get_latest_candle(
        self,
        condition_id: str,
        resolution: str
    ) -> Optional[Candle]:
        """Get most recent candle."""
```

### Dashboard API Updates

```python
# New endpoints for dashboard

@app.route("/api/universe/stats")
def universe_stats():
    """Get tier distribution and top markets."""
    return {
        "tier_counts": {1: 9500, 2: 450, 3: 50},
        "total_markets": 10000,
        "top_by_score": [...],
        "recent_promotions": [...],
    }

@app.route("/api/universe/search")
def universe_search():
    """Search market universe."""
    # Query params: q, category, min_price, max_price, etc.
    pass

@app.route("/api/market/<condition_id>/history")
def market_history(condition_id: str):
    """Get price history for a market."""
    # Returns candles if Tier 2+, else just current snapshot
    pass
```

---

## Storage Estimates

### Summary Table

| Component | Size | Growth Rate | Retention |
|-----------|------|-------------|-----------|
| market_universe | 200 MB | +10 MB/month | Forever |
| price_snapshots (24h) | 500 MB | Stable | 24 hours |
| price_candles (Tier 2) | 5 GB | +500 MB/month | Varies by resolution |
| orderbook_snapshots | 6 GB | Stable | 7 days |
| polymarket_trades (Tier 3) | 50 GB | +3 GB/day | 30 days active |
| polymarket_trades_archive | Growing | +90 GB/month | Cold storage |

### Total Active Storage

```
Tier 1: 200 MB + 500 MB = 700 MB
Tier 2: 5 GB
Tier 3: 50 GB + 6 GB = 56 GB
─────────────────────────────────
Total: ~62 GB active

Compare to current: 53 GB
Compare to full mirror: 1-3 TB/year
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Create market_universe table, populate from API

- [ ] Create `market_universe` table schema
- [ ] Implement `MarketUniverseRepository`
- [ ] Add background task: fetch all markets every 5 min
- [ ] Implement basic interestingness scoring
- [ ] Add `tier` column management
- [ ] Dashboard: show tier distribution

**Deliverable:** All 10,000+ markets visible in database

### Phase 2: Price History (Week 2)
**Goal:** Add Tier 2 candle aggregation

- [ ] Create `price_candles` table
- [ ] Implement candle aggregation from trades
- [ ] Add candle fetching from API (for markets without trades)
- [ ] Implement retention policies
- [ ] Dashboard: show price charts for Tier 2 markets

**Deliverable:** Price history for top 2,000 markets

### Phase 3: Promotion Pipeline (Week 3)
**Goal:** Automatic tier management

- [ ] Implement `TierManager` class
- [ ] Add promotion/demotion rules
- [ ] Create `strategy_requests` table
- [ ] Connect to WebSocket subscription management
- [ ] Add manual watchlist support

**Deliverable:** Markets automatically flow between tiers

### Phase 4: Strategy Integration (Week 4)
**Goal:** Update strategy interface

- [ ] Update `Strategy` base class with `discover_markets()`
- [ ] Update `StrategyContext` with tier info
- [ ] Migrate `high_prob_yes` strategy to new interface
- [ ] Add example `moonshot` strategy
- [ ] Add example `momentum` strategy

**Deliverable:** Multiple strategies discovering different markets

### Phase 5: Dashboard & Polish (Week 5)
**Goal:** Full visibility and monitoring

- [ ] Universe browser in dashboard
- [ ] Tier promotion history view
- [ ] Strategy discovery stats
- [ ] Performance optimization
- [ ] Documentation

**Deliverable:** Production-ready tiered architecture

---

## Testing Requirements

### Unit Tests

```python
class TestInterestingnessScoring:
    """Test scoring algorithm."""

    def test_high_volume_scores_higher(self):
        high_vol = compute_interestingness(MarketMetrics(volume_24h=1_000_000, ...))
        low_vol = compute_interestingness(MarketMetrics(volume_24h=1_000, ...))
        assert high_vol > low_vol

    def test_price_movement_increases_score(self):
        moving = compute_interestingness(MarketMetrics(price_change_24h=0.15, ...))
        stable = compute_interestingness(MarketMetrics(price_change_24h=0.01, ...))
        assert moving > stable

    def test_new_markets_get_bonus(self):
        new = compute_interestingness(MarketMetrics(market_age_days=2, ...))
        old = compute_interestingness(MarketMetrics(market_age_days=30, ...))
        assert new > old

    def test_wide_spread_penalized(self):
        tight = compute_interestingness(MarketMetrics(spread=0.01, ...))
        wide = compute_interestingness(MarketMetrics(spread=0.15, ...))
        assert tight > wide


class TestTierPromotion:
    """Test tier management."""

    async def test_high_score_promotes_to_tier_2(self):
        market = create_market(interestingness_score=50)
        await tier_manager.run_promotion_cycle()
        assert market.tier == 2

    async def test_strategy_request_promotes_to_tier_3(self):
        await tier_manager.request_tier("test", "cond_123", 3, "testing")
        await tier_manager.run_promotion_cycle()
        market = await repo.get("cond_123")
        assert market.tier == 3

    async def test_inactive_demotes_after_24h(self):
        market = create_market(tier=3, last_activity=hours_ago(25))
        await tier_manager.run_promotion_cycle()
        assert market.tier == 2


class TestMarketDiscovery:
    """Test strategy discovery interface."""

    async def test_high_prob_discovers_95_plus(self):
        strategy = HighProbabilityStrategy()
        await create_market(yes_price=0.96)
        await create_market(yes_price=0.50)

        requests = await strategy.discover_markets(universe)

        assert len(requests) == 1
        assert requests[0].tier == Tier.TRADES

    async def test_moonshot_discovers_low_prob(self):
        strategy = MoonshotStrategy()
        await create_market(yes_price=0.05, volume_24h=50000)
        await create_market(yes_price=0.50)

        requests = await strategy.discover_markets(universe)

        assert len(requests) == 1
```

### Integration Tests

```python
class TestFullPipeline:
    """End-to-end tier management tests."""

    async def test_new_market_flows_through_tiers(self):
        # 1. Market appears in API
        market = await api.create_market(...)

        # 2. Universe fetch picks it up
        await universe_fetcher.run()
        assert await repo.exists(market.condition_id)
        assert (await repo.get(market.condition_id)).tier == 1

        # 3. Price moves, score increases
        await simulate_price_movement(market, change=0.15)
        await scorer.run()

        # 4. Promotion cycle promotes to Tier 2
        await tier_manager.run_promotion_cycle()
        assert (await repo.get(market.condition_id)).tier == 2

        # 5. Strategy signals, promotes to Tier 3
        await strategy.emit_signal(market.condition_id, "BUY")
        await tier_manager.run_promotion_cycle()
        assert (await repo.get(market.condition_id)).tier == 3
```

---

## Rollback Plan

### If Issues Arise

1. **Immediate:** Disable promotion pipeline, freeze tiers
2. **Short-term:** Revert to hardcoded market list for ingestion
3. **Full rollback:** Drop new tables, restore original behavior

### Backward Compatibility

- Existing `polymarket_trades` table unchanged
- Existing strategies continue to work
- New tables are additive, not replacing

### Feature Flags

```python
FEATURE_FLAGS = {
    "tiered_data_enabled": True,
    "auto_promotion_enabled": True,
    "strategy_discovery_enabled": True,
    "universe_fetch_enabled": True,
}
```

---

## Open Questions

1. **Historical backfill:** Should we backfill candles from API for existing Tier 2 markets?

2. **Cross-market analysis:** Some strategies need to compare multiple markets (arbitrage). Should there be a "market group" concept?

3. **Category-based tiers:** Should entire categories be promotable? (e.g., "promote all crypto markets to Tier 2")

4. **Cost tracking:** Should we track API call costs per tier to optimize fetch frequency?

5. **Machine learning integration:** Could interestingness scoring incorporate ML predictions?

---

## Appendix: Polymarket API Reference

### Relevant Endpoints

```
GET /markets
  - Returns all markets with metadata
  - Pagination: ?limit=100&offset=0
  - ~10,000 markets total

GET /markets/{condition_id}
  - Single market details
  - Includes current prices, volume

GET /prices-history
  - Historical price data
  - Parameters: market, interval, fidelity

GET /book
  - Current orderbook
  - Bids and asks with sizes

WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/market
  - Real-time price updates
  - Subscribe by asset_ids (token IDs)
```

### Rate Limits

- REST: ~100 requests/minute
- WebSocket: 100 subscriptions per connection
- Recommendation: Batch market fetches, use WS for real-time

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-12-22 | 1.0 | Initial specification |

