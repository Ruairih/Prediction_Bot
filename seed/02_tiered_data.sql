-- Tiered Data Architecture Migration
-- Adds market universe, price candles, and tier management tables

-- ═══════════════════════════════════════════════════════════════════════════
-- TIER 1: Market Universe
-- Complete view of all Polymarket markets with metadata and price snapshots
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS market_universe (
    -- Identity
    condition_id TEXT PRIMARY KEY,
    market_id TEXT,

    -- Metadata (mostly immutable)
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,
    end_date TIMESTAMP,
    created_at TIMESTAMP,

    -- Outcome tokens (JSONB to support multi-outcome markets)
    -- Format: [{"token_id": "0x...", "outcome": "Yes", "outcome_index": 0}, ...]
    outcomes JSONB NOT NULL DEFAULT '[]',
    outcome_count INTEGER DEFAULT 2,

    -- Price snapshot for primary outcome (usually YES for binary markets)
    -- Updated every 5 minutes
    price REAL,
    best_bid REAL,
    best_ask REAL,
    spread REAL,

    -- Volume metrics
    volume_24h REAL DEFAULT 0,
    volume_total REAL DEFAULT 0,
    liquidity REAL DEFAULT 0,
    trade_count_24h INTEGER DEFAULT 0,

    -- Price changes (computed from price_snapshots table)
    price_change_1h REAL DEFAULT 0,
    price_change_24h REAL DEFAULT 0,

    -- Interestingness scoring
    interestingness_score REAL DEFAULT 0,

    -- Tier management (1=Universe, 2=History, 3=Trades)
    tier INTEGER DEFAULT 1 CHECK (tier IN (1, 2, 3)),
    tier_changed_at TIMESTAMP,
    pinned_tier INTEGER,  -- Manual override, prevents demotion below this tier

    -- Resolution status
    is_resolved BOOLEAN DEFAULT FALSE,
    resolution_outcome TEXT,
    winning_outcome_index INTEGER,  -- 0=Yes, 1=No for binary markets
    resolved_at TIMESTAMP,

    -- Timestamps
    snapshot_at TIMESTAMP DEFAULT NOW(),
    created_in_db_at TIMESTAMP DEFAULT NOW(),

    -- Tracking for demotion rules
    last_strategy_signal_at TIMESTAMP,
    score_below_threshold_since TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_universe_tier ON market_universe(tier);
CREATE INDEX IF NOT EXISTS idx_universe_score ON market_universe(interestingness_score DESC);
CREATE INDEX IF NOT EXISTS idx_universe_category ON market_universe(category);
CREATE INDEX IF NOT EXISTS idx_universe_price ON market_universe(price);
CREATE INDEX IF NOT EXISTS idx_universe_volume ON market_universe(volume_24h DESC);
CREATE INDEX IF NOT EXISTS idx_universe_end_date ON market_universe(end_date);
CREATE INDEX IF NOT EXISTS idx_universe_active ON market_universe(is_resolved) WHERE NOT is_resolved;
CREATE INDEX IF NOT EXISTS idx_universe_tier_score ON market_universe(tier, interestingness_score DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- Price Snapshots (for computing price changes)
-- Keep 24 hours of 5-minute snapshots
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS price_snapshots (
    condition_id TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,
    price REAL,
    volume_24h REAL,

    PRIMARY KEY (condition_id, snapshot_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_recent ON price_snapshots(snapshot_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- TIER 2: Price Candles
-- OHLCV candles at multiple resolutions for interesting markets
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS price_candles (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    resolution TEXT NOT NULL,  -- '5m', '1h', '1d'
    bucket_start TIMESTAMP NOT NULL,

    -- OHLCV
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    vwap REAL,

    PRIMARY KEY (condition_id, token_id, resolution, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON price_candles(condition_id, token_id, resolution, bucket_start DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- TIER 3: Orderbook Snapshots
-- Top-of-book and depth for active markets
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    snapshot_at TIMESTAMP NOT NULL,

    -- Top of book
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    mid_price REAL,

    -- Depth (top 5 levels as JSONB)
    bids JSONB,  -- [{price, size}, ...]
    asks JSONB,

    -- Aggregate depth metrics
    bid_depth_5pct REAL,  -- Total size within 5% of best bid
    ask_depth_5pct REAL,

    PRIMARY KEY (condition_id, token_id, snapshot_at)
);

CREATE INDEX IF NOT EXISTS idx_orderbook_recent
    ON orderbook_snapshots(condition_id, token_id, snapshot_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- Strategy Tier Requests
-- Strategies can request markets be promoted to specific tiers
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS strategy_tier_requests (
    strategy_name TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    requested_tier INTEGER NOT NULL CHECK (requested_tier IN (2, 3)),
    reason TEXT,
    requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL DEFAULT (NOW() + INTERVAL '1 hour'),

    PRIMARY KEY (strategy_name, condition_id)
);

-- Note: Can't use NOW() in index predicate (not immutable)
-- Filter at query time instead
CREATE INDEX IF NOT EXISTS idx_tier_requests_tier
    ON strategy_tier_requests(requested_tier, expires_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- Cleanup Functions
-- ═══════════════════════════════════════════════════════════════════════════

-- Function to clean up old price snapshots (keep 24h)
CREATE OR REPLACE FUNCTION cleanup_old_price_snapshots()
RETURNS void AS $$
BEGIN
    DELETE FROM price_snapshots
    WHERE snapshot_at < NOW() - INTERVAL '24 hours';
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old candles based on retention policy
CREATE OR REPLACE FUNCTION cleanup_old_candles()
RETURNS void AS $$
BEGIN
    -- 5m candles: 7 days
    DELETE FROM price_candles
    WHERE resolution = '5m' AND bucket_start < NOW() - INTERVAL '7 days';

    -- 1h candles: 90 days
    DELETE FROM price_candles
    WHERE resolution = '1h' AND bucket_start < NOW() - INTERVAL '90 days';

    -- 1d candles: keep forever (no cleanup)
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old orderbook snapshots (keep 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_orderbook_snapshots()
RETURNS void AS $$
BEGIN
    DELETE FROM orderbook_snapshots
    WHERE snapshot_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

-- Function to clean up expired tier requests
CREATE OR REPLACE FUNCTION cleanup_expired_tier_requests()
RETURNS void AS $$
BEGIN
    DELETE FROM strategy_tier_requests
    WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;
