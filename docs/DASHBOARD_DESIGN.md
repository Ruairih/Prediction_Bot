# Polymarket Trading Dashboard - Design Document

> **A comprehensive, professional trading interface for personal use**

---

## Implementation Status

> **Last Updated: December 2025**

### Completed (v1.0)

| Feature | Status | Location |
|---------|--------|----------|
| **Flask Backend API** | ✅ Done | `src/polymarket_bot/monitoring/dashboard.py` |
| **React Frontend** | ✅ Done | `dashboard/` |
| **Overview Page** | ✅ Done | KPIs, activity stream, bot status |
| **Positions Page** | ✅ Done | Real-time positions from API |
| **Activity Page** | ✅ Done | Trigger history with filters |
| **API Authentication** | ✅ Done | Optional API key via `DASHBOARD_API_KEY` |
| **Real-time Updates** | ✅ Done | React Query polling (10-30s) |
| **Security (localhost default)** | ✅ Done | Binds to 127.0.0.1 by default |

### In Progress / TODO

| Feature | Status | Notes |
|---------|--------|-------|
| SSE real-time streaming | Partial | SSE hook invalidates queries; emits price/signal/order/position/fill events |
| Performance charts | ✅ Done | Real equity curve + PnL buckets |
| Kill switch API | ✅ Done | /api/control/kill wired to bot shutdown |
| Strategy page | ✅ Done | Live config + decision log |
| Risk page | ✅ Done | Live limits + update API |
| Pause/Resume controls | ✅ Done | /api/control/pause + /api/control/resume |
| Manual order entry UI | ✅ Done | Markets detail panel |
| Orderbook depth + slippage | ✅ Done | Tiered orderbook snapshots |
| Order blotter | ✅ Done | Portfolio page order table |
| Settings page | ✅ Done | API key + export tools |

### Architecture Decision

**Kept Flask** (not FastAPI) for the monitoring API because:
- Simple REST endpoints don't need FastAPI's async routing
- Flask runs easily in a background thread
- Less dependency overhead

---

## Executive Summary

The dashboard provides a React frontend connected to a Flask API. Focus on **explainability**, **control**, and **real-time awareness**.

---

## Professional Dashboard Replacement Spec (v2)

This section defines the replacement dashboard for professional trading use. It supersedes the v1 layout and fills in missing trader-grade controls, data, and auditability. The v2 spec assumes real data (no mocks), full explainability, and operator-grade controls.

### Goals

- Trader-grade decision support: depth, liquidity, execution quality, and risk context in every view.
- Explainability by default: every trade links to a full signal and filter trace.
- Operator control: safe manual overrides, confirmations, and audit trail.
- Real data fidelity: no hardcoded UI values; real-time updates with replay.

### Primary Users

- Operator: live monitoring, manual overrides, emergency controls.
- Analyst: performance and attribution, no trading controls.
- Debug: data health and ingestion issues.
- Viewer: read-only view for audits or spectators.

### Information Architecture (v2)

| Page | Purpose |
|------|---------|
| Mission Control | KPIs, activity tape, health, and risk snapshot |
| Portfolio | Positions, orders, exposure, exit controls |
| Markets | Universe explorer and market detail |
| Strategy | Signals, filters, model outputs, decision log |
| Performance | PnL, equity curve, drawdown, attribution |
| Risk | Limits, utilization, overrides |
| Activity | Full audit log with trace view |
| System | Ingestion, WebSocket, gotcha telemetry |
| Settings | Preferences, API keys, exports |

### Global Layout and Navigation

- Top command bar: mode, balance, health, kill switch, and global actions.
- Left nav: persistent, collapsible, with counters (open positions, breaches).
- Right inspector: contextual panel for selected market or position.
- Global search: market/question search and quick jump.

### Data Contracts (Core Entities)

Market
- condition_id, market_id, question, category, end_time, resolved
- yes_price, no_price, best_bid, best_ask, spread, mid_price
- volume_24h, liquidity, open_interest, price_change_1h, price_change_24h

Position
- position_id, condition_id, token_id, side, size
- entry_price, avg_price, current_price
- entry_time, hold_days, status, exit_plan
- unrealized_pnl, realized_pnl, pnl_percent

