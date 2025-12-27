ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS exit_status TEXT;

UPDATE positions
SET exit_status = 'pending'
WHERE exit_pending IS TRUE
  AND (exit_status IS NULL OR exit_status = '');

UPDATE positions
SET exit_status = NULL
WHERE exit_pending IS FALSE
  AND exit_status = 'pending';
