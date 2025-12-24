# Polymarket Trading Bot

## What This Is

A **strategy-agnostic trading bot framework** for Polymarket prediction markets. The framework handles all infrastructure (data ingestion, storage, order execution, monitoring) while trading strategies are pluggable modules that make decisions.

**Key principle:** The framework provides data and executes decisions. Strategies only decide.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MONITORING                               │
│            Health checks, metrics, alerts, dashboard             │
│                    (observes all components)                     │
└─────────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│  INGESTION  │──────▶│    CORE     │──────▶│  EXECUTION  │
│             │       │             │       │             │
│ WebSocket   │       │  Trading    │       │ Order       │
│ REST APIs   │       │  Engine     │       │ Management  │
│ Data sync   │       │  Orchestr.  │       │ Positions   │
└─────────────┘       └─────────────┘       └─────────────┘
        │                    │                      │
        │             ┌──────┴──────┐               │
        │             │ STRATEGIES  │               │
        │             │             │               │
        │             │ Pure logic  │               │
        │             │ No I/O      │               │
        │             │ Pluggable   │               │
        │             └─────────────┘               │
        │                    │                      │
        └────────────────────┼──────────────────────┘
                             ▼
                    ┌─────────────┐
                    │   STORAGE   │
                    │             │
                    │  PostgreSQL │
                    │  Repos      │
                    │  Migrations │
                    └─────────────┘
```

### Data Flow

```
1. INGESTION receives price update from Polymarket WebSocket
2. CORE builds context and invokes STRATEGY
3. STRATEGY evaluates and returns signal (BUY/SELL/WATCH/IGNORE)
4. CORE routes signal to EXECUTION
5. EXECUTION submits order to Polymarket CLOB
6. STORAGE persists everything (triggers, orders, positions)
7. MONITORING observes and alerts on anomalies
```

---

## Component Responsibilities

| Component | Purpose | Does | Does NOT |
|-----------|---------|------|----------|
| **storage** | Data persistence | PostgreSQL, repositories, migrations | Call APIs, make decisions |
| **ingestion** | Data retrieval | Fetch from Polymarket, normalize | Store data, make decisions |
| **strategies** | Decision logic | Evaluate markets, emit signals | Touch DB, call APIs, maintain state |
| **core** | Orchestration | Route data→strategy→execution | Contain trading logic |
| **execution** | Order management | Submit orders, track positions | Decide when to trade |
| **monitoring** | Observability | Health checks, metrics, alerts | Affect trading behavior |

---

## Pluggable Strategy Architecture

The bot is **strategy-agnostic**. Strategies are loaded from a registry at startup:

```python
# Set strategy via environment variable
STRATEGY_NAME=high_prob_yes python -m polymarket_bot.main

# Or implement your own strategy
from polymarket_bot.strategies import Strategy, get_default_registry

class MyStrategy(Strategy):
    @property
    def name(self) -> str:
        return "my_strategy"

    def evaluate(self, context: StrategyContext) -> Signal:
        # Your trading logic here
        ...

# Register and use
registry = get_default_registry()
registry.register(MyStrategy())
```

### Live Mode Validation

When running in live mode (`DRY_RUN=false`), the bot **fails fast** if:
- Polymarket API credentials are missing
- `py-clob-client` is not installed
- CLOB client initialization fails

This prevents the bot from silently running with mock behavior while thinking it's trading live.

```python
# Live mode requires:
# 1. Valid polymarket_api_creds.json
# 2. py-clob-client installed: pip install py-clob-client
# 3. CLOB client successfully connects