Order
- order_id, token_id, side, type, price, size
- status, submitted_at, filled_at, slippage_bps, fees

Signal
- signal_id, condition_id, token_id, strategy
- trigger_price, trigger_size, model_score, decision, reason
- filter_results, confidence, created_at

Risk
- max_positions, max_exposure, per_market_cap, min_reserve
- price_threshold, stop_loss, profit_target, utilization, breaches

System
- ws_connected, last_tick_age, ingestion_rate, error_rate
- gotcha_counters (G1-G6), db_latency, api_latency

### Real-Time Data Strategy

Streaming (sub-1s)
- price updates, order status, fills, bot state changes, alerts

Fast polling (5-15s)
- positions, balances, open orders, exposure, risk utilization

Slow polling (60s)
- performance aggregates, daily snapshots, attribution

Replay
- event cursor and replay window to avoid missed fills

### Page Specifications (v2)

Mission Control
- KPI grid: total PnL, daily PnL, win rate, open positions, deployed, reserve
- Live tape: signals, orders, fills, rejects with severity
- Risk snapshot: exposure meter, reserve status, breach indicators
- System pulse: WebSocket status, last tick age, error rate
- Quick actions: pause, cancel all, flatten, kill switch

Portfolio
- Positions table: sortable by PnL, age, size, strategy
- Order blotter: status, slippage, fees, and fill ratio
- Position detail drawer: entry, exits, current market, and decision link
- Manual actions: close, reduce, cancel/replace

Markets
- Universe grid: filters for category, price range, liquidity, days to resolution
- Market detail: question, resolution rules, price chart, depth, spreads
- Liquidity view: orderbook depth and slippage estimator by size

Strategy
- Decision pipeline: price update -> filters -> model -> decision
- Signal log: filter outcomes, model score, confidence, reason
- "Why this trade": trace view with each filter pass/fail

Performance
- Equity curve with drawdown overlay
- Attribution by strategy, category, holding period
- Execution quality: slippage distribution, fill rate, fees

Risk
- Limits panel with version history and confirmations
- Exposure map: per category and per market
- Overrides: pause, cooldown, per-market blocks

Activity
- Searchable audit log with trace view
- Export to CSV/JSON by date and entity

System
- Ingestion health, WS reconnects, data staleness
- Gotcha counters: stale trades filtered, orderbook mismatch, size backfill

### Manual Overrides and Controls

- Pause/Resume trading (system state toggle).
- Cancel all open orders (with confirmation).
- Flatten all positions (with confirmation).
- Manual order entry with reason and size limits.
- Manual close/partial close with price constraint.
- Per-market block and per-strategy enable/disable.

### Selected Bet (Market) Detail Data

- Market summary: question, resolution rules, end time, status.
- Pricing: best bid/ask, mid, spread, last trade, 1h/24h change.
- Liquidity: depth within 1pct/5pct/10pct, volume, open interest.
- Position context: size, avg entry, break-even, PnL, exit plan.
- Signal context: last signal, model score, filter outcomes, reason.
- Execution context: open orders, last fill, slippage, fees.

### API Requirements

REST
- GET /api/status
- GET /api/positions
- GET /api/orders
- GET /api/metrics
- GET /api/markets
- GET /api/market/{condition_id}
- GET /api/market/{condition_id}/history
- GET /api/market/{condition_id}/orderbook
- GET /api/signals
- GET /api/decisions
- GET /api/activity
- POST /api/control/pause
- POST /api/control/resume
- POST /api/control/kill
- POST /api/orders/cancel_all
- POST /api/positions/{id}/close

Streaming
- /api/stream (SSE or WS)
- events: price, signal, order, fill, position, bot_state, alert

### Security and Permissions

- Localhost binding by default, API key required when exposed.
- Read-only role and operator role separation.
- Audit log for all manual actions and limit changes.

### Non-Functional Requirements

- UI latency < 1s for streaming updates.
- Polling data freshness < 15s for positions and orders.
- Clear error states and stale data labeling.
- Auditability: every action links to stored record.

