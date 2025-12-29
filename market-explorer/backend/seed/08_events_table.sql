-- Events table for storing event-level aggregated data
-- Events group multiple related markets (e.g., "2028 Democratic Presidential Nominee" groups 128 candidate markets)

CREATE TABLE IF NOT EXISTS explorer_events (
    event_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT,
    description TEXT,
    category TEXT,
    image TEXT,
    icon TEXT,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,

    -- Aggregated metrics (sum of all markets in event)
    volume NUMERIC(20, 2),           -- Total volume (lifetime)
    volume_24h NUMERIC(20, 2),       -- 24h volume
    volume_7d NUMERIC(20, 2),        -- 7 day volume
    liquidity NUMERIC(20, 2),        -- Total liquidity
    open_interest NUMERIC(20, 2),

    -- Market counts
    market_count INTEGER DEFAULT 0,
    active_market_count INTEGER DEFAULT 0,

    -- Status
    active BOOLEAN DEFAULT true,
    closed BOOLEAN DEFAULT false,
    featured BOOLEAN DEFAULT false,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_explorer_events_volume ON explorer_events(volume DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_explorer_events_volume_24h ON explorer_events(volume_24h DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_explorer_events_category ON explorer_events(category);
CREATE INDEX IF NOT EXISTS idx_explorer_events_active ON explorer_events(active);

-- Add comment
COMMENT ON TABLE explorer_events IS 'Stores event-level aggregated data from Polymarket. Events group multiple related markets.';