# Dry run mode (default) works without CLOB client
DRY_RUN=true python -m polymarket_bot.main  # OK, no CLOB needed
DRY_RUN=false python -m polymarket_bot.main  # Requires working CLOB
```

---

## Dependency Graph & Parallel Build Phases

```
PHASE 1 ─────────────────────────────────────────────────────────────
│
│  ┌─────────────┐
│  │   STORAGE   │  ← Build first. Everyone depends on this.
│  └─────────────┘
│
PHASE 2 ─────────────────────────────────────────────────────────────
│
│  ┌─────────────┐     ┌─────────────┐
│  │  INGESTION  │     │ STRATEGIES  │  ← Can build in PARALLEL
│  └─────────────┘     └─────────────┘    (both only need storage types)
│
PHASE 3 ─────────────────────────────────────────────────────────────
│
│  ┌─────────────┐
│  │    CORE     │  ← Needs ingestion + strategies + storage
│  └─────────────┘
│
PHASE 4 ─────────────────────────────────────────────────────────────
│
│  ┌─────────────┐     ┌─────────────┐
│  │  EXECUTION  │     │ MONITORING  │  ← Can build in PARALLEL
│  └─────────────┘     └─────────────┘
│
```

### Parallelization Rules

1. **Phase 1 must complete** before any other phase starts
2. **Phase 2 components are independent** - ingestion and strategies can be built simultaneously
3. **Phase 3 waits** for Phase 2 completion
4. **Phase 4 components are independent** - execution and monitoring can be built simultaneously

### Interface Contracts

For parallel work to succeed, respect these boundaries:

- Each component **owns its directory exclusively**
- Components communicate through **public interfaces in `__init__.py`**
- **Never import from another component's internal modules**
- If you need something that doesn't exist yet, **create a stub/mock and document the need**

---

## Cross-Cutting Gotchas

These bugs affected production. **Every agent must understand these**, regardless of which component they're building.

### G1: Stale Trade Data ("Belichick Bug")

| | |
|---|---|
| **What** | Polymarket's "recent trades" API returns trades that may be **months old** for low-volume markets |
| **Impact** | Executed at 95¢ based on 2-month-old trade when actual market was 5¢ |
| **Affects** | ingestion, core, strategies |
| **Rule** | **ALWAYS filter trades by timestamp.** Default max age: 300 seconds |

```python
# WRONG - trusts API's definition of "recent"
trades = await client.get_trades(condition_id)

# RIGHT - explicitly filter by age
trades = await client.get_recent_trades(condition_id, max_age_seconds=300)
```

### G2: Duplicate Token IDs

| | |
|---|---|
| **What** | Multiple `token_id`s can map to the same market (`condition_id`) |
| **Impact** | Traded same market multiple times, thinking they were different |
| **Affects** | storage, core, strategies |
| **Rule** | **Use `should_trigger()` which checks both token_id AND condition_id** |

```python
# WRONG - only checks token_id
if not triggers.has_triggered(token_id, threshold):
    execute()

# RIGHT - use should_trigger() for combined check
if triggers.should_trigger(token_id, condition_id, threshold):
    execute()
    triggers.create(trigger)
```

### G3: WebSocket Missing Trade Size

| | |
|---|---|
| **What** | WebSocket price updates don't include trade size |
| **Impact** | Strategies that need size (for model features) got None |
| **Affects** | ingestion, core, strategies |
| **Rule** | **If you need size, fetch from REST API separately** |

```python
# WebSocket gives you this (NO SIZE):
{"asset_id": "0x...", "price": "0.95"}

# Must fetch size separately:
size = await client.get_trade_size_at_price(condition_id, price)
```

### G4: CLOB Balance Cache Staleness

| | |
|---|---|
| **What** | Polymarket's balance API caches aggressively |
| **Impact** | Showed $1000 available when actual balance was $50 |
| **Affects** | execution |
| **Rule** | **Refresh balance after every order fill, not just on startup** |

```python
# After order fills:
order_manager.sync_order_status(order_id)
balance_manager.refresh()  # MUST do this
```

### G5: Orderbook vs Trade Price Divergence

| | |
|---|---|
| **What** | Spike trades can show 95¢ while orderbook is actually at 5¢ |
| **Impact** | Would have bought at 95¢ in a 5¢ market |
| **Affects** | core, execution |
| **Rule** | **ALWAYS verify orderbook price before executing. Reject if >10¢ deviation** |

```python
# Before executing:
is_valid, actual_price, reason = await client.verify_price(
    token_id,
    expected_price=trigger_price,
    max_deviation=0.10
)
if not is_valid:
    reject(f"Orderbook mismatch: {reason}")