### Implementation Phases

1. Data contracts and streaming event support.
2. Mission Control and Portfolio rebuild with live data.
3. Markets and detail panel with orderbook and history.
4. Strategy explainability and decision trace.
5. Performance analytics and attribution.
6. Risk controls and manual overrides.

---

## Design Principles

1. **Explainability**: Every trade traceable to signals, thresholds, and constraints
2. **Control**: Immediate pause/override with clear dry-run vs live distinction
3. **Performance Insight**: Strategy, execution quality, and risk over time
4. **Real-time Awareness**: Live updates without information overload

---

## Page Structure & Navigation

### Layout
- **Left Sidebar**: Navigation menu (collapsible on mobile)
- **Top Status Bar**: Always visible - mode (DRY/LIVE), health, balance, kill-switch
- **Main Content**: Page-specific widgets and data

### Pages (10 total)

| Page | Purpose | Priority |
|------|---------|----------|
| **Overview** | Mission control, KPIs, live activity | v1 Must-Have |
| **Positions & Orders** | Open positions, order management | v1 Must-Have |
| **Strategy & Signals** | Decision logs, "why this trade?" | v1 Must-Have |
| **Performance** | P&L, equity curve, attribution | v1 Must-Have |
| **Markets** | Market explorer, individual detail | v1 Nice-to-Have |
| **Risk & Controls** | Limits, thresholds, parameters | v1 Must-Have |
| **Activity Log** | Searchable timeline of all events | v1 Must-Have |
| **Alerts** | Alert rules, history, notifications | v1.5 |
| **System & Ingestion** | WebSocket health, gotcha stats | v1 Nice-to-Have |
| **Settings** | Preferences, export, API keys | v1.5 |

---

## Detailed Page Specifications

### 1. Overview (Home) - Mission Control

**Purpose**: At-a-glance view of everything important

**Widgets**:

```
┌─────────────────────────────────────────────────────────────────┐
│ [DRY RUN MODE]                    Balance: $487.32  │ ⏸ PAUSE │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Total P&L│  │ Today's  │  │ Win Rate │  │ Open     │        │
│  │  $47.82  │  │  $3.20   │  │  98.5%   │  │ Positions│        │
│  │   ↑12%   │  │   ↑2.1%  │  │  67/68   │  │    3     │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                 │
│  ┌─────────────────────────────┐  ┌─────────────────────────┐  │
│  │     LIVE ACTIVITY          │  │    BOT STATUS           │  │
│  │ ─────────────────────────  │  │                         │  │
│  │ 14:32:01 BUY 2 @ $0.95    │  │  Status: ● Running      │  │
│  │   → "Will BTC hit..."      │  │  Last trade: 2m ago     │  │
│  │ 14:31:45 SIGNAL rejected   │  │  WebSocket: Connected   │  │
│  │   → Size filter (45<50)    │  │  Error rate: 0%         │  │
│  │ 14:30:12 Price update      │  │                         │  │
│  │   → Market XYZ → $0.97     │  │  [⏸ Pause] [⬛ Stop]    │  │
│  └─────────────────────────────┘  └─────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              EQUITY CURVE (Last 30 Days)                │   │
│  │    $500 ──────────────────────────────────/             │   │
│  │    $450 ─────────────────────────────/                  │   │
│  │    $400 ───────────────────────/                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**KPI Tiles**:
- Total P&L (all-time)
- Today's P&L
- Win Rate (wins/total)
- Open Positions count
- Available Balance
- Capital Deployed

**Live Activity Stream**:
- Real-time feed of trades, signals, fills
- Color-coded by type (green=buy, red=sell, gray=rejected)
- Clickable to expand details

**Intervention Panel**:
- **Pause/Resume** button
- **Cancel All Orders** button
- **Close All Positions** button
- **Toggle Dry Run** switch (requires confirmation)

---

### 2. Positions & Orders

**Purpose**: Manage current holdings and orders

**Open Positions Table**:
| Market | Entry | Current | P&L | Size | Age | Actions |
|--------|-------|---------|-----|------|-----|---------|
| Will BTC hit... | $0.95 | $0.97 | +$0.04 | 2 | 3d | [Close] |
| Will ETH... | $0.93 | $0.94 | +$0.02 | 2 | 1d | [Close] |

**Order History Table**:
| Time | Market | Side | Price | Size | Status | Slippage |
|------|--------|------|-------|------|--------|----------|
| 14:32:01 | BTC... | BUY | $0.95 | 2 | FILLED | -$0.01 |

**Position Detail Modal** (on click):
- Entry details (time, price, size, cost)
- Current market status
- P&L breakdown
- Decision log link ("Why was this entered?")
- Manual close with price input

---

### 3. Strategy & Signals - The "Why" Page

**Purpose**: Understand every trading decision

**Signal Pipeline Visualization**:
```
[Price Update] → [Hard Filters] → [Strategy Eval] → [Decision]
     ↓               ↓                 ↓               ↓
   $0.95          ✓ Pass           Score: 0.98      → BUY
                  G1: Fresh
                  G5: Valid
                  G6: Not weather
