# Polymarket Market Explorer - Technical Specification

> **A professional, read-only dashboard for discovering, analyzing, and monitoring Polymarket prediction markets**

---

## Executive Summary

### What This Is

A **standalone market explorer dashboard** that provides a dense, professional interface for viewing all Polymarket markets. Unlike the existing trading bot dashboard (which monitors bot activity and positions), this tool is focused purely on **market discovery and analysis**.

### Key Differentiators from Trading Bot Dashboard

| Aspect | Trading Bot Dashboard | Market Explorer |
|--------|----------------------|-----------------|
| **Purpose** | Monitor bot activity | Discover & analyze markets |
| **Scope** | Bot's positions/signals only | ALL Polymarket markets |
| **Users** | Bot operator | Researchers, analysts, traders |
| **Data Focus** | Execution, P&L, signals | Liquidity, spreads, trends |
| **Trading** | Shows bot's trades | Read-only, no trading |

### Architecture Decision: Standalone with Shared Data

**Recommendation: Standalone application that shares the ingestion layer with the trading bot.**

Rationale:
- **Separation of concerns**: Different users, different risk profiles
- **Independent scaling**: Market explorer may have heavy analytics workloads
- **Simpler deployment**: Can run without the trading bot
- **Shared efficiency**: Avoids duplicate API calls to Polymarket
- **Read-only safety**: No risk of accidental trades

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED INGESTION LAYER                        │
│         (REST, WebSocket, CLOB - one source of truth)           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED POSTGRESQL DATABASE                    │
│              (Markets, Orderbooks, Trades, Prices)              │
└─────────────────────────────────────────────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────┐
│   TRADING BOT       │               │  MARKET EXPLORER    │
│   DASHBOARD         │               │  (This Spec)        │
│                     │               │                     │
│ - Bot status        │               │ - All markets       │
│ - Positions         │               │ - Analysis tools    │
│ - Signals           │               │ - Categorization    │
│ - P&L tracking      │               │ - Watchlists        │
│ - Bot controls      │               │ - Alerts            │
└─────────────────────┘               └─────────────────────┘
```

---

## Target Users

### Primary Personas

1. **Quant Researcher**
   - Needs: Historical data, correlations, model inputs
   - Wants: API access, bulk exports, backtesting data

2. **Discretionary Trader**
   - Needs: Real-time spreads, liquidity depth, momentum
   - Wants: Watchlists, alerts, quick scanning

3. **Market Analyst**
   - Needs: Category analysis, volume trends, resolution tracking
   - Wants: Custom tags, saved views, reports

### Non-Goals (Explicitly Out of Scope)

- Order placement or trade execution
- Portfolio tracking (use trading bot dashboard)
- Wallet integration
- P&L calculation for user positions

---

## Data Architecture

### Data Sources

| Source | Data | Refresh Rate | Purpose |
|--------|------|--------------|---------|
| **Polymarket REST** | Market metadata, events | 1-5 min | Authoritative market info |
| **Gamma Markets API** | Enhanced metadata, grouping | 5 min | Event clustering, tags |
| **CLOB REST** | Full orderbook snapshots | 1-5 min | Depth analytics, reconciliation |
| **WebSocket** | Real-time bid/ask, trades | Real-time | Live pricing, trade flow |

### Canonical Data Model

```sql
-- Core market metadata
CREATE TABLE explorer_markets (
    condition_id TEXT PRIMARY KEY,
    market_id TEXT,
    event_id TEXT,                    -- For grouping related markets
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,                    -- Platform category
    auto_category TEXT,               -- Our ML/rule-based category
    end_time TIMESTAMPTZ,
    resolution_time TIMESTAMPTZ,
    resolved BOOLEAN DEFAULT FALSE,
    outcome TEXT,                     -- YES/NO/INVALID after resolution

    -- Pricing (updated real-time)
    yes_price DECIMAL(6,4),
    no_price DECIMAL(6,4),
    best_bid DECIMAL(6,4),
    best_ask DECIMAL(6,4),
    spread DECIMAL(6,4),
    mid_price DECIMAL(6,4),

    -- Volume & Liquidity
    volume_24h DECIMAL(14,2),
    volume_7d DECIMAL(14,2),
    open_interest DECIMAL(14,2),
    liquidity_score DECIMAL(6,2),     -- Computed metric

    -- Momentum
    price_change_1h DECIMAL(6,4),
    price_change_24h DECIMAL(6,4),
    price_velocity DECIMAL(8,4),      -- Rate of change

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_prices CHECK (yes_price >= 0 AND yes_price <= 1)
);

