-- Pipeline Visibility Tables
-- Tracks rejection statistics and manual overrides for dashboard visibility

-- =============================================================================
-- Aggregated rejection stats (persisted hourly from in-memory counters)
-- =============================================================================
CREATE TABLE IF NOT EXISTS pipeline_rejection_stats (
    id SERIAL PRIMARY KEY,
    bucket_start TIMESTAMP NOT NULL,
    bucket_end TIMESTAMP NOT NULL,
    stage TEXT NOT NULL,  -- 'g1_trade_age', 'g5_orderbook', 'duplicate', etc.
    count INTEGER NOT NULL DEFAULT 0,
    -- Sample rejection for this bucket (for drill-down)
    sample_token_id TEXT,
    sample_condition_id TEXT,
    sample_price REAL,
    sample_question TEXT,
    sample_rejection_values JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stats_bucket
    ON pipeline_rejection_stats(bucket_start);
CREATE INDEX IF NOT EXISTS idx_pipeline_stats_stage
    ON pipeline_rejection_stats(stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_stats_bucket_stage
    ON pipeline_rejection_stats(bucket_start, stage);

-- =============================================================================
-- Manual overrides audit trail
-- =============================================================================
CREATE TABLE IF NOT EXISTS manual_overrides (
    id SERIAL PRIMARY KEY,
    override_type TEXT NOT NULL,  -- 'force_trade', 'skip_trade', 'unblock'
    condition_id TEXT NOT NULL,
    token_id TEXT,

    -- Who and why
    actor TEXT NOT NULL DEFAULT 'dashboard',
    reason TEXT NOT NULL,

    -- Safety acknowledgments (for force_trade)
    acknowledged_g1 BOOLEAN DEFAULT FALSE,
    acknowledged_g5 BOOLEAN DEFAULT FALSE,
    acknowledged_g6 BOOLEAN DEFAULT FALSE,

    -- Trade parameters (for force_trade)
    override_price REAL,
    override_size REAL,
    max_slippage REAL,

    -- Result tracking
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'executed', 'failed', 'cancelled'
    execution_result JSONB,
    error_message TEXT,

    -- Timestamps
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_overrides_condition
    ON manual_overrides(condition_id);
CREATE INDEX IF NOT EXISTS idx_overrides_status
    ON manual_overrides(status);
CREATE INDEX IF NOT EXISTS idx_overrides_created
    ON manual_overrides(created_at DESC);

-- =============================================================================
-- Market blocks (persistent blocklist)
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_blocks (
    condition_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    blocked_by TEXT NOT NULL DEFAULT 'dashboard',
    blocked_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Comments
-- =============================================================================
COMMENT ON TABLE pipeline_rejection_stats IS
    'Hourly aggregated rejection statistics from pipeline tracker';
COMMENT ON TABLE manual_overrides IS
    'Audit trail for manual trading overrides from dashboard';
COMMENT ON TABLE market_blocks IS
    'Markets manually blocked from trading';