```

### G6: Rainbow Bug (Weather Filter)

| | |
|---|---|
| **What** | "Rainbow Six Siege" esports market was incorrectly blocked as a weather market because it contained "rain" |
| **Impact** | Legitimate trading opportunities missed |
| **Affects** | strategies |
| **Rule** | **Use word boundaries in regex matching for category filters** |

```python
# WRONG - substring match
if "rain" in question.lower():
    block_as_weather()

# RIGHT - word boundary match
import re
weather_pattern = r'\b(rain|snow|hurricane|storm|weather)\b'
if re.search(weather_pattern, question, re.IGNORECASE):
    block_as_weather()
```

### G7: Timezone-Aware Datetime in PostgreSQL

| | |
|---|---|
| **What** | `asyncpg` errors when inserting timezone-aware datetimes into `timestamp without time zone` columns |
| **Impact** | Database inserts failed for market data |
| **Affects** | ingestion, storage |
| **Rule** | **Convert to naive UTC before inserting into PostgreSQL** |

```python
def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
```

### G8: Startup Hang (Market Fetch Blocking)

| | |
|---|---|
| **What** | Bot appeared frozen during startup for 30+ seconds while fetching all markets |
| **Impact** | Users thought the bot crashed; CI/CD timeouts |
| **Affects** | ingestion |
| **Rule** | **Cap startup fetch, continue in background** |

```python
# IngestionConfig has startup_market_limit (default: 2000)
# Background task fetches remaining markets after startup
# Startup: ~2s instead of 30+s
```

---

## Testing Philosophy

### Principles

1. **Tests live with code:** `component/tests/`, not a separate tree
2. **Test behavior, not implementation:** What it does, not how
3. **Every gotcha has a regression test:** The bugs above must have tests
4. **Mock external APIs:** Never hit real Polymarket in tests
5. **Fast by default:** Integration tests marked separately

### Coverage Targets

| Component | Target | Rationale |
|-----------|--------|-----------|
| storage | >95% | Foundation; bugs cascade everywhere |
| execution | >95% | Handles real money |
| core | >90% | Complex orchestration |
| strategies | >90% | Trading decisions |
| ingestion | >85% | External API mocking is hard |
| monitoring | >80% | Less critical path |

### Test Commands

```bash
# All tests
pytest

# One component
pytest src/polymarket_bot/storage/tests/

# With coverage
pytest --cov=src/polymarket_bot --cov-report=html

# Fast tests only (no network/integration)
pytest -m "not integration"

# Specific test
pytest src/polymarket_bot/storage/tests/test_database.py::TestTransactions -v
```

---

## For Agents Working on This Codebase

### Before You Start

1. **Read this entire file** (root CLAUDE.md)
2. **Read your component's CLAUDE.md** at `src/polymarket_bot/{component}/CLAUDE.md`
3. **Check gotchas** in `docs/reference/known_gotchas.md` for your component
4. **Run existing tests** to make sure they pass:
   ```bash
   pytest src/polymarket_bot/{your_component}/tests/
   ```

### While Working

| Do | Don't |
|----|-------|
| Own your component's directory completely | Modify other components' code |
| Define clean interfaces in `__init__.py` | Import from other components' internals |
| Write tests alongside implementation | Leave testing for later |
| Document new gotchas you discover | Assume someone else will document |
| Create stubs for missing dependencies | Block waiting for other components |

### When You Need Something That Doesn't Exist

If another component hasn't built what you need:

1. **Define the interface you need** (what you'd import)
2. **Create a mock/stub** in your tests
3. **Document the dependency** in your component's CLAUDE.md
4. **Continue working** - don't block

Example:
```python
# In your test conftest.py:
@pytest.fixture
def mock_trigger_repo():
    """Stub until storage layer implements TriggerRepository."""
    repo = MagicMock()
    repo.has_triggered.return_value = False
    repo.has_condition_triggered.return_value = False
    return repo