-- Time-series price/volume (use TimescaleDB hypertable)
CREATE TABLE explorer_ohlcv (
    condition_id TEXT NOT NULL,
    bucket TIMESTAMPTZ NOT NULL,      -- 1min, 5min, 1h, 1d
    timeframe TEXT NOT NULL,          -- '1m', '5m', '1h', '1d'
    open DECIMAL(6,4),
    high DECIMAL(6,4),
    low DECIMAL(6,4),
    close DECIMAL(6,4),
    volume DECIMAL(14,2),
    trade_count INT,
    PRIMARY KEY (condition_id, bucket, timeframe)
);

-- Orderbook snapshots for depth analysis
CREATE TABLE explorer_orderbook_snapshots (
    id SERIAL PRIMARY KEY,
    condition_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    side TEXT NOT NULL,               -- 'YES' or 'NO'
    depth_json JSONB NOT NULL,        -- [{price, size}, ...]
    spread DECIMAL(6,4),
    depth_1pct DECIMAL(14,2),         -- Liquidity within 1% of mid
    depth_5pct DECIMAL(14,2),
    depth_10pct DECIMAL(14,2)
);

-- User tags and watchlists
CREATE TABLE explorer_user_tags (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,            -- For multi-user support
    condition_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, condition_id, tag)
);