```

**Decision Log Table**:
| Time | Market | Price | Score | Decision | Reason |
|------|--------|-------|-------|----------|--------|
| 14:32:01 | BTC... | $0.95 | 0.98 | ENTRY | High score, passed all filters |
| 14:31:45 | ETH... | $0.96 | 0.95 | REJECT | Size 45 < 50 minimum |
| 14:30:12 | DOGE... | $0.94 | 0.88 | WATCH | Score below 0.97, added to watchlist |

**"Why This Trade?" Panel** (expandable):
```
Trade: BUY 2 @ $0.95 on "Will BTC hit $100k?"

✓ Price Check: $0.95 >= $0.95 threshold
✓ Size Filter: 75 shares >= 50 minimum
✓ Trade Age: 12 seconds (< 300s max)
✓ Orderbook: Best bid $0.94 within 10% of trigger
✓ No duplicate trigger for this market
✓ Model Score: 0.98 >= 0.97 entry threshold

Decision: ENTRY SIGNAL
Executed: 2024-12-21 14:32:01.234
Fill Price: $0.95 (0% slippage)
```

---

### 4. Performance Analytics

**Purpose**: Understand how the strategy performs over time

**Key Visualizations**:

1. **Equity Curve**
   - Line chart of cumulative P&L over time
   - Drawdown shaded area
   - Benchmark line (if applicable)

2. **Daily Returns Bar Chart**
   - Green/red bars for each day
   - Running average line

3. **Win Rate by Category**
   - Pie or bar chart: Crypto, Politics, Sports, etc.
   - Shows where strategy performs best

4. **P&L Attribution**
   - Entry timing edge
   - Market movement
   - Execution slippage

**Summary Stats Panel**:
```
All-Time Performance
─────────────────────────
Total Trades:      68
Winning Trades:    67 (98.5%)
Losing Trades:     1 (1.5%)
Total P&L:         $47.82
Average Win:       $0.84
Average Loss:      $-8.90
Profit Factor:     5.3
Max Drawdown:      $12.40 (2.5%)
Sharpe Ratio:      3.2
```

---

### 5. Risk & Controls

**Purpose**: Configure and monitor risk limits

**Current Limits Display**:
```
Risk Limits (v3 - Updated 2024-12-20)
─────────────────────────────────────
Max Position Size:     $2.00  ✓
Max Total Exposure:    $100.00  ✓ (Currently: $5.70)
Max Positions:         50  ✓ (Currently: 3)
Min Balance Reserve:   $100.00  ✓ (Currently: $487.32)
Price Threshold:       $0.95  ✓
Stop Loss:             $0.90
Profit Target:         $0.99
```

**Real-Time Risk Meter**:
```
Exposure: [████████░░░░░░░░░░░░] 8% of max
Balance:  [██████████████████░░] 97% healthy
```

**Parameter Editor**:
- Editable fields with validation
- Save creates new version (audit trail)
- Requires confirmation for live mode changes

**Emergency Controls**:
- **Kill Switch**: Stop all trading immediately
- **Cooldown Mode**: Pause for X minutes
- **Force Dry Run**: Switch to paper trading

---

### 6. Activity Log

**Purpose**: Complete audit trail of everything

**Searchable Log**:
```
Filter: [All Types ▼] [All Markets ▼] [Last 24h ▼] [Search...]

