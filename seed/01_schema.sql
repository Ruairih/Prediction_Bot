CREATE TABLE IF NOT EXISTS stream_watchlist (
    market_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    slug TEXT NOT NULL,
    category TEXT,
    best_bid REAL,
    best_ask REAL,
    liquidity REAL,
    volume REAL,
    end_date TEXT,
    generated_at TEXT NOT NULL,
    condition_id TEXT
);

CREATE TABLE IF NOT EXISTS polymarket_trades (
    condition_id TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    token_id TEXT,
    price REAL,
    size REAL,
    side TEXT,
    timestamp BIGINT,
    raw_json TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    PRIMARY KEY (condition_id, trade_id)
);

CREATE TABLE IF NOT EXISTS trade_watermarks (
    condition_id TEXT PRIMARY KEY,
    last_timestamp BIGINT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS polymarket_first_triggers (
    token_id TEXT NOT NULL,
    condition_id TEXT,
    threshold REAL NOT NULL,
    trigger_timestamp BIGINT NOT NULL,
    price REAL,
    size REAL,
    created_at TEXT NOT NULL,
    model_score REAL,
    model_version TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    PRIMARY KEY (token_id, threshold)
);

CREATE TABLE IF NOT EXISTS trigger_watermarks (
    threshold REAL PRIMARY KEY,
    last_timestamp BIGINT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS polymarket_candidates (
    id SERIAL PRIMARY KEY,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    threshold REAL NOT NULL,
    trigger_timestamp BIGINT NOT NULL,
    price REAL,
    status TEXT NOT NULL,
    score REAL,
    created_at TEXT NOT NULL,
    model_score REAL,
    model_version TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS candidate_watermarks (
    threshold REAL PRIMARY KEY,
    last_created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    threshold REAL NOT NULL,
    trigger_timestamp BIGINT,
    candidate_price REAL,
    fill_price REAL,
    size REAL,
    model_score REAL,
    model_version TEXT,
    decision TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    description TEXT,
    outcome TEXT,
    outcome_index INTEGER
);

CREATE TABLE IF NOT EXISTS polymarket_resolutions (
    condition_id TEXT PRIMARY KEY,
    winning_outcome_index INTEGER,
    winning_outcome TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS polymarket_token_meta (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT,
    market_id TEXT,
    outcome_index INTEGER,
    outcome TEXT,
    question TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS live_orders (
    id SERIAL PRIMARY KEY,
    order_id TEXT UNIQUE,
    candidate_id INTEGER NOT NULL,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    threshold REAL NOT NULL,
    order_price REAL,
    order_size REAL,
    fill_price REAL,
    fill_size REAL,
    status TEXT NOT NULL,
    reason TEXT,
    submitted_at TEXT NOT NULL,
    filled_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    market_id TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    side TEXT NOT NULL DEFAULT 'BUY',
    size REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_cost REAL NOT NULL,
    current_price REAL,
    current_value REAL,
    unrealized_pnl REAL,
    realized_pnl REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    resolution TEXT,
    entry_order_id TEXT,
    exit_order_id TEXT,
    entry_timestamp TEXT NOT NULL,
    exit_timestamp TEXT,
    resolved_at TEXT,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(token_id, entry_timestamp)
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    realized_pnl REAL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    num_trades INTEGER DEFAULT 0,
    num_wins INTEGER DEFAULT 0,
    num_losses INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS trade_approvals (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT,
    approved_at TEXT NOT NULL,
    approved_by TEXT DEFAULT 'telegram',
    max_price REAL DEFAULT 0.98,
    expires_at TEXT,
    status TEXT DEFAULT 'pending',
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS approval_alerts (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT,
    question TEXT,
    price REAL,
    model_score REAL,
    alerted_at TEXT NOT NULL,
    approved BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS exit_events (
    id SERIAL PRIMARY KEY,
    position_id INTEGER NOT NULL,
    token_id TEXT NOT NULL,
    condition_id TEXT,
    exit_type TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    size REAL NOT NULL,
    gross_pnl REAL NOT NULL,
    net_pnl REAL NOT NULL,
    hours_held REAL NOT NULL,
    exit_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT,
    created_at TEXT NOT NULL,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS market_scores_cache (
    condition_id TEXT PRIMARY KEY,
    market_id TEXT,
    question TEXT,
    category TEXT,
    best_bid REAL,
    best_ask REAL,
    spread_pct REAL,
    liquidity REAL,
    volume REAL,
    end_date TEXT,
    time_to_end_hours REAL,
    model_score REAL,
    passes_filters INTEGER,
    filter_rejections TEXT,
    is_weather INTEGER,
    is_crypto INTEGER,
    is_politics INTEGER,
    is_sports INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS score_history (
    id SERIAL PRIMARY KEY,
    token_id TEXT,
    score REAL,
    time_to_end_hours REAL,
    scored_at BIGINT
);

CREATE TABLE IF NOT EXISTS trade_watchlist (
    token_id TEXT PRIMARY KEY,
    market_id TEXT,
    condition_id TEXT,
    question TEXT,
    trigger_price REAL,
    trigger_size REAL,
    trigger_timestamp BIGINT,
    initial_score REAL,
    current_score REAL,
    time_to_end_hours REAL,
    last_scored_at BIGINT,
    status TEXT DEFAULT 'watching',
    created_at BIGINT,
    updated_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_candidate ON paper_trades(candidate_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_status ON live_orders(status);
CREATE INDEX IF NOT EXISTS idx_live_orders_candidate ON live_orders(candidate_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_token ON live_orders(token_id);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_token ON positions(token_id);
CREATE INDEX IF NOT EXISTS idx_exit_events_position ON exit_events(position_id);
CREATE INDEX IF NOT EXISTS idx_exit_events_status ON exit_events(status);
CREATE INDEX IF NOT EXISTS idx_score_history_token ON score_history(token_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON trade_watchlist(status);
