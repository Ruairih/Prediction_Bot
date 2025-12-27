-- Fix liquidity_score column precision
-- The original DECIMAL(6,2) can only hold max 9999.99
-- But liquidity values from Polymarket can be in the millions

-- Alter liquidity_score to handle larger values
ALTER TABLE explorer_markets
    ALTER COLUMN liquidity_score TYPE DECIMAL(14,2);

-- Also ensure the dynamically-added columns have proper types
-- (these may have been added by sync script with incorrect sizes)
DO $$
BEGIN
    -- Make liquidity columns consistent with schema
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'explorer_markets' AND column_name = 'liquidity') THEN
        ALTER TABLE explorer_markets ALTER COLUMN liquidity TYPE DECIMAL(14,2);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'explorer_markets' AND column_name = 'liquidity_num') THEN
        ALTER TABLE explorer_markets ALTER COLUMN liquidity_num TYPE DECIMAL(14,2);
    END IF;
END $$;
