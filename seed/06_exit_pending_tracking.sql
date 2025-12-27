-- Migration: Track pending exit orders on positions
-- Prevents duplicate exit orders when a previous exit is still live.

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS exit_pending BOOLEAN DEFAULT FALSE;

UPDATE positions
SET exit_pending = FALSE
WHERE exit_pending IS NULL;
