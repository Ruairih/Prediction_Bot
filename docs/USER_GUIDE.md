# Polymarket Trading Bot - User Guide

> **A strategy-agnostic automated trading framework for Polymarket prediction markets**

---

## Table of Contents

1. [What Is This?](#what-is-this)
2. [Quick Start](#quick-start)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the Bot](#running-the-bot)
7. [Understanding the Strategy](#understanding-the-strategy)
8. [Monitoring & Dashboard](#monitoring--dashboard)
9. [Trading Modes](#trading-modes)
10. [Safety & Risk Management](#safety--risk-management)
11. [Database & Data](#database--data)
12. [Troubleshooting](#troubleshooting)
13. [Production Deployment & Data Continuity](#production-deployment--data-continuity)
14. [Architecture Overview](#architecture-overview)

---

## What Is This?

This is an **automated trading bot** for [Polymarket](https://polymarket.com), a prediction market platform. The bot:

- **Monitors markets in real-time** via WebSocket and REST APIs
- **Identifies trading opportunities** based on configurable strategies
- **Executes trades automatically** through the Polymarket CLOB (Central Limit Order Book)
- **Manages positions** with profit targets and stop-losses
- **Provides monitoring** via a web dashboard and Telegram alerts

### Key Principle

The framework handles all infrastructure (data ingestion, storage, order execution, monitoring) while **trading strategies are pluggable modules** that make the actual buy/sell decisions.

### Default Strategy: High Probability Yes

The included strategy targets markets where:
- The "Yes" outcome is trading at **>= 95 cents** (95% implied probability)
- A scoring model rates the outcome at **>= 97% confidence**
- The triggering trade size is **>= 50 shares** (critical for win rate)

This strategy has historically achieved a **99%+ win rate** on qualifying trades.

---

## Quick Start

```bash
# 1. Start the infrastructure (PostgreSQL)
docker-compose up -d postgres

# 2. Set up credentials (see Configuration section)
cp .env.example .env
cp polymarket_api_creds.json.example polymarket_api_creds.json
# Edit both files with your credentials

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run in dry-run mode (paper trading - no real money)
python -m polymarket_bot.main --mode all --dry-run

# 5. When ready for live trading (REAL MONEY!)
DRY_RUN=false python -m polymarket_bot.main --mode all
```

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Runtime |
| PostgreSQL | 15+ | Data storage |
| Docker | 24+ | Container runtime (recommended) |

### Required Accounts & Credentials

| Account | Purpose | How to Get |
|---------|---------|------------|
| **Polymarket Account** | Trading | [polymarket.com](https://polymarket.com) |
| **Polymarket API Keys** | CLOB access | Account Settings → API |
| **Polygon Wallet** | Transaction signing | Any Ethereum wallet |
| **USDC on Polygon** | Trading capital | Bridge from Ethereum or buy |
| **Telegram Bot** (optional) | Alerts | [@BotFather](https://t.me/BotFather) |

### Minimum Capital

- **Recommended minimum**: $500 USDC
- **Configured reserve**: $100 (never trades below this)
- **Default position size**: $20 per trade

---

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone and enter directory
git clone <repository-url>
cd polymarket-bot

# Start all services
docker-compose up -d

# Enter the dev container
docker-compose exec dev bash

# Run the bot
python -m polymarket_bot.main --mode all
```

### Option 2: Local Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install package
pip install -e ".[dev]"

# Start PostgreSQL (if not using Docker)
# Make sure PostgreSQL is running on port 5433

# Initialize database
./scripts/setup_test_db.sh

# Run the bot
python -m polymarket_bot.main --mode all
```

---

## Configuration

### Environment Variables (.env)

Copy `.env.example` to `.env` and configure:

```bash
# =============================================================================
# CRITICAL SETTINGS
# =============================================================================

# Database connection
DATABASE_URL=postgresql://predict:predict@localhost:5433/predict

# For Docker, use service name:
# DATABASE_URL=postgresql://predict:predict@postgres:5432/predict

# Path to Polymarket API credentials file
POLYMARKET_CREDS_PATH=./polymarket_api_creds.json

# Trading mode - ALWAYS START WITH TRUE!
DRY_RUN=true

# =============================================================================
# TRADING PARAMETERS
# =============================================================================

# Strategy to use
STRATEGY_NAME=high_prob_yes

# Price threshold (only trade when price >= this)
PRICE_THRESHOLD=0.95

# Position size in USDC per trade
POSITION_SIZE=20

# Maximum concurrent positions
MAX_POSITIONS=50

# Minimum trade size filter (CRITICAL for win rate)
MIN_TRADE_SIZE=50

# Maximum age of trade data in seconds (Belichick bug protection)
MAX_TRADE_AGE_SECONDS=300

# Maximum orderbook deviation from trigger price
MAX_PRICE_DEVIATION=0.10

# =============================================================================
# EXIT STRATEGY
# =============================================================================

# Minimum balance to keep in reserve (never trade below this)
MIN_BALANCE_RESERVE=100

# Profit target for long positions (exit when price reaches this)
PROFIT_TARGET=0.99

# Stop loss for long positions
STOP_LOSS=0.90

# Days before applying exit rules (short positions hold to resolution)
MIN_HOLD_DAYS=7

# =============================================================================
# POSITION SYNC (Recommended)
# =============================================================================

# Your Polymarket wallet address (enables automatic position reconciliation)
WALLET_ADDRESS=0x...

# Sync positions on startup (default: true)
SYNC_POSITIONS_ON_STARTUP=true

# Hold policy for imported positions: "new", "mature", or "actual"
STARTUP_SYNC_HOLD_POLICY=new

# =============================================================================
# ALERTS (Optional)
# =============================================================================

TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL=INFO  # DEBUG for verbose output
```

### Polymarket API Credentials (polymarket_api_creds.json)

Generate API keys at Polymarket Account Settings → API, then create:

```json
{
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "api_passphrase": "your-passphrase",
  "private_key": "0x...",
  "funder": "0x...",
  "signature_type": 2,
  "host": "https://clob.polymarket.com",
  "chain_id": 137
}
```

**SECURITY WARNING**:
- Never commit this file to git (it's in .gitignore)
- The `private_key` controls real funds on Polygon mainnet!
- Keep a backup in a secure location

---

## Running the Bot

### Basic Commands

```bash
# Full system (ingestion + trading + monitoring)
python -m polymarket_bot.main --mode all

# Ingestion only (just collect data, no trading)
python -m polymarket_bot.main --mode ingestion

# Monitor only (dashboard + health checks)
python -m polymarket_bot.main --mode monitor

# With explicit dry-run (paper trading)
python -m polymarket_bot.main --mode all --dry-run

# Live trading (REAL MONEY!)
DRY_RUN=false python -m polymarket_bot.main --mode all
```

### What Each Mode Does

| Mode | Ingestion | Trading | Monitoring | Use Case |
|------|-----------|---------|------------|----------|
| `all` | ✅ | ✅ | ✅ | Production operation |
| `ingestion` | ✅ | ❌ | ❌ | Data collection only |
| `monitor` | ❌ | ❌ | ✅ | Check existing positions |
| `engine` | ❌ | ✅ | ❌ | Process cached data |

### Startup Sequence

When you start the bot, it:

1. **Connects to database** - Verifies PostgreSQL is accessible
2. **Loads configuration** - Reads .env and credentials
3. **Initializes CLOB client** - Connects to Polymarket API (live mode only)
4. **Restores state** - Loads open orders and positions from database
5. **Starts WebSocket** - Connects to real-time price feed
6. **Begins monitoring** - Starts health checks and dashboard

### Graceful Shutdown

Press `Ctrl+C` to stop. The bot will:

1. Stop accepting new signals
2. Complete in-flight order submissions
3. Save current state to database
4. Close WebSocket and database connections

---

## Understanding the Strategy

### High Probability Yes Strategy

The default `high_prob_yes` strategy operates on this logic:

```
IF price >= 0.95 (95 cents)
   AND model_score >= 0.97 (97% confidence)
   AND trade_size >= 50 shares
THEN → BUY

IF price >= 0.95
   AND 0.90 <= model_score < 0.97
THEN → Add to WATCHLIST for re-scoring

OTHERWISE → HOLD (do nothing)
```

### Why These Thresholds?

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| **Price** | >= $0.95 | High implied probability = more likely to resolve Yes |
| **Model Score** | >= 0.97 | External scoring model confidence |
| **Trade Size** | >= 50 | **Critical**: Adds +3.5% to win rate |

### Position Management

**Short positions (held < 7 days):**
- Hold to market resolution
- Expected 99%+ win rate justifies the wait

**Long positions (held >= 7 days):**
- Exit at profit target ($0.99) - Take the guaranteed profit
- Exit at stop loss ($0.90) - Cut losses
- Continue holding between these levels

### Win Rate Expectation

With proper filters applied:
- **Without size filter**: ~95.7% win rate
- **With size filter (>= 50)**: ~99%+ win rate

The size filter is the single most important factor for profitability.

---

## Monitoring & Dashboard

### Web Dashboards

The bot includes **three dashboards** for different purposes:

| Interface | URL | Purpose |
|-----------|-----|---------|
| **Flask Dashboard** | `http://localhost:9050` | Trading metrics, starts with bot |
| **React Dashboard** | `http://localhost:3000` | Full trading UI with real-time updates |
| **Market Explorer** | `http://localhost:3004` | Market discovery UI (separate app) |
| **Ingestion Dashboard** | `http://localhost:8081` | Data flow monitoring |

**Note**: The Flask Dashboard uses port 9050 by default (not 5050) to avoid conflicts.

#### Flask API Endpoints (port 9050)

| Endpoint | Purpose |
|----------|---------|
| `/health` | Overall system health |
| `/api/status` | Bot status and mode |
| `/api/positions` | Current open positions |
| `/api/metrics` | Trading performance metrics |
| `/api/triggers` | Recent trigger events |
| `/api/watchlist` | Markets being watched |

#### Running the React Dashboard

```bash
cd dashboard
npm install
npm run dev
```

The React dashboard connects to the Flask API via Vite proxy (configured in `vite.config.ts`).

#### Running the Ingestion Dashboard

```bash
python scripts/run_ingestion.py
```

This provides real-time monitoring of data ingestion from Polymarket.

### Dashboard Configuration

```bash
# Enable/disable dashboard (default: true)
DASHBOARD_ENABLED=true

# Host binding (default: 0.0.0.0 for Docker/Tailscale access)
DASHBOARD_HOST=0.0.0.0

# Port (default: 9050 - recommended to avoid conflicts)
DASHBOARD_PORT=9050
```

**Security Note**: When `DASHBOARD_HOST=0.0.0.0`, the dashboard is accessible from other machines. Always set `DASHBOARD_API_KEY` for security when exposed on a network.

### Dashboard Security

**For Docker/container deployments** where the dashboard needs to be accessible from outside:

1. Set `DASHBOARD_HOST=0.0.0.0` to bind to all interfaces
2. **REQUIRED**: Set an API key for authentication:

```bash
export DASHBOARD_HOST=0.0.0.0
export DASHBOARD_API_KEY="your-secret-key-here"
```

Access with header:
```bash
curl -H "X-API-Key: your-secret-key" http://host:9050/api/positions
```

Or query parameter:
```bash
curl "http://host:9050/api/positions?api_key=your-secret-key"
```

**WARNING**: Never expose the dashboard on a network without setting `DASHBOARD_API_KEY`!

### Telegram Alerts

Configure in `.env`:
```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=your_chat_id
```

You'll receive alerts for:
- Trade executions
- Position closures
- Health issues (WebSocket disconnect, low balance)
- System errors

### Key Metrics to Watch

| Metric | Healthy Range | Alert If |
|--------|--------------|----------|
| **Win Rate** | > 95% | < 90% |
| **Balance** | > $100 | < $50 |
| **Open Positions** | < 50 | > MAX_POSITIONS |
| **WebSocket** | Connected | Disconnected > 5 min |

---

## Trading Modes

### Dry Run (Paper Trading)

```bash
DRY_RUN=true python -m polymarket_bot.main
```

In dry run mode:
- ✅ Ingests real market data
- ✅ Evaluates strategies
- ✅ Logs what trades WOULD execute
- ❌ Does NOT submit real orders
- ❌ Does NOT spend real money

**Note**: Telegram alerts still fire in dry-run mode (they will say "Trade Executed" even though no real trade occurred). This is by design for testing alerts.

**Always start with dry run** to verify your configuration works.

### Live Trading

```bash
DRY_RUN=false python -m polymarket_bot.main
```

In live mode:
- ✅ Submits real orders to Polymarket
- ✅ Uses real USDC from your wallet
- ✅ Tracks real positions
- ⚠️ **REAL MONEY AT RISK**

### Live Mode Requirements

The bot will **fail fast** if:
- No valid `polymarket_api_creds.json`
- Missing required credential fields
- CLOB client fails to initialize
- Balance check fails

This is intentional - better to fail immediately than trade incorrectly.

---

## Safety & Risk Management

### Built-in Protections

| Protection | What It Does |
|------------|--------------|
| **G1: Stale Data Filter** | Rejects trades older than 5 minutes |
| **G2: Duplicate Prevention** | Only triggers once per market per threshold |
| **G3: Size Backfill** | Fetches missing trade size from REST API |
| **G4: Balance Refresh** | Updates balance after every fill |
| **G5: Orderbook Verification** | Rejects if orderbook diverges > 10% from trigger |
| **G6: Word Boundary Filters** | Prevents false positives in category filters |

### Risk Limits

| Limit | Default | Configurable |
|-------|---------|--------------|
| Max price | $0.95 | `PRICE_THRESHOLD` |
| Position size | $20 | `POSITION_SIZE` |
| Max positions | 50 | `MAX_POSITIONS` |
| Reserve balance | $100 | `MIN_BALANCE_RESERVE` |
| Stop loss | $0.90 | `STOP_LOSS` |

### What Can Go Wrong

| Risk | Mitigation |
|------|------------|
| **Market resolves No** | Position is lost (rare with filters) |
| **Exchange issues** | Monitor WebSocket health |
| **API rate limits** | Built-in rate limiting |
| **Network outage** | Positions persist in DB, resume on restart |
| **Credential theft** | Never commit credentials, use env vars |

### Emergency Stop

1. Press `Ctrl+C` for graceful shutdown
2. Set `DRY_RUN=true` before restarting
3. Check `/api/positions` for open positions
4. Manually close positions on Polymarket if needed

---

## Database & Data

### Tables Overview

| Table | Purpose |
|-------|---------|
| `polymarket_trades` | Historical trade data |
| `polymarket_token_meta` | Token/market metadata |
| `stream_watchlist` | Markets being monitored |
| `positions` | Open and closed positions |
| `orders` | Order history |
| `exit_events` | Position exit records |
| `polymarket_first_triggers` | Trigger deduplication |

### Database Maintenance

```bash
# Backup
pg_dump predict > backup_$(date +%Y%m%d).sql

# Restore
psql predict < backup.sql

# Reset (DESTROYS ALL DATA)
psql predict -f seed/01_schema.sql
```

### Data Retention

The bot does not automatically clean old data. Consider:
- Archiving trades older than 90 days
- Backing up before major changes
- Monitoring disk usage

---

## Troubleshooting

### Common Issues

#### "Live trading requires Polymarket API credentials"

```
RuntimeError: Live trading requires Polymarket API credentials
```

**Fix**: Check `polymarket_api_creds.json`:
- File exists and is valid JSON
- All required fields present: `api_key`, `api_secret`, `api_passphrase`, `private_key`
- Credentials are correct (test on Polymarket website)

#### "Database connection failed"

```
asyncpg.exceptions.ConnectionDoesNotExistError
```

**Fix**:
- Ensure PostgreSQL is running: `docker-compose up -d postgres`
- Check `DATABASE_URL` in `.env`
- Verify port 5433 (local) or 5432 (Docker) is correct

#### "WebSocket disconnected"

```
WARNING: WebSocket disconnected, reconnecting...
```

**Normal behavior** - the bot auto-reconnects. If persistent:
- Check internet connection
- Polymarket may be having issues
- Restart the bot

#### "Insufficient balance"

```
InsufficientBalanceError: Required 20.00, available 15.00
```

**Fix**:
- Add more USDC to your Polygon wallet
- Reduce `POSITION_SIZE` in `.env`
- Wait for existing positions to close

#### Tests Failing

```bash
# Run all tests
pytest -v

# Check specific component
pytest src/polymarket_bot/execution/tests/ -v
```

### Logs

Set `LOG_LEVEL=DEBUG` for verbose output:

```bash
LOG_LEVEL=DEBUG python -m polymarket_bot.main
```

Log locations:
- **stdout**: All logs (captured by Docker/systemd)
- **No file logging by default**: Use Docker logs or redirect

### Getting Help

1. Check this guide thoroughly
2. Review `CLAUDE.md` files in each component directory
3. Check `docs/reference/known_gotchas.md`
4. Open an issue at the repository

---

## Production Deployment & Data Continuity

This section explains how to run the bot in production and what happens to your data and trading when the bot restarts or experiences downtime.

### Running Permanently with systemd

For production deployment, use **systemd** to keep the bot running continuously with automatic restarts.

**Installation:**

```bash
# Copy the service file
sudo cp deploy/systemd/polymarket-bot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable polymarket-bot

# Start the service
sudo systemctl start polymarket-bot

# Check status
sudo systemctl status polymarket-bot

# View logs
sudo journalctl -u polymarket-bot -f
```

**What the service provides:**
- **Automatic restart**: If the bot crashes, systemd restarts it after 10 seconds
- **Boot persistence**: The bot starts automatically when the server boots
- **Resource limits**: Memory capped at 2GB to prevent runaway usage
- **Security hardening**: Runs as unprivileged user with restricted file access
- **Graceful shutdown**: 30-second timeout for clean shutdown on stop

**Service configuration (`/etc/systemd/system/polymarket-bot.service`):**

```ini
[Unit]
Description=Polymarket Trading Bot
After=network.target postgresql.service

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/polymarket-bot
EnvironmentFile=/opt/polymarket-bot/.env
ExecStart=/opt/polymarket-bot/.venv/bin/python -m polymarket_bot.main --mode all
Restart=always
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### What Persists vs What Is Ephemeral

Understanding what data survives a restart is critical for operating the bot reliably.

| Data Type | Persists? | Where Stored | Notes |
|-----------|-----------|--------------|-------|
| **Open Positions** | ✅ Yes | PostgreSQL `positions` table | Restored on startup |
| **Open Orders** | ✅ Yes | PostgreSQL `orders` table | Restored with balance reservations |
| **Balance Reservations** | ✅ Yes | Rebuilt from orders | Prevents over-allocation |
| **Trade History** | ✅ Yes | PostgreSQL | Permanent audit trail |
| **Exit Events** | ✅ Yes | PostgreSQL `exit_events` | Permanent audit trail |
| **Trigger History** | ✅ Yes | PostgreSQL `polymarket_first_triggers` | Prevents duplicate triggers |
| **Price Updates** | ❌ No | Memory only | Live WebSocket data |
| **Watchlist Scoring** | ❌ No | Memory only | Rebuilt from fresh data |

### State Recovery on Restart

When the bot starts (or restarts), it automatically recovers state:

```
Startup Sequence:
1. Connect to PostgreSQL
2. Refresh balance from Polymarket CLOB API
3. Load open orders from database
   └─> Restore balance reservations for each order
   └─> Sync order status with CLOB (detect fills while offline)
4. Load open positions from database
5. **Position Sync** (if WALLET_ADDRESS configured):
   └─> Verify positions still exist on Polymarket
   └─> Close positions from resolved markets
   └─> Import externally created positions
   └─> Update sizes for partial external sells
6. Start WebSocket connection
7. Begin processing live events
```

**The bot logs this on startup:**
```
INFO: Startup position sync: reconciling with Polymarket...
INFO: Startup position sync complete: 0 imported, 1 updated, 2 closed
INFO: Loaded state: 10 positions, 3 orders
```

### Automatic Position Sync

**New in this version:** The bot now automatically reconciles positions with Polymarket on every startup. This prevents several critical bugs:

| Without Position Sync | With Position Sync |
|----------------------|-------------------|
| Ghost positions from resolved markets | Detected and closed |
| Externally sold positions still tracked | Detected and removed |
| Externally created positions invisible | Imported and monitored |
| Wrong position sizes after partial sells | Updated to actual |

**Configuration:**

```bash
# Required: Your Polymarket wallet address
WALLET_ADDRESS=0x...

# Enable/disable startup sync (default: true)
SYNC_POSITIONS_ON_STARTUP=true

# How to treat newly imported positions:
# - "new": 7-day hold period starts fresh (default, safe)
# - "mature": Exit logic applies immediately
# - "actual": Use actual trade timestamps (slowest)
STARTUP_SYNC_HOLD_POLICY=new
```

**If Polymarket API is down at startup:**
- The bot logs a warning and continues with database state
- Background sync will eventually reconcile
- No startup failure - trading continues with stale data

### Data Ingestion: Live-Only, No Backfill

**Critical to understand:** The bot operates on **live data only**. It does NOT backfill historical data.

**How data ingestion works:**
1. **WebSocket connects** to Polymarket's real-time price feed
2. **Price updates stream in** as they happen on the exchange
3. **Each update is evaluated** by the strategy
4. **Trades execute** if the strategy signals BUY

**What this means:**
- The bot only sees trades that occur **while it is running**
- If a 95¢ trade happens while the bot is offline, it will **NOT** be captured
- There is **no way to replay** missed trading opportunities
- The WebSocket has no "catch up" or historical data feature

### What Happens During Downtime

**Scenario:** Bot is offline from 2:00 AM to 2:30 AM

| Event | Result |
|-------|--------|
| Trade at $0.96 happens at 2:15 AM | **MISSED** - Bot was offline, opportunity lost |
| Your open position hits profit target | **NOT EXITED** - Exit monitoring was offline |
| Order fills while bot is offline | **DETECTED** - CLOB status synced on restart |
| Market resolves while offline | **HANDLED** - Position sync detects closed positions |

**Key points:**
- **Missed opportunities are NOT recoverable** - The Polymarket WebSocket does not provide historical data
- **Open orders may fill** - CLOB executes orders even when bot is offline; status synced on restart
- **Exit monitoring pauses** - Positions won't exit at targets during downtime
- **Market resolutions are detected** - Position sync handles externally closed positions

### Maximizing Uptime

To minimize missed opportunities:

1. **Use systemd** for automatic restart on crash
2. **Monitor with Telegram alerts** for downtime notifications
3. **Set up health monitoring** (external ping to `/health` endpoint)
4. **Use a reliable server** with good network connectivity
5. **Keep the database local** to avoid network latency/failures

**Example uptime monitoring script:**

```bash
#!/bin/bash
# Add to cron: */5 * * * * /opt/scripts/check_bot.sh

if ! curl -sf http://localhost:9050/health > /dev/null; then
    # Bot is down - alert via Telegram
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
        -d "chat_id=$CHAT_ID" \
        -d "text=⚠️ Polymarket bot is DOWN!"
fi
```

### Docker vs Systemd

| Approach | Pros | Cons |
|----------|------|------|
| **Docker** | Isolated environment, easy updates | Extra layer of complexity |
| **systemd** | Native Linux, lower overhead | Requires system Python setup |
| **Docker + systemd** | Best of both (Docker for app, systemd for restart) | Most complex setup |

**Recommendation:** For production, use the **systemd service files** in `deploy/systemd/`. They're pre-configured with security hardening and resource limits.

### Position Sync After Extended Downtime

If the bot was offline for an extended period, run a position sync to reconcile:

```bash
# Dry run to see what changed
python -m polymarket_bot.sync_positions \
    --wallet-address 0xYourWallet \
    --dry-run

# Actually sync
python -m polymarket_bot.sync_positions \
    --wallet-address 0xYourWallet
```

This will:
- Detect positions closed externally (market resolution, manual sale)
- Import new positions created externally
- Update position sizes that changed

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MONITORING                               │
│            Health checks, metrics, alerts, dashboard             │
└─────────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  INGESTION  │──────▶│    CORE     │──────▶│  EXECUTION  │
│             │       │             │       │             │
│ WebSocket   │       │  Trading    │       │ Order       │
│ REST APIs   │       │  Engine     │       │ Management  │
│ Data sync   │       │  Strategy   │       │ Positions   │
└─────────────┘       └─────────────┘       └─────────────┘
        │                    │                      │
        └────────────────────┼──────────────────────┘
                             ▼
                    ┌─────────────┐
                    │   STORAGE   │
                    │ PostgreSQL  │
                    └─────────────┘
```

### Data Flow

1. **INGESTION** receives price update from Polymarket WebSocket
2. **CORE** builds context and invokes **STRATEGY**
3. **STRATEGY** evaluates and returns signal (BUY/HOLD/WATCH)
4. **CORE** routes signal to **EXECUTION**
5. **EXECUTION** submits order to Polymarket CLOB
6. **STORAGE** persists everything
7. **MONITORING** observes and alerts

### Component Responsibilities

| Component | Does | Does NOT |
|-----------|------|----------|
| **Storage** | PostgreSQL, repositories | Call APIs |
| **Ingestion** | Fetch from Polymarket, normalize | Make decisions |
| **Strategies** | Evaluate markets, emit signals | Touch DB, call APIs |
| **Core** | Orchestrate data flow | Contain trading logic |
| **Execution** | Submit orders, track positions | Decide when to trade |
| **Monitoring** | Health checks, alerts | Affect trading |

---

## Quick Reference

### Start Commands

```bash
# Paper trading (safe)
python -m polymarket_bot.main --mode all

# Live trading (REAL MONEY!)
DRY_RUN=false python -m polymarket_bot.main --mode all

# Data ingestion only
python -m polymarket_bot.main --mode ingestion
```

### Key Environment Variables

```bash
DRY_RUN=true              # Paper trading mode
PRICE_THRESHOLD=0.95      # Minimum price to trade
POSITION_SIZE=20          # USD per trade
MAX_POSITIONS=50          # Maximum concurrent positions
WALLET_ADDRESS=0x...      # Your wallet (required for position sync)
SYNC_POSITIONS_ON_STARTUP=true  # Reconcile on startup
LOG_LEVEL=INFO            # Logging verbosity
DASHBOARD_HOST=0.0.0.0    # Dashboard host (0.0.0.0 for Docker/Tailscale)
DASHBOARD_PORT=9050       # Dashboard port (9050 recommended)
DASHBOARD_API_KEY=        # Dashboard auth (REQUIRED if exposed)
```

### Test Commands

```bash
pytest                                    # All tests
pytest -v                                 # Verbose
pytest --cov=src/polymarket_bot           # With coverage
./scripts/run_tests.sh                    # Convenience script
```

### Useful URLs

| URL | Purpose |
|-----|---------|
| `http://localhost:3000` | React dashboard (dev) |
| `http://localhost:9050/health` | Flask API health |
| `http://localhost:9050/api/positions` | Open positions |
| `http://localhost:8081` | Ingestion dashboard |
| `https://polymarket.com` | Polymarket website |
| `https://clob.polymarket.com` | CLOB API |

---

*Last updated: December 2025*
