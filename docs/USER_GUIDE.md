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
13. [Architecture Overview](#architecture-overview)

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
# 1. Start the infrastructure (PostgreSQL + Redis)
docker-compose up -d postgres redis

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
| Redis | 7+ | Caching (optional) |
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

### Web Dashboard

The bot includes both a **Flask API** (backend) and a **React dashboard** (frontend):

| Interface | URL | Purpose |
|-----------|-----|---------|
| **React Dashboard** | `http://localhost:3000` | Modern web UI with real-time updates |
| **Flask API** | `http://localhost:5050` | REST API for data access |

#### Flask API Endpoints

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

### Dashboard Configuration

```bash
# Enable/disable dashboard (default: true)
DASHBOARD_ENABLED=true

# Host binding (default: 127.0.0.1 for security)
DASHBOARD_HOST=127.0.0.1

# Port (default: 5050)
DASHBOARD_PORT=5050
```

**Security Note**: The dashboard binds to `127.0.0.1` (localhost) by default. This means it's only accessible from the local machine.

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
curl -H "X-API-Key: your-secret-key" http://host:5050/api/positions
```

Or query parameter:
```bash
curl "http://host:5050/api/positions?api_key=your-secret-key"
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
LOG_LEVEL=INFO            # Logging verbosity
DASHBOARD_HOST=127.0.0.1  # Dashboard host (security)
DASHBOARD_API_KEY=        # Dashboard auth (optional)
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
| `http://localhost:5050/health` | Flask API health |
| `http://localhost:5050/api/positions` | Open positions |
| `https://polymarket.com` | Polymarket website |
| `https://clob.polymarket.com` | CLOB API |

---

*Last updated: December 2025*