```

### Finishing Up

Before considering your component complete:

- [ ] All your tests pass: `pytest src/polymarket_bot/{component}/tests/`
- [ ] No regressions in full suite: `pytest`
- [ ] Coverage meets target: `pytest --cov=src/polymarket_bot/{component}`
- [ ] Public interface documented in `__init__.py`
- [ ] Component CLAUDE.md updated with any new gotchas

---

## Project Commands

```bash
# Environment
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Testing
pytest                                    # All tests
pytest -v                                 # Verbose
pytest -x                                 # Stop on first failure
pytest --cov=src/polymarket_bot           # With coverage
pytest -m "not integration"               # Unit tests only
pytest tests/integration/                 # Integration tests only

# Convenience scripts
./scripts/run_tests.sh                    # All tests
./scripts/run_tests.sh unit               # Unit tests only
./scripts/run_tests.sh coverage           # With coverage report
./scripts/setup_test_db.sh                # Initialize test database

# Code quality
ruff check src/                           # Linting
ruff format src/                          # Formatting
mypy src/polymarket_bot/                  # Type checking

# Running (after implementation)
python -m polymarket_bot.main             # Main bot
python -m polymarket_bot.main --dry-run   # Paper trading mode
python -m polymarket_bot.monitoring       # Dashboard only
```

---

## File Structure

```
polymarket_bot/
├── CLAUDE.md                 ← You are here (project overview)
├── pyproject.toml            ← Package configuration
├── docs/
│   └── reference/            ← Historical context & guidance
│       ├── README.md
│       ├── known_gotchas.md
│       ├── architecture_decisions.md
│       └── past_iterations/
├── src/
│   └── polymarket_bot/
│       ├── __init__.py
│       ├── storage/          ← PHASE 1
│       │   ├── CLAUDE.md
│       │   ├── __init__.py
│       │   └── tests/
│       ├── ingestion/        ← PHASE 2 (parallel)
│       │   ├── CLAUDE.md
│       │   ├── __init__.py
│       │   └── tests/
│       ├── strategies/       ← PHASE 2 (parallel)
│       │   ├── CLAUDE.md
│       │   ├── __init__.py
│       │   └── tests/
│       ├── core/             ← PHASE 3
│       │   ├── CLAUDE.md
│       │   ├── __init__.py
│       │   └── tests/
│       ├── execution/        ← PHASE 4 (parallel)
│       │   ├── CLAUDE.md
│       │   ├── __init__.py
│       │   └── tests/
│       └── monitoring/       ← PHASE 4 (parallel)
│           ├── CLAUDE.md
│           ├── __init__.py
│           └── tests/
└── tests/                    ← Integration tests
    └── conftest.py
