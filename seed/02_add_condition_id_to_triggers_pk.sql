-- Migration: Add condition_id to polymarket_first_triggers unique constraint
-- This fixes G2 (duplicate token IDs across markets) by ensuring we dedupe
-- by (token_id, condition_id, threshold) instead of just (token_id, threshold).

-- For SQLite, we need to recreate the table to change the primary key
-- This is idempotent - if the table already has the right structure, this is a no-op

-- Create new table with correct PK
CREATE TABLE IF NOT EXISTS polymarket_first_triggers_new (
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL DEFAULT '',
    threshold REAL NOT NULL,
    trigger_timestamp BIGINT NOT NULL,
    price REAL,
    size REAL,
    created_at TEXT NOT NULL,
    model_score REAL,
    model_version TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    PRIMARY KEY (token_id, condition_id, threshold)
);

-- Copy data from old table if it exists (ignore duplicates)
INSERT OR IGNORE INTO polymarket_first_triggers_new
SELECT
    token_id,
    COALESCE(condition_id, '') as condition_id,
    threshold,
    trigger_timestamp,
    price,
    size,
    created_at,
    model_score,
    model_version,
    outcome,
    outcome_index
FROM polymarket_first_triggers;

-- Drop old table
DROP TABLE IF EXISTS polymarket_first_triggers;

-- Rename new table
ALTER TABLE polymarket_first_triggers_new RENAME TO polymarket_first_triggers;

-- Add index on condition_id for G2 checks
CREATE INDEX IF NOT EXISTS idx_triggers_condition ON polymarket_first_triggers(condition_id);
CREATE INDEX IF NOT EXISTS idx_triggers_threshold ON polymarket_first_triggers(threshold);
