-- Market Explorer Database Schema
-- This schema is separate from the trading bot tables

-- Core market table for the explorer
CREATE TABLE IF NOT EXISTS explorer_markets (
    condition_id TEXT PRIMARY KEY,
    market_id TEXT,
    event_id TEXT,
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,
    auto_category TEXT,
    end_time TIMESTAMPTZ,
    resolution_time TIMESTAMPTZ,
    resolved BOOLEAN DEFAULT FALSE,
    outcome TEXT,
    status TEXT DEFAULT 'active',

    -- Pricing
    yes_price DECIMAL(6,4),
    no_price DECIMAL(6,4),
    best_bid DECIMAL(6,4),
    best_ask DECIMAL(6,4),

    -- Liquidity metrics
    volume_24h DECIMAL(14,2),
    volume_7d DECIMAL(14,2),
    open_interest DECIMAL(14,2),
    liquidity_score DECIMAL(6,2),

    -- Price changes
    price_change_1h DECIMAL(6,4),
    price_change_24h DECIMAL(6,4),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT valid_yes_price CHECK (yes_price >= 0 AND yes_price <= 1),
    CONSTRAINT valid_no_price CHECK (no_price >= 0 AND no_price <= 1)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_explorer_markets_category ON explorer_markets(category);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_status ON explorer_markets(status);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_resolved ON explorer_markets(resolved);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_end_time ON explorer_markets(end_time);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_volume_24h ON explorer_markets(volume_24h DESC);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_liquidity_score ON explorer_markets(liquidity_score DESC);
CREATE INDEX IF NOT EXISTS idx_explorer_markets_event_id ON explorer_markets(event_id);

-- Full-text search index on question (requires pg_trgm extension)
-- Run this separately if pg_trgm is available:
-- CREATE INDEX IF NOT EXISTS idx_explorer_markets_question_trgm ON explorer_markets USING gin (question gin_trgm_ops);

-- Fallback: B-tree index for prefix matching
CREATE INDEX IF NOT EXISTS idx_explorer_markets_question ON explorer_markets(question);

-- OHLCV time-series data (use TimescaleDB if available)
CREATE TABLE IF NOT EXISTS explorer_ohlcv (
    condition_id TEXT NOT NULL,
    bucket TIMESTAMPTZ NOT NULL,
    timeframe TEXT NOT NULL,
    open DECIMAL(6,4),
    high DECIMAL(6,4),
    low DECIMAL(6,4),
    close DECIMAL(6,4),
    volume DECIMAL(14,2),
    trade_count INT,
    PRIMARY KEY (condition_id, bucket, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_explorer_ohlcv_condition_bucket ON explorer_ohlcv(condition_id, bucket DESC);

-- Orderbook snapshots for depth analysis
CREATE TABLE IF NOT EXISTS explorer_orderbook_snapshots (
    id SERIAL PRIMARY KEY,
    condition_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    side TEXT NOT NULL,
    depth_json JSONB NOT NULL,
    spread DECIMAL(6,4),
    depth_1pct DECIMAL(14,2),
    depth_5pct DECIMAL(14,2),
    depth_10pct DECIMAL(14,2)
);

CREATE INDEX IF NOT EXISTS idx_explorer_orderbook_condition ON explorer_orderbook_snapshots(condition_id, timestamp DESC);

-- User tags for custom categorization
CREATE TABLE IF NOT EXISTS explorer_user_tags (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, condition_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_explorer_user_tags_user ON explorer_user_tags(user_id);
CREATE INDEX IF NOT EXISTS idx_explorer_user_tags_tag ON explorer_user_tags(tag);

-- Saved filters/views
CREATE TABLE IF NOT EXISTS explorer_saved_filters (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    filter_json JSONB NOT NULL,
    pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_explorer_saved_filters_user ON explorer_saved_filters(user_id);

-- Watchlists
CREATE TABLE IF NOT EXISTS explorer_watchlists (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    condition_ids TEXT[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_explorer_watchlists_user ON explorer_watchlists(user_id);

-- Market correlation cache
CREATE TABLE IF NOT EXISTS explorer_correlations (
    market_a TEXT NOT NULL,
    market_b TEXT NOT NULL,
    window TEXT NOT NULL,
    correlation DECIMAL(5,4),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (market_a, market_b, window)
);

-- Alerts configuration
CREATE TABLE IF NOT EXISTS explorer_alerts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    condition_id TEXT,
    alert_type TEXT NOT NULL,
    threshold DECIMAL(10,4),
    enabled BOOLEAN DEFAULT TRUE,
    last_triggered TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_explorer_alerts_user ON explorer_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_explorer_alerts_condition ON explorer_alerts(condition_id);

-- Enable trigram extension for fuzzy search (run as superuser)
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
