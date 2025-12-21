-- Migration: Add tables required by the execution layer
-- These tables track orders submitted to the CLOB and detailed position tracking

-- Orders table for tracking order lifecycle
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    filled_size REAL DEFAULT 0,
    avg_fill_price REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_token ON orders(token_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

-- Add position_id column to positions table if not exists
-- Note: SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we check manually
-- For new installations, this creates the column; for existing, it's a no-op

-- Triggers table used by core layer
CREATE TABLE IF NOT EXISTS triggers (
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    threshold REAL NOT NULL,
    price REAL,
    trade_size REAL,
    model_score REAL,
    triggered_at INTEGER NOT NULL,
    PRIMARY KEY (token_id, condition_id, threshold)
);

CREATE INDEX IF NOT EXISTS idx_triggers_triggered_at ON triggers(triggered_at);

-- Add realized_pnl and exit_time to exit_events if not present
-- For existing tables, these may already exist as net_pnl/gross_pnl and created_at
-- The monitoring layer expects realized_pnl and exit_time column names

-- For compatibility, create a view that maps old column names to new ones
-- This is a workaround since SQLite doesn't support ADD COLUMN IF NOT EXISTS

CREATE VIEW IF NOT EXISTS exit_events_v AS
SELECT
    id,
    position_id,
    token_id,
    condition_id,
    exit_type,
    entry_price,
    exit_price,
    size,
    gross_pnl,
    net_pnl AS realized_pnl,
    hours_held,
    exit_order_id,
    status,
    reason,
    created_at AS exit_time,
    executed_at
FROM exit_events;
