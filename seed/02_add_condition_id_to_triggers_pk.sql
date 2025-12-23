-- Migration: Add condition_id to polymarket_first_triggers unique constraint
-- This fixes G2 (duplicate token IDs across markets) by ensuring we dedupe
-- by (token_id, condition_id, threshold) instead of just (token_id, threshold).
--
-- PostgreSQL-compatible migration with safe deduplication

-- Step 1: Add condition_id column if not exists (with default for existing rows)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'polymarket_first_triggers'
          AND column_name = 'condition_id'
    ) THEN
        ALTER TABLE polymarket_first_triggers ADD COLUMN condition_id TEXT NOT NULL DEFAULT '';
    END IF;
END $$;

-- Step 2: Deduplicate using CTE with row_number to handle ties deterministically
-- Keep the oldest row (by trigger_timestamp, then by ctid for ties)
DELETE FROM polymarket_first_triggers
WHERE ctid IN (
    SELECT ctid FROM (
        SELECT ctid,
               ROW_NUMBER() OVER (
                   PARTITION BY token_id, COALESCE(condition_id, ''), threshold
                   ORDER BY trigger_timestamp ASC, ctid ASC
               ) as rn
        FROM polymarket_first_triggers
    ) ranked
    WHERE rn > 1
);

-- Step 3: Drop old primary key constraint if it exists
DO $$
DECLARE
    pk_name TEXT;
BEGIN
    -- Find the current primary key constraint name (schema-qualified)
    SELECT tc.constraint_name INTO pk_name
    FROM information_schema.table_constraints tc
    WHERE tc.table_schema = current_schema()
      AND tc.table_name = 'polymarket_first_triggers'
      AND tc.constraint_type = 'PRIMARY KEY';

    IF pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE polymarket_first_triggers DROP CONSTRAINT %I', pk_name);
        RAISE NOTICE 'Dropped old primary key: %', pk_name;
    END IF;
END $$;

-- Step 4: Add new primary key with condition_id included
-- This will fail if duplicates still exist (shouldn't happen after step 2)
ALTER TABLE polymarket_first_triggers
ADD CONSTRAINT polymarket_first_triggers_pkey
PRIMARY KEY (token_id, condition_id, threshold);

-- Step 5: Add indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_triggers_condition
    ON polymarket_first_triggers(condition_id);
CREATE INDEX IF NOT EXISTS idx_triggers_threshold
    ON polymarket_first_triggers(threshold);
CREATE INDEX IF NOT EXISTS idx_triggers_token_threshold
    ON polymarket_first_triggers(token_id, threshold);

-- Step 6: Add unique constraint for G2 protection at DB level
-- This ensures only ONE trigger per (condition_id, threshold) even if code is bypassed
CREATE UNIQUE INDEX IF NOT EXISTS idx_triggers_condition_threshold_unique
    ON polymarket_first_triggers(condition_id, threshold);

-- Verify: Report the new PK structure
DO $$
DECLARE
    pk_cols TEXT;
BEGIN
    SELECT string_agg(a.attname, ', ' ORDER BY array_position(i.indkey, a.attnum))
    INTO pk_cols
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    WHERE i.indrelid = 'polymarket_first_triggers'::regclass AND i.indisprimary;

    RAISE NOTICE 'New primary key columns: %', pk_cols;
END $$;
