-- Migration: Add age_source column to positions table
-- This permanently fixes the recurring bug where synced positions never exit
-- because hold_start_at was set to NOW during sync.
--
-- CRITICAL FIX: Unknown age positions are now ELIGIBLE for exit.
-- Only positions with age_source='bot_created' or 'actual' will have
-- the 7-day hold enforced. All others can exit at profit target.

-- Add age_source column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'positions' AND column_name = 'age_source'
    ) THEN
        ALTER TABLE positions ADD COLUMN age_source TEXT DEFAULT 'unknown';

        -- Add comment explaining the column
        COMMENT ON COLUMN positions.age_source IS
            'Reliability of timestamp for exit logic. Values: bot_created (trusted), actual (trusted), unknown (NOT trusted - eligible for exit). Default unknown ensures synced positions can exit.';
    END IF;
END
$$;

-- CRITICAL: Set all existing positions without age_source to 'unknown'
-- This ensures they are ELIGIBLE for exit (not blocked by 7-day hold)
UPDATE positions
SET age_source = 'unknown'
WHERE age_source IS NULL;

-- Set bot_trade positions to 'bot_created' (trusted timestamp)
UPDATE positions
SET age_source = 'bot_created'
WHERE import_source = 'bot_trade'
  AND age_source = 'unknown'
  AND hold_start_at IS NOT NULL
  AND hold_start_at != created_at;  -- Only if hold_start was explicitly set

-- Log the migration
DO $$
DECLARE
    unknown_count INTEGER;
    bot_created_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unknown_count FROM positions WHERE age_source = 'unknown';
    SELECT COUNT(*) INTO bot_created_count FROM positions WHERE age_source = 'bot_created';

    RAISE NOTICE 'age_source migration complete: % unknown, % bot_created',
        unknown_count, bot_created_count;
END
$$;
