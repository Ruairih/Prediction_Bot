-- Sync Status Tracking
-- Tracks sync job executions for health monitoring and debugging

-- Sync runs history table
CREATE TABLE IF NOT EXISTS explorer_sync_runs (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,                    -- 'market_sync', 'price_update', etc.
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INT,

    -- Metrics
    rows_fetched INT DEFAULT 0,
    rows_upserted INT DEFAULT 0,
    rows_failed INT DEFAULT 0,

    -- Error tracking
    error_message TEXT,

    -- Lock tracking
    lock_acquired BOOLEAN DEFAULT TRUE,
    locked_by TEXT,                            -- hostname/pid that holds lock

    -- API stats
    api_calls INT DEFAULT 0,
    api_retry_count INT DEFAULT 0
);

-- Index for finding latest runs quickly
CREATE INDEX IF NOT EXISTS idx_explorer_sync_runs_job_started
    ON explorer_sync_runs(job_name, started_at DESC);

-- Index for finding failed runs
CREATE INDEX IF NOT EXISTS idx_explorer_sync_runs_status
    ON explorer_sync_runs(status) WHERE status = 'failed';

-- Current sync status view (latest run per job)
CREATE OR REPLACE VIEW explorer_sync_status AS
SELECT DISTINCT ON (job_name)
    job_name,
    status,
    started_at,
    finished_at,
    duration_ms,
    rows_upserted,
    rows_failed,
    error_message,
    EXTRACT(EPOCH FROM (NOW() - COALESCE(finished_at, started_at)))::INT AS seconds_since_run,
    CASE
        WHEN status = 'running' THEN 'syncing'
        WHEN status = 'failed' THEN 'error'
        WHEN EXTRACT(EPOCH FROM (NOW() - finished_at)) > 600 THEN 'stale'  -- >10 min
        WHEN EXTRACT(EPOCH FROM (NOW() - finished_at)) > 120 THEN 'warning'  -- >2 min
        ELSE 'healthy'
    END AS health_status
FROM explorer_sync_runs
ORDER BY job_name, started_at DESC;

-- Function to clean up old sync runs (keep last 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_sync_runs() RETURNS void AS $$
BEGIN
    DELETE FROM explorer_sync_runs
    WHERE started_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

-- Comment for documentation
COMMENT ON TABLE explorer_sync_runs IS 'Tracks execution history of sync jobs for monitoring';
COMMENT ON VIEW explorer_sync_status IS 'Current sync status per job type with health indicators';