CREATE TABLE explorer_saved_filters (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    filter_json JSONB NOT NULL,       -- Query parameters
    pinned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE explorer_watchlists (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    condition_ids TEXT[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Market correlation cache
CREATE TABLE explorer_correlations (
    market_a TEXT NOT NULL,
    market_b TEXT NOT NULL,
    window TEXT NOT NULL,             -- '1d', '7d', '30d'
    correlation DECIMAL(5,4),
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (market_a, market_b, window)
);
```

### Derived Metrics (Computed on Ingestion)

| Metric | Formula | Update Frequency |
|--------|---------|------------------|
| **Spread** | best_ask - best_bid | Real-time |
| **Mid Price** | (best_bid + best_ask) / 2 | Real-time |
| **Liquidity Score** | Weighted depth in tight bands | 1 min |
| **Price Velocity** | EMA of price change rate | 1 min |
| **Momentum Score** | Short/long EMA cross signal | 5 min |
| **Correlation** | Rolling returns correlation | 1 hour |

---

## Feature Specifications

### F1: Market Screener (Core Feature)

**Purpose**: Dense, sortable, filterable view of all markets

**Layout**:
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Search...] [Category ▼] [Status ▼] [Liquidity ▼] [More Filters] [Save View]│
├─────────────────────────────────────────────────────────────────────────────┤
│ ┌─────┬────────────────────────┬───────┬───────┬────────┬───────┬─────────┐ │
│ │ ★   │ Market                 │ Price │Spread │ Vol 24h│ Depth │ Expires │ │
│ ├─────┼────────────────────────┼───────┼───────┼────────┼───────┼─────────┤ │
│ │ ☆   │ Will BTC hit $150k?    │ 0.42  │ 0.02  │ $124K  │ ████  │ 45d     │ │
│ │     │ ▁▂▃▅▆▇█▇▅ (sparkline)  │ +2.1% │       │        │       │         │ │
│ ├─────┼────────────────────────┼───────┼───────┼────────┼───────┼─────────┤ │
│ │ ★   │ Trump wins 2028?       │ 0.31  │ 0.01  │ $89K   │ ██████│ 1095d   │ │
│ │     │ ▅▆▇█▇▆▅▄▃ (sparkline)  │ -1.3% │       │        │       │         │ │
│ └─────┴────────────────────────┴───────┴───────┴────────┴───────┴─────────┘ │
│                                                                              │
│ Showing 1,247 of 3,421 markets                              [< 1 2 3 ... >] │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Columns (Configurable)**:

| Column | Description | Sortable |
|--------|-------------|----------|
| Star | Watchlist toggle | - |
| Market | Question + inline sparkline | Yes |
| Price | Current YES price | Yes |
| Change | 1h/24h price change | Yes |
| Spread | Bid-ask spread | Yes |
| Volume 24h | Trading volume | Yes |
| Depth | Liquidity bar visualization | Yes |
| Open Interest | Total deployed capital | Yes |
| Category | Market category tag | Yes |
| Expires | Time to resolution | Yes |
| Status | Active/Resolving/Resolved | Yes |

**Filters**:

| Filter | Type | Options |
|--------|------|---------|
| Category | Multi-select | Crypto, Politics, Sports, etc. |
| Price Range | Range slider | 0.00 - 1.00 |
| Spread Max | Slider | 0.01 - 0.20 |
| Min Volume | Input | $1K, $10K, $100K, etc. |
| Min Liquidity | Slider | Score 0-100 |
| Time to Expiry | Range | 1h - 1yr+ |
| Status | Multi-select | Active, Resolving, Resolved |
| Tags | Multi-select | User-defined tags |

**View Modes**:
- **Compact**: 20 rows visible, minimal columns
- **Standard**: 15 rows, balanced info
- **Detailed**: 10 rows, all columns + expanded sparklines

### F2: Market Detail Panel

**Purpose**: Deep-dive into a single market without leaving the screener

**Activation**: Click row or hover + pin

**Layout**:
```
┌─────────────────────────────────────────────────────────────────┐
│ Will Bitcoin hit $150,000 by end of 2025?              [★] [×] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  YES: $0.42 (+2.1%)    NO: $0.58 (-2.1%)    Spread: $0.02       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │          PRICE CHART (24h / 7d / 30d / All)                 ││
│  │     $0.50 ──────────────────────────────────────────        ││
│  │     $0.40 ─────────────────────────────/────────────        ││
│  │     $0.30 ──────────────────/───────────────────────        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │ ORDERBOOK DEPTH      │  │ STATS                            │ │
│  │                      │  │                                  │ │
│  │ Bids        Asks     │  │ Volume 24h:    $124,532          │ │
│  │ ████████    ████     │  │ Open Interest: $1.2M             │ │
│  │ ██████      ██████   │  │ Trades 24h:    1,247             │ │
│  │ ████        ████████ │  │ Avg Trade:     $99.78            │ │
│  │                      │  │ Liquidity:     A+ (92/100)       │ │
│  │ Depth @ 5%: $45K     │  │ Created:       2024-01-15        │ │
│  └──────────────────────┘  │ Expires:       2025-12-31        │ │
│                            └──────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ RECENT TRADES                                            │   │
│  │ 14:32:01  BUY   $0.42   150 shares   $63.00             │   │
│  │ 14:31:45  SELL  $0.41   200 shares   $82.00             │   │
│  │ 14:30:12  BUY   $0.42   75 shares    $31.50             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Related Markets: [Trump wins 2028] [GOP nominee] [+3 more]     │
│  Tags: [crypto] [bitcoin] [+ Add Tag]                           │
└─────────────────────────────────────────────────────────────────┘
```

### F3: Categorization & Tagging

**Auto-Categorization Pipeline**:

```python
# Rule-based first pass (high precision)
CATEGORY_RULES = {
    'crypto': [r'\b(bitcoin|btc|eth|ethereum|crypto|defi)\b'],
    'politics': [r'\b(president|election|congress|senate|vote)\b'],
    'sports': [r'\b(nfl|nba|mlb|championship|playoffs|super bowl)\b'],
    'entertainment': [r'\b(oscar|grammy|emmy|box office|movie)\b'],
    'macro': [r'\b(fed|interest rate|inflation|gdp|recession)\b'],
    'tech': [r'\b(apple|google|microsoft|ai|ipo|acquisition)\b'],
}

# Embedding-based fallback for fuzzy matches
# Use sentence-transformers for semantic similarity to category exemplars
```

**User Tagging**:
- Click "+ Add Tag" on any market
- Autocomplete from existing tags
- Tags visible in screener as chips
- Filter by tags in screener

**Saved Filters/Views**:
- Save current filter state as named view
- Pin views to sidebar for quick access
- Share views via URL parameters

### F4: Liquidity Analysis

**Depth Visualization**:
```
                    ORDERBOOK DEPTH
    ──────────────────┼──────────────────
         BIDS         │         ASKS
    ──────────────────┼──────────────────
    $12,450 ████████  │  ████ $8,200
    $8,300  █████     │  ██████ $11,400
    $4,100  ███       │  ████████ $15,600
    ──────────────────┼──────────────────
    Depth @ 1%: $24K  │  Depth @ 1%: $19K
    Depth @ 5%: $89K  │  Depth @ 5%: $72K
```

**Liquidity Score Components**:
| Factor | Weight | Description |
|--------|--------|-------------|
| Tight Spread | 30% | Spread as % of mid |
| Depth @ 1% | 25% | Liquidity within 1% of mid |
| Depth @ 5% | 20% | Liquidity within 5% of mid |
| Volume/OI Ratio | 15% | Trading activity |
| Order Count | 10% | Number of resting orders |

### F5: Alerts & Notifications

**Alert Types**:

| Alert | Trigger | Example |
|-------|---------|---------|
| Price Cross | Price crosses threshold | "BTC $150k" crosses 0.50 |
| Spread Widen | Spread exceeds threshold | Spread > 5% |
| Volume Spike | Volume exceeds N x average | 24h vol > 3x 7d avg |
| Liquidity Drop | Depth drops below threshold | Depth @ 5% < $10K |
| Resolution Soon | Time to expiry < threshold | Expires in < 24h |
| New Market | New market in category | New crypto market |

**Notification Channels**:
- In-app notification center
- Browser notifications
- Optional: Telegram integration (reuse bot's Telegram module)

### F6: Cross-Market Analysis

**Correlation Matrix**:
```
             BTC $150k  ETH $5k  Trump 2028  Fed Rate
BTC $150k      1.00      0.82      0.12       -0.34
ETH $5k        0.82      1.00      0.08       -0.41
Trump 2028     0.12      0.08      1.00        0.23
Fed Rate      -0.34     -0.41      0.23        1.00
```

**Related Markets**:
- Same event grouping (from Gamma API)
- High correlation markets
- Semantic similarity (question embeddings)
- Hedging pairs (inverse outcomes)

### F7: Historical Analysis

**Charts Available**:
- Price (candlestick or line)
- Volume bars
- Spread over time
- Liquidity score trend
- Trade flow (buy vs sell volume)

**Timeframes**: 1h, 4h, 1d, 7d, 30d, All

**Export**:
- CSV download (OHLCV data)
- JSON API access
- Configurable date ranges

---

## Technical Architecture

### Technology Stack

**Frontend**:
| Layer | Technology | Rationale |
|-------|------------|-----------|
| Framework | React 18 + TypeScript | Modern, typed, ecosystem |
| Build | Vite | Fast dev, optimized builds |
| State | TanStack Query | Server state, caching, real-time |
| Table | TanStack Table + Virtual | 1000+ rows, virtualization |
| Charts | Lightweight Charts (TradingView) | Financial charts, performant |
| Styling | Tailwind CSS | Utility-first, dark mode |
| Icons | Lucide React | Consistent, tree-shakeable |

**Backend** (new service or extend existing):
| Layer | Technology | Rationale |
|-------|------------|-----------|
| API | FastAPI | Async, fast, typed |
| Database | PostgreSQL + TimescaleDB | Relational + time-series |
| Cache | Redis | Hot data, rate limiting |
| WebSocket | FastAPI WebSocket | Real-time streaming |

### Service Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MARKET EXPLORER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   React     │◄──►│  FastAPI    │◄──►│   PostgreSQL        │  │
│  │   Frontend  │    │   Backend   │    │   + TimescaleDB     │  │
│  │             │    │             │    │                     │  │
│  │  Port 3004  │    │  Port 8080  │    │   (shared with bot) │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│         │                  │                     ▲              │
│         │                  │                     │              │
│         └──────WebSocket───┘                     │              │
│                                                  │              │
├──────────────────────────────────────────────────┼──────────────┤
│                 SHARED INGESTION LAYER           │              │
│  ┌─────────────────────────────────────────────┐ │              │
│  │  Polymarket WebSocket + REST + CLOB         │─┘              │
│  │  (existing ingestion service from bot)      │                │
│  └─────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

### API Endpoints

```
# Markets
GET  /api/markets                    # List with filters, pagination
GET  /api/markets/{condition_id}     # Full market detail
GET  /api/markets/{condition_id}/orderbook
GET  /api/markets/{condition_id}/trades
GET  /api/markets/{condition_id}/ohlcv?timeframe=1h
GET  /api/markets/search?q=bitcoin

# Categories
GET  /api/categories                 # List all categories with counts
GET  /api/categories/{slug}/markets  # Markets in category

# User Data
GET  /api/watchlists
POST /api/watchlists
PUT  /api/watchlists/{id}
DELETE /api/watchlists/{id}

GET  /api/tags
POST /api/markets/{condition_id}/tags
DELETE /api/markets/{condition_id}/tags/{tag}

GET  /api/saved-filters
POST /api/saved-filters
DELETE /api/saved-filters/{id}

# Alerts
GET  /api/alerts
POST /api/alerts
DELETE /api/alerts/{id}

# Analytics
GET  /api/analytics/correlations?markets=id1,id2,id3
GET  /api/analytics/category-stats
GET  /api/analytics/volume-leaders
GET  /api/analytics/momentum-leaders

# Streaming
WS   /api/stream                     # Real-time prices, trades
     → { type: "price", condition_id, yes_price, spread, ... }
     → { type: "trade", condition_id, side, price, size, ... }
     → { type: "alert", alert_id, condition_id, message, ... }
```

### Performance Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Initial Load | < 2s | Time to interactive |
| Table Scroll | 60fps | No jank with 1000+ rows |
| Search Latency | < 200ms | Filter application |
| Real-time Update | < 500ms | Price update to UI |
| API Response | < 100ms | P95 for list endpoints |

---

## Implementation Phases

### Phase 1: Foundation (MVP)
**Goal**: Basic market screener with core data

- [ ] Database schema (explorer_* tables)
- [ ] FastAPI backend with market list/detail endpoints
- [ ] React app with TanStack Table
- [ ] Basic filtering (category, price, volume)
- [ ] Market detail panel (static data)
- [ ] WebSocket price streaming

**Deliverable**: Functional screener showing all markets with real-time prices

### Phase 2: Analysis Tools
**Goal**: Pro trader features

- [ ] Orderbook depth visualization
- [ ] Historical OHLCV charts
- [ ] Sparklines in table
- [ ] Liquidity score computation
- [ ] Spread monitoring
- [ ] Momentum indicators

**Deliverable**: Rich market analysis capabilities

### Phase 3: Personalization
**Goal**: User workflow features

- [ ] Watchlists (create, manage, quick filter)
- [ ] Custom tags per market
- [ ] Saved filters/views
- [ ] Column customization
- [ ] View modes (compact/standard/detailed)

**Deliverable**: Personalized trading workspace

### Phase 4: Alerts & Intelligence
**Goal**: Proactive notifications

- [ ] Alert rule creation UI
- [ ] In-app notification center
- [ ] Browser notifications
- [ ] Telegram integration (optional)
- [ ] Auto-categorization ML pipeline
- [ ] Related markets suggestions
- [ ] Correlation matrix

**Deliverable**: Smart alerting and market discovery

### Phase 5: Advanced Analytics
**Goal**: Quant-grade features

- [ ] Cross-market correlation analysis
- [ ] Volume/flow analysis
- [ ] Historical data export (CSV/API)
- [ ] Custom computed columns
- [ ] Multi-market comparison charts

**Deliverable**: Research-grade analytics platform

---

## File Structure

```
polymarket-explorer/
├── README.md
├── docker-compose.yml
│
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   └── explorer/
│   │       ├── __init__.py
│   │       ├── main.py              # FastAPI app
│   │       ├── config.py
│   │       ├── api/
│   │       │   ├── markets.py
│   │       │   ├── watchlists.py
│   │       │   ├── alerts.py
│   │       │   └── analytics.py
│   │       ├── services/
│   │       │   ├── market_service.py
│   │       │   ├── categorization.py
│   │       │   └── correlation.py
│   │       ├── models/
│   │       │   └── schemas.py
│   │       └── db/
│   │           ├── database.py
│   │           └── repositories.py
│   └── tests/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── components/
│   │   │   ├── MarketTable/
│   │   │   ├── MarketDetail/
│   │   │   ├── Filters/
│   │   │   ├── Charts/
│   │   │   └── common/
│   │   ├── hooks/
│   │   │   ├── useMarkets.ts
│   │   │   ├── useWebSocket.ts
│   │   │   └── useWatchlist.ts
│   │   ├── stores/
│   │   │   └── filterStore.ts
│   │   └── types/
│   │       └── market.ts
│   └── tests/
│
└── shared/
    └── migrations/
        └── explorer_schema.sql
```

---

## Relationship to Trading Bot

### Shared Components

| Component | Sharing Strategy |
|-----------|------------------|
| **Database** | Same PostgreSQL instance, separate tables (explorer_*) |
| **Ingestion** | Reuse bot's ingestion service, add explorer-specific derived tables |
| **Market Data** | Read from bot's markets table |
| **User Auth** | Separate (explorer may be multi-user) |
| **Telegram** | Optional reuse for alerts |

### Data Flow

```
Polymarket APIs
      │
      ▼
┌─────────────────────────────────┐
│  Ingestion Service (Existing)   │
│  - WebSocket listener           │
│  - REST poller                  │
│  - CLOB fetcher                 │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│  PostgreSQL (Shared)            │
│  ├── markets (bot + explorer)   │
│  ├── orderbooks (bot + explorer)│
│  ├── trades (bot + explorer)    │
│  ├── triggers (bot only)        │
│  ├── positions (bot only)       │
│  ├── explorer_* (explorer only) │
│  └── ...                        │
└─────────────────────────────────┘
      │
      ├──────────────────┐
      ▼                  ▼
┌───────────────┐  ┌───────────────┐
│ Trading Bot   │  │ Market        │
│ Dashboard     │  │ Explorer      │
│ (Port 3000)   │  │ (Port 3004)   │
└───────────────┘  └───────────────┘
```

### Deployment Options

1. **Same Server, Different Ports**
   - Bot dashboard: localhost:3000
   - Market explorer: localhost:3004
   - Shared database, shared ingestion

2. **Separate Containers**
   - Each service in its own container
   - Shared PostgreSQL container
   - Orchestrated via docker-compose

3. **Fully Independent**
   - Separate database instance
   - Duplicate ingestion (not recommended)
   - Only if strict isolation required

---

## Open Questions for User

1. **Multi-user support?**
   - Single user (simpler) vs multi-user (needs auth)?

2. **Hosting location?**
   - Same server as trading bot?
   - Separate VPS for isolation?

3. **Alert delivery?**
   - In-app only?
   - Reuse Telegram from bot?
   - Email?

4. **Historical data retention?**
   - How far back for OHLCV? (affects storage)
   - 30 days? 1 year? Forever?

5. **API access for external tools?**
   - Need REST API for programmatic access?
   - Export formats needed?

---

## Consulted Sources

This spec was developed in consultation with:
- **Codex (GPT-5)**: Architecture recommendations, UI patterns, data modeling
- **Claude Opus 4.5**: Integration with existing bot, implementation strategy
- Polymarket API documentation
- TradingView Lightweight Charts documentation
- TanStack Table/Virtual documentation

---

## Appendix: Model Consultation Summary

### Codex (GPT-5) Key Recommendations

1. **Start standalone, read-only** to minimize risk and build trust
2. **Shared ingestion** avoids duplicate API calls and keeps data consistent
3. **TanStack Table + Virtual** for performant 1000+ row tables
4. **Rule-based categorization first**, embeddings for fuzzy matching
5. **Correlation analysis** as a key differentiator for pro traders
6. **Liquidity score** should weight tight-band depth heavily

### Architecture Principles Applied

1. **Separation of concerns**: Explorer has different users/risks than trading bot
2. **Data reuse**: Don't duplicate ingestion, share the source of truth
3. **Read-only safety**: No trading functionality = no risk of accidents
4. **Progressive enhancement**: Start simple (Phase 1), add pro features incrementally
