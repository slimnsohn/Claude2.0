-- Core market data
CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,              -- platform:market_id
    platform TEXT NOT NULL,           -- 'polymarket' or 'kalshi'
    title TEXT NOT NULL,
    resolution_rules TEXT NOT NULL,
    end_date TEXT,
    volume REAL,
    liquidity REAL,
    current_yes_price REAL,
    book_depth_5pct REAL,            -- total depth within 5% of mid
    raw_json TEXT,                    -- full API response
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL
);

-- Track rule changes over time
CREATE TABLE IF NOT EXISTS rule_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    resolution_rules TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    rules_hash TEXT NOT NULL,         -- SHA256 for change detection
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Claude analysis results
CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    rules_hash TEXT NOT NULL,         -- links to which snapshot was analyzed
    prompt_version TEXT NOT NULL,     -- for A/B tracking
    mismatch_found INTEGER NOT NULL,  -- 0 or 1
    severity TEXT,                    -- 'high', 'medium', 'low', 'none'
    mismatch_categories TEXT,         -- JSON array of triggered categories
    retail_assumption TEXT,           -- what retail thinks
    actual_resolution TEXT,           -- what rules actually say
    rules_adjusted_probability REAL,  -- Claude's estimate
    market_price_at_analysis REAL,    -- snapshot of price when analyzed
    price_divergence REAL,            -- rules_adjusted_prob - market_price
    priority_score REAL,              -- severity × liquidity × price_extremity
    raw_response TEXT,                -- full Claude JSON response
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Cross-platform market matching
CREATE TABLE IF NOT EXISTS cross_platform_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    polymarket_id TEXT NOT NULL,
    kalshi_id TEXT NOT NULL,
    match_confidence REAL NOT NULL,   -- fuzzy match score 0-1
    title_similarity REAL,
    date_match INTEGER,               -- 0 or 1
    rule_divergence_summary TEXT,     -- how rules differ
    arb_signal INTEGER DEFAULT 0,     -- 1 if structural arb detected
    detected_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    FOREIGN KEY (polymarket_id) REFERENCES markets(id),
    FOREIGN KEY (kalshi_id) REFERENCES markets(id)
);

-- Your actual positions (import from cashflow logger)
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    side TEXT NOT NULL,               -- 'YES' or 'NO'
    avg_price REAL NOT NULL,
    quantity REAL NOT NULL,
    entered_at TEXT NOT NULL,
    exited_at TEXT,
    pnl REAL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Historical resolution audit
CREATE TABLE IF NOT EXISTS resolution_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    resolved_at TEXT,
    resolution_outcome TEXT,          -- 'YES', 'NO', 'VOID', etc.
    resolved_per_rules INTEGER,       -- 1 = resolved per rules, 0 = resolved per title implication
    mismatch_was_flagged INTEGER,     -- 1 if we flagged this pre-resolution
    mismatch_severity_at_flag TEXT,   -- what severity we assigned
    price_at_flag REAL,               -- price when we flagged
    price_at_resolution REAL,         -- final price before resolution
    notes TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Prompt A/B testing
CREATE TABLE IF NOT EXISTS prompt_evals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_version TEXT NOT NULL,
    eval_run_at TEXT NOT NULL,
    labeled_market_id TEXT NOT NULL,
    expected_mismatch INTEGER NOT NULL,  -- 1 = real mismatch, 0 = clean
    predicted_mismatch INTEGER NOT NULL,
    predicted_severity TEXT,
    is_correct INTEGER NOT NULL,         -- 1 if prediction matches label
    latency_ms INTEGER,
    token_count INTEGER,
    notes TEXT
);

-- Dismissed alerts (don't re-alert)
CREATE TABLE IF NOT EXISTS dismissed_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    reason TEXT,                       -- optional user note
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Watchlist (tracked markets with price monitoring)
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    target_price REAL,                -- alert if price crosses this
    notes TEXT,
    FOREIGN KEY (market_id) REFERENCES markets(id)
);

-- Resolution source monitors
CREATE TABLE IF NOT EXISTS source_monitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,         -- 'BLS CPI', 'AP Race Call', etc.
    source_url TEXT,
    last_checked_at TEXT,
    last_updated_at TEXT,              -- when source content last changed
    content_hash TEXT,                 -- detect changes
    linked_market_ids TEXT,            -- JSON array of market IDs resolving on this source
    quirks TEXT                        -- JSON object of known behaviors
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_markets_platform ON markets(platform);
CREATE INDEX IF NOT EXISTS idx_markets_volume ON markets(volume);
CREATE INDEX IF NOT EXISTS idx_analysis_severity ON analysis_results(severity);
CREATE INDEX IF NOT EXISTS idx_analysis_priority ON analysis_results(priority_score);
CREATE INDEX IF NOT EXISTS idx_snapshots_market ON rule_snapshots(market_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_hash ON rule_snapshots(rules_hash);
CREATE INDEX IF NOT EXISTS idx_cross_match ON cross_platform_matches(polymarket_id, kalshi_id);
CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_id);
CREATE INDEX IF NOT EXISTS idx_audit_market ON resolution_audit(market_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_market ON watchlist(market_id);
