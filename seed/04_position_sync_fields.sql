-- Migration: Add fields for position sync/import tracking
-- These fields support importing existing Polymarket positions into the bot

-- Add import tracking fields to positions table
ALTER TABLE positions ADD COLUMN IF NOT EXISTS imported_at TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS import_source TEXT DEFAULT 'bot_trade';
ALTER TABLE positions ADD COLUMN IF NOT EXISTS hold_start_at TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS cost_basis_unknown BOOLEAN DEFAULT FALSE;

-- import_source values:
--   'bot_trade' = position created by bot's own trading
--   'polymarket_sync' = imported from Polymarket API
--   'manual_import' = manually imported by user

-- hold_start_at: When the 7-day hold period starts (for exit logic)
--   For bot trades: same as entry_timestamp
--   For imports: can be set to import time (Option A) or backdated (Option B)

-- Create positions_sync_log table for audit trail
CREATE TABLE IF NOT EXISTS positions_sync_log (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    sync_type TEXT NOT NULL,  -- 'full', 'incremental', 'manual'
    wallet_address TEXT NOT NULL,
    positions_found INTEGER NOT NULL DEFAULT 0,
    positions_imported INTEGER NOT NULL DEFAULT 0,
    positions_updated INTEGER NOT NULL DEFAULT 0,
    positions_closed INTEGER NOT NULL DEFAULT 0,
    errors TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'))
);

-- Index for querying sync history
CREATE INDEX IF NOT EXISTS idx_positions_sync_log_wallet
    ON positions_sync_log(wallet_address);
CREATE INDEX IF NOT EXISTS idx_positions_sync_log_run_id
    ON positions_sync_log(run_id);

-- Update existing positions to have hold_start_at = entry_timestamp (for consistency)
UPDATE positions
SET hold_start_at = entry_timestamp,
    import_source = 'bot_trade'
WHERE hold_start_at IS NULL;