```

---

## Reference Documentation

The `docs/reference/` folder contains **historical context and guidance**.

- **It is NOT prescriptive** - don't copy implementations verbatim
- **It IS informative** - understand why decisions were made
- **When in doubt**, trust: Code > Component CLAUDE.md > Root CLAUDE.md > Reference docs

See `docs/reference/README.md` for how to use that folder.

---

## Credentials & Secrets

### Required Credentials

| Credential | File/Variable | Purpose |
|------------|---------------|---------|
| Database URL | `DATABASE_URL` env var | PostgreSQL connection |
| Polymarket API | `polymarket_api_creds.json` | CLOB API access |
| Polygon Wallet | `PRIVATE_KEY` env var | Sign transactions |
| Telegram Bot | `TELEGRAM_BOT_TOKEN` env var | Alert notifications |
| Telegram Chat | `TELEGRAM_CHAT_ID` env var | Where to send alerts |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `DRY_RUN` | `true` | Paper trading mode (no real orders) |
| `STRATEGY_NAME` | `high_prob_yes` | Strategy to use from registry |
| `PRICE_THRESHOLD` | `0.95` | Price threshold for triggers |
| `POSITION_SIZE` | `20` | Position size in dollars |
| `MAX_POSITIONS` | `50` | Maximum concurrent positions |
| `MIN_BALANCE_RESERVE` | `100` | Minimum balance to keep reserved |
| `PROFIT_TARGET` | `0.99` | Exit price for long positions |
| `STOP_LOSS` | `0.90` | Stop loss exit price |
| `MIN_HOLD_DAYS` | `7` | Days before applying exit strategy |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DASHBOARD_ENABLED` | `true` | Enable/disable monitoring dashboard |
| `DASHBOARD_HOST` | `0.0.0.0` | Dashboard bind address (`0.0.0.0` for Docker/Tailscale - see G11) |
| `DASHBOARD_PORT` | `9050` | Dashboard port (use a port FREE on your host - see G11) |
| `DASHBOARD_API_KEY` | (optional) | API key for dashboard authentication |

**Note on Dashboards (G11/G11b/G11c):** Three dashboards available:
1. **Flask Dashboard** (port 9050) - Basic trading metrics, starts with bot
2. **React Dashboard** (port 3000) - Full trading UI: `cd dashboard && npm run dev`
3. **Ingestion Dashboard** (port 8081) - Data flow monitoring: `python scripts/run_ingestion.py`

For Tailscale access from Docker, run on HOST:
```bash
sudo tailscale serve --bg --tcp 9050 tcp://localhost:9050  # Flask trading
sudo tailscale serve --bg --tcp 3000 tcp://localhost:3000  # React trading
sudo tailscale serve --bg --tcp 8081 tcp://localhost:8081  # Ingestion
```
See `docs/reference/known_gotchas.md#g11b` and `#g11c` for details.

### Setup Instructions

1. **Copy example files:**
   ```bash
   cp .env.example .env
   cp polymarket_api_creds.json.example polymarket_api_creds.json
   ```

2. **Generate Polymarket API credentials:**
   - Go to https://polymarket.com/
   - Navigate to account settings → API
   - Generate new API keys
   - Save to `polymarket_api_creds.json`

3. **Configure Telegram alerts:**
   - Create a bot via @BotFather on Telegram
   - Get your chat ID via @userinfobot
   - Add tokens to `.env`

4. **CRITICAL: Never commit secrets!**
   - `.gitignore` blocks `.env` and `*_creds.json`
   - Always use `.example` files for templates

### Credential File Format

**polymarket_api_creds.json:**
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

---

## Error Handling Strategy

### Principle: Fail Fast, Log Everything

- External API errors: Catch, log, alert, continue
- Database errors: Catch, log, rollback transaction
- Strategy errors: Catch, log, skip to next market
- **Never silently swallow exceptions**

### Error Categories

| Category | Action | Alert? |
|----------|--------|--------|
| Database connection loss | Stop processing, reconnect | YES |
| WebSocket disconnect > 5 min | Stop processing, reconnect | YES |
| Balance < $10 | Stop trading | YES |
| Single market fetch failure | Log, skip market | NO |
| Strategy evaluation error | Log, skip market | NO |
| Single order submission failure | Log, retry once | YES |
| Orderbook divergence (G5) | Log, reject trade | NO |
| Stale trade data (G1) | Filter out silently | NO |

### Exception Hierarchy

```python
# Base exception for all bot errors
class PolymarketBotError(Exception):
    pass

# Recoverable errors (log and continue)
class RecoverableError(PolymarketBotError):
    pass

# Fatal errors (stop processing)
class FatalError(PolymarketBotError):
    pass

# Specific errors
class InsufficientBalanceError(FatalError):
    pass

class PriceTooHighError(RecoverableError):
    pass

class OrderbookDivergenceError(RecoverableError):
    pass
```

