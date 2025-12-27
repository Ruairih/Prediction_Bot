-- Migration: Cleanup stale markets
-- Markets that are closed/resolved should have their liquidity zeroed out
-- or be marked properly so they don't appear in active sorts

-- First, let's see what we're dealing with (for manual review)
-- SELECT condition_id, question, liquidity_score, status, closed, active, updated_at
-- FROM explorer_markets
-- WHERE liquidity_score > 100000 AND (closed = true OR status = 'resolved')
-- ORDER BY liquidity_score DESC LIMIT 20;

-- Mark markets as resolved/closed if they haven't been updated in 30 days
-- and have high liquidity (likely stale)
UPDATE explorer_markets
SET status = 'stale',
    active = false
WHERE updated_at < NOW() - INTERVAL '30 days'
  AND liquidity_score > 100000
  AND status != 'resolved';

-- For truly closed markets, zero out the liquidity to prevent sort issues
-- (This is optional - only do if you want to be aggressive)
-- UPDATE explorer_markets
-- SET liquidity_score = 0
-- WHERE closed = true OR status = 'resolved';

-- Add index for faster filtering on active markets
CREATE INDEX IF NOT EXISTS idx_explorer_markets_active_status
ON explorer_markets (status, active) WHERE status = 'active' AND active = true;

-- Add index for liquidity sorting on active markets only
CREATE INDEX IF NOT EXISTS idx_explorer_markets_active_liquidity
ON explorer_markets (liquidity_score DESC NULLS LAST) 
WHERE status = 'active' AND active = true;

-- Comment showing expected behavior
COMMENT ON COLUMN explorer_markets.liquidity_score IS 
'Current orderbook liquidity in USD. Only reliable for active markets - resolved markets may have stale values.';