14:32:01.234 │ FILL    │ Order #1234 filled: BUY 2 @ $0.95
14:32:01.100 │ ORDER   │ Submitted order: BUY 2 @ $0.95 on "BTC..."
14:32:00.890 │ SIGNAL  │ Entry signal: score=0.98, market="BTC..."
14:32:00.500 │ PRICE   │ Price update: "BTC..." → $0.95
14:31:45.100 │ REJECT  │ Signal rejected: size=45 < 50 minimum
14:30:12.000 │ WATCH   │ Added to watchlist: "DOGE..." score=0.88
```

**Trace View** (click on entry):
- Shows full event chain from price update → decision
- Links to related events
- Expandable JSON for debugging

**Export**:
- CSV download
- JSON download
- Date range selection

---

## Real-Time Data Strategy

### WebSocket/SSE Stream (< 1 second latency)
- Price updates
- Order status changes
- Fill notifications
- Bot state changes (pause, error, reconnect)
- Alert triggers
- New signals

### Polling (30-60 seconds)
- Performance metrics (P&L, win rate)
- Position valuations
- Watchlist updates

### Batch/On-Demand
- Historical charts
- Activity log (paginated)
- Market metadata

---

## API Endpoints Required

### Core REST Endpoints

```
# Status & Control
GET  /api/status                    # Mode, health, version
POST /api/control/pause             # Pause trading
POST /api/control/resume            # Resume trading
POST /api/control/kill              # Emergency stop

# Positions & Orders
GET  /api/positions                 # List open positions
GET  /api/positions/{id}            # Position detail
POST /api/positions/{id}/close      # Manual close
GET  /api/orders                    # Order history
POST /api/orders/cancel_all         # Cancel all open orders

# Signals & Decisions
GET  /api/signals                   # Recent signals
GET  /api/signals/{id}              # Signal detail with reasoning
GET  /api/decisions                 # Decision log with filters

# Performance
GET  /api/performance/summary       # KPIs
GET  /api/performance/timeseries    # Equity curve data
GET  /api/performance/by-category   # P&L by market category

# Risk
GET  /api/risk/limits               # Current limits
PUT  /api/risk/limits               # Update limits
GET  /api/risk/exposure             # Current exposure

# Markets
GET  /api/markets                   # Market list with filters
GET  /api/markets/{id}              # Market detail
GET  /api/markets/{id}/prices       # Price history

# Activity
GET  /api/activity                  # Paginated activity log
GET  /api/activity/{id}/trace       # Full event trace

# Alerts
GET  /api/alerts                    # Alert history
POST /api/alerts/rules              # Create alert rule
```

### WebSocket Endpoint

```
WS /api/stream

Events:
- { type: "price", market_id, price, timestamp }
- { type: "signal", market_id, score, decision, reason }
- { type: "order", order_id, status, ... }
- { type: "fill", order_id, price, size, ... }
- { type: "position", position_id, action, ... }
- { type: "alert", severity, message, ... }
- { type: "bot_state", status, mode, ... }
```

---

## Database Schema Additions

### New Tables Needed

```sql
-- Signal/decision logging
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    trigger_price DECIMAL(10,6),
    trade_size DECIMAL(10,2),
    model_score DECIMAL(5,4),
    decision TEXT NOT NULL,  -- 'entry', 'watch', 'hold', 'reject'
    reason TEXT,
    features_json JSONB,
    CONSTRAINT fk_market FOREIGN KEY (market_id) REFERENCES ...
);

-- Performance snapshots (daily rollups)
CREATE TABLE daily_performance (
    date DATE PRIMARY KEY,
    starting_balance DECIMAL(12,2),
    ending_balance DECIMAL(12,2),
    pnl DECIMAL(12,2),
    trades_count INT,
    wins INT,
    losses INT,
    fees DECIMAL(12,2)
);

