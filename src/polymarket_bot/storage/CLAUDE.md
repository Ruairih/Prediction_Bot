# Storage Layer - CLAUDE.md

## Component Purpose

The Storage Layer is the **foundation** of the trading bot. It provides:
- Async PostgreSQL connection management with asyncpg
- Pydantic models matching the production schema
- Repository pattern for all data access
- Watermark pattern for idempotent processing

**Build this FIRST.** All other components depend on it.

---

## Architecture

### Database
- **asyncpg** connection pool for high-performance async access
- Connection pooling with configurable min/max connections
- Transaction context managers with auto-commit/rollback

### Production Schema
The schema matches `seed/01_schema.sql` - the battle-tested production schema.
**Do NOT rename tables or change the schema structure.**

### Key Tables

| Table | Purpose |
|-------|---------|
| `polymarket_trades` | Raw trade data from Polymarket |
| `trade_watermarks` | Track last processed trade per condition |
| `polymarket_first_triggers` | First-hit triggers (deduplication) |
| `trigger_watermarks` | Track processing state per threshold |
| `polymarket_candidates` | Candidates awaiting decision |
| `paper_trades` | Paper trading records |
| `live_orders` | Real orders submitted to Polymarket |
| `positions` | Open/closed positions |
| `exit_events` | Exit event records |
| `trade_approvals` | Human approval for trades |
| `approval_alerts` | Alerts pending approval |

---

## Critical Patterns

### 1. Watermark Pattern (Idempotent Processing)

```python
# CORRECT: Use watermarks to track processed data
watermark = await trade_watermark_repo.get_timestamp(condition_id)
new_trades = await get_trades_since(watermark)
for trade in new_trades:
    await process(trade)
await trade_watermark_repo.update(condition_id, new_trades[-1].timestamp)
```

### 2. Dual-Key Trigger Deduplication (G2 Gotcha)

```python
# CORRECT: Check BOTH token_id AND condition_id
should_trigger = await trigger_repo.should_trigger(
    token_id=token_id,
    condition_id=condition_id,  # CRITICAL
    threshold=threshold,
)
if should_trigger:
    await trigger_repo.create(trigger)
```

### 3. Trade Staleness Filtering (G1 Gotcha)

```python
# CORRECT: Filter by age to prevent Belichick Bug
recent_trades = await trade_repo.get_recent(
    condition_id,
    max_age_seconds=300  # Only last 5 minutes
)
```

---

## File Structure

```
storage/
├── __init__.py          # Public exports
├── database.py          # Async connection pool (asyncpg)
├── models.py            # Pydantic models matching production schema
├── repositories/
│   ├── __init__.py
│   ├── base.py          # Base repository class
│   ├── trade_repo.py    # Trades + watermarks
│   ├── trigger_repo.py  # Triggers + watermarks + dual-key dedup
│   ├── candidate_repo.py
│   ├── order_repo.py    # LiveOrder, PaperTrade
│   ├── position_repo.py # Position, ExitEvent, DailyPnl
│   ├── approval_repo.py # TradeApproval, ApprovalAlert
│   ├── market_repo.py   # StreamWatchlist, Resolution, TokenMeta
│   └── watchlist_repo.py # TradeWatchlist, MarketScoresCache, ScoreHistory
└── tests/
    ├── conftest.py      # PostgreSQL test fixtures
    ├── test_database.py
    ├── test_trade_repo.py
    ├── test_trigger_repo.py
    └── test_position_repo.py
```

---

## Usage Examples

### Initialize Database

```python
from polymarket_bot.storage import Database, DatabaseConfig

config = DatabaseConfig(
    url="postgresql://predict:predict@postgres:5432/predict"
)
db = Database(config)
await db.initialize()
```

### Use Repositories

```python
from polymarket_bot.storage import (
    TriggerRepository,
    PositionRepository,
    PolymarketFirstTrigger,
)

# Create repositories
trigger_repo = TriggerRepository(db)
position_repo = PositionRepository(db)

# Check if should trigger (with G2 protection)
should = await trigger_repo.should_trigger(
    token_id="0x...",
    condition_id="0x...",
    threshold=0.95,
)

# Get open positions
open_positions = await position_repo.get_open()
```

### Transaction Management

```python
# Auto-commit on success, rollback on exception
async with db.transaction() as conn:
    await conn.execute("INSERT INTO positions ...")
    await conn.execute("UPDATE daily_pnl ...")
```

---

## Testing

Tests require PostgreSQL running (via docker-compose):

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Run storage tests
PYTHONPATH=src pytest src/polymarket_bot/storage/tests/ -v

# Run specific test
PYTHONPATH=src pytest src/polymarket_bot/storage/tests/test_trigger_repo.py -v
```

### Test Database URL

Tests use `DATABASE_URL` env var, defaulting to:
```
postgresql://predict:predict@localhost:5433/predict
```

(Port 5433 is the docker-compose mapped port)

---

## Gotchas Implemented

| Gotcha | Implementation |
|--------|----------------|
| G1: Stale Trade Data | `TradeRepository.get_recent(max_age_seconds=300)` |
| G2: Duplicate Token IDs | `TriggerRepository.should_trigger()` checks both token_id AND condition_id |
| Watermark Pattern | All watermark repos use `GREATEST()` to prevent going backwards |

---

## Dependencies

- `asyncpg` - Async PostgreSQL driver
- `pydantic` - Data validation

Ensure `asyncpg` is installed:
```bash
pip install asyncpg
```