---

## Concurrency Model

### Async Architecture

All I/O is async using `asyncio`:
- Use `asyncio.gather()` for parallel fetches
- Use database transactions for atomic operations
- WebSocket and HTTP share the same event loop

### Resource Limits

| Resource | Limit | Rationale |
|----------|-------|-----------|
| HTTP concurrent requests | 10 | Respect API rate limits |
| Database pool connections | 5-20 | Balance throughput vs. resources |
| WebSocket subscriptions | 100 markets | API limit |
| Order submission | Sequential | Prevent race conditions |

### Semaphore Pattern

```python
# Limit concurrent HTTP requests
http_semaphore = asyncio.Semaphore(10)

async def fetch_with_limit(url):
    async with http_semaphore:
        return await client.get(url)

# Parallel fetches with limit
results = await asyncio.gather(*[
    fetch_with_limit(url) for url in urls
])
```

### Data Flow Concurrency

```
WebSocket (continuous) ─┐
                        ├─> Event Queue ─> Processing (sequential)
REST Polling (10s)    ─┘
                                          │
                                          v
                                   Strategy Eval (fast, sync)
                                          │
                                          v
                                   Order Submission (sequential)
```

---

## Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Trigger-to-execution | <500ms | >2s |
| Strategy evaluation | <50ms | >200ms |
| Database query | <10ms | >100ms |
| WebSocket latency | <100ms | >500ms |
| Health check cycle | <5s | >10s |

### Monitoring

Track these metrics via the monitoring dashboard:
- P50, P95, P99 latencies for each operation
- Error rates by category
- Throughput (events/second, trades/hour)

---

## Hard Filters (Pre-Strategy)

These filters run BEFORE strategy evaluation. If rejected, strategy is never called.

| Filter | Rule | Gotcha | Reason |
|--------|------|--------|--------|
| **Weather** | Word-boundary regex match | G6 | "Rainbow Six" false positive |
| **Time-to-end** | > 6 hours remaining | - | Insufficient resolution time |
| **Trade size** | >= 50 shares | - | +3.5% win rate impact |
| **Trade age** | < 300 seconds | G1 | Belichick bug prevention |
| **Orderbook divergence** | < 10¢ from trigger | G5 | Spike trade protection |
| **Category blocklist** | Not in blocklist | - | Exclude volatile categories |
| **Duplicate trigger** | First trigger only | G2 | Prevent duplicate trades |

### Filter Implementation Order

```python
def apply_hard_filters(context: StrategyContext) -> tuple[bool, str]:
    """Returns (should_reject, reason)."""

    # 1. Trade age (G1 - Belichick)
    if context.trade_age_seconds > 300:
        return True, "Trade too old (G1)"

    # 2. Weather filter (G6 - Rainbow)
    if is_weather_market(context.question):
        return True, "Weather market (G6)"

    # 3. Time to end
    if context.time_to_end_hours < 6:
        return True, "Expiring too soon"

    # 4. Trade size
    if context.trade_size and context.trade_size < 50:
        return True, "Trade size too small"

    # 5. Category blocklist
    if context.category in BLOCKED_CATEGORIES:
        return True, f"Blocked category: {context.category}"

    return False, ""
```

---

## Database Migration Strategy

### Current Approach

Schema uses raw SQL files in `seed/`:
- Files are numbered sequentially: `01_schema.sql`, `02_add_column.sql`
- Each file is idempotent (`CREATE TABLE IF NOT EXISTS`)
- Applied automatically on database init

### Adding Migrations

1. Create new numbered SQL file:
   ```bash
   touch seed/02_add_new_table.sql
   ```

2. Write idempotent SQL:
   ```sql
   -- seed/02_add_new_table.sql
   CREATE TABLE IF NOT EXISTS new_table (
       id SERIAL PRIMARY KEY,
       ...
   );
   ```