-- Risk limit versions
CREATE TABLE risk_limits_history (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    limits_json JSONB NOT NULL,
    changed_by TEXT,
    reason TEXT
);

-- Bot state log
CREATE TABLE bot_state_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    mode TEXT NOT NULL,  -- 'live', 'dry_run', 'paused', 'stopped'
    status TEXT NOT NULL,
    error_message TEXT,
    metadata_json JSONB
);
```

---

## Technology Stack Recommendation

### Frontend
- **React 18+** with TypeScript
- **Vite** for fast development
- **TailwindCSS** for styling
- **ECharts** or **Recharts** for financial charts
- **React Query** for data fetching/caching
- **React Router** for navigation

### Backend (Current Implementation)
- **Flask** for REST API (simple, thread-safe with asyncpg)
- **SSE** for real-time streaming (endpoint exists)
- **PostgreSQL** via asyncpg
- **Redis** (optional, for caching)

### Deployment
- Docker Compose with Flask API + React frontend
- Vite dev server for development (proxies to Flask)
- Production: nginx serving React static files + Flask API

---

## Implementation Phases

### Phase 1: v1.0 ✅ COMPLETE
1. ✅ Flask backend API with health, positions, metrics, triggers endpoints
2. ✅ React frontend with React Query data fetching
3. ✅ Overview page with KPIs and live activity
4. ✅ Positions page with real API data
5. ✅ Activity page with trigger history
6. ✅ Clear connection status indicator
7. ✅ Security: localhost binding by default, optional API key

### Phase 2: v1.5 (In Progress)
1. 🔄 Performance page with equity curve (placeholder exists)
2. 🔄 Risk & Controls page with parameter editor
3. 🔄 Strategy page with decision log
4. ⏳ Pause/resume/kill switch controls (needs bot control API)
5. ⏳ SSE real-time updates (endpoint exists, frontend uses polling)

### Phase 3: v2.0 (Future)
1. Markets explorer with detail view
2. Alert system with Telegram integration
3. Mobile-optimized views
4. Advanced analytics (attribution, benchmarking)
5. Manual position close/adjust functionality

---

## Mobile Considerations

For mobile, provide a simplified "Command Center" view:

```
┌─────────────────────────┐
│  [DRY RUN]    $487.32  │
├─────────────────────────┤
│  P&L Today    +$3.20   │
│  Win Rate     98.5%    │
│  Positions    3        │
├─────────────────────────┤
│  ● Bot Running         │
│  Last trade: 2m ago    │
├─────────────────────────┤
│  [⏸ PAUSE]  [⬛ STOP] │
├─────────────────────────┤
│  Recent Activity:       │
│  • BUY 2 @ $0.95       │
│  • Signal rejected      │
│  • Price update         │
└─────────────────────────┘
```

Features on mobile:
- Large touch targets for controls
- Collapsible cards
- Pull-to-refresh
- Sparkline charts (no detail)

---

## Sources & Inspiration

- [Polymarket Analytics](https://polymarketanalytics.com/) - Trader discovery, market comparison
- [Blockworks Analytics](https://blockworks.com/analytics/polymarket) - Volume/OI visualizations
- [Hashdive](https://www.hashdive.com/) - Liquidity depth, whale tracking
- [Cryptohopper Dashboard](https://docs.cryptohopper.com/docs/trading-bot/dashboard/) - Bot control patterns
- [CompanionLink UI/UX Guide](https://www.companionlink.com/blog/2025/01/crypto-bot-ui-ux-design-best-practices/amp/) - Mobile-first design

---

## Next Steps

### Completed ✅
1. ~~Consolidate dashboards into single React + Flask app~~ → Done
2. ~~Design Overview and Positions pages~~ → Implemented
3. ~~Frontend: React app with routing and layout~~ → Done
4. ~~Security: localhost binding + API key auth~~ → Done

### Remaining Work
1. **Backend**: Add decision/signal logging API for Strategy page
2. **Backend**: Add bot control API (pause/resume/kill)
3. **Frontend**: Connect SSE endpoint for real-time updates
4. **Frontend**: Implement Performance charts with Recharts
5. **Frontend**: Add manual position close/adjust modals