3. Test on backup first:
   ```bash
   pg_dump predict > backup.sql
   psql predict < seed/02_add_new_table.sql
   ```

### Rollback

Write reversal scripts manually:
```sql
-- rollback/02_remove_new_table.sql
DROP TABLE IF EXISTS new_table;
```

### Future: Alembic

Consider migrating to Alembic when:
- Team grows beyond 2-3 people
- Schema changes become frequent
- Need automatic rollback support

---

## Operational Guidelines

### State Rehydration on Startup

When the bot starts, it automatically restores state from the database:

1. **Open Positions**: Loaded from `positions` table
2. **Open Orders**: Loaded from `orders` table (pending, live, partial statuses)
3. **Balance Reservations**: Restored for open orders to prevent over-allocation

```python
# This happens automatically in ExecutionService.load_state()
await execution_service.load_state()
# - Refreshes balance from CLOB
# - Loads open orders and restores reservations
# - Loads open positions
```

This ensures the bot can safely restart without losing track of:
- Pending orders that may fill
- Positions that need exit monitoring
- Balance that's reserved for open orders

### Logging Configuration

Logs go to stdout/stderr for container compatibility:

```python
import logging

# Configure via LOG_LEVEL env var (DEBUG/INFO/WARNING/ERROR)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

### Log Levels

| Level | Use For |
|-------|---------|
| DEBUG | Detailed data flow, API responses |
| INFO | Trade executions, position changes, health status |
| WARNING | Recoverable errors, stale data filtered |
| ERROR | Failed operations that need attention |

### Running as Service

For production, run under systemd or supervisor:

```ini
# /etc/systemd/system/polymarket-bot.service
[Unit]
Description=Polymarket Trading Bot
After=network.target postgresql.service

[Service]
Type=simple
User=trading
WorkingDirectory=/opt/polymarket-bot
EnvironmentFile=/opt/polymarket-bot/.env
ExecStart=/opt/polymarket-bot/.venv/bin/python -m polymarket_bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Health Monitoring

Dashboard runs on port 5050:
- `/health` - Overall system health
- `/api/positions` - Current positions
- `/api/metrics` - Trading metrics
- `/api/watchlist` - Watchlist entries

### Backup Strategy

```bash
# Daily PostgreSQL backup (add to cron)
0 2 * * * pg_dump predict > /backups/predict_$(date +\%Y\%m\%d).sql

# Keep last 7 days
find /backups -name "predict_*.sql" -mtime +7 -delete
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

Tests run automatically on:
- Push to `main` or `develop`
- Pull requests to `main`

### Pipeline Stages

1. **Lint & Type Check** - Ruff + MyPy
2. **Unit Tests** - Component tests with PostgreSQL
3. **Integration Tests** - Cross-component tests
4. **Coverage Check** - Enforce coverage thresholds

### Coverage Targets (Enforced in CI)

| Component | Target | Rationale |
|-----------|--------|-----------|
| storage | >95% | Foundation; bugs cascade everywhere |
| execution | >95% | Handles real money |
| core | >90% | Complex orchestration |
| strategies | >90% | Trading decisions |
| ingestion | >85% | External API mocking is hard |
| monitoring | >80% | Less critical path |

---

## Approval Workflow (Human-in-the-Loop)

### When Approval Required

The bot can require human approval before executing trades:
- Configurable via `REQUIRE_APPROVAL` env var
- Uses Telegram for approval requests

### Workflow

1. Bot identifies trade opportunity
2. Creates `approval_alerts` record
3. Sends Telegram message with details
4. Human responds (approve/reject)
5. If approved within timeout, trade executes
6. `trade_approvals` record created

### Tables

- `approval_alerts` - Pending approval requests
- `trade_approvals` - Approved trades with expiry

### Timeout

Approvals expire after configurable window (default 5 minutes).
After expiry, the opportunity is logged but not executed.
