# Known Gotchas

These are **real production bugs** that caused significant issues. Every agent working on this codebase MUST understand these.

## G1: Stale Trade Data ("Belichick Bug")

**What happened:** Polymarket's "recent trades" API returned trades that were 2 months old for a low-volume market. The bot executed at 95¢ based on this stale data when the actual market was at 5¢.

**Root cause:** The API returns trades by recency in their database, not by actual trade timestamp. Low-volume markets may have no recent trades.

**Fix:** ALWAYS filter trades by timestamp. Default max age: 300 seconds.

```python
# WRONG - trusts API's definition of "recent"
trades = await client.get_trades(condition_id)

# RIGHT - explicitly filter by age
trades = await client.get_recent_trades(condition_id, max_age_seconds=300)
```

**Affected components:** ingestion, core, strategies

---

## G2: Duplicate Token IDs

**What happened:** Multiple `token_id`s mapped to the same market (`condition_id`). The bot traded the same market multiple times, thinking they were different.

**Root cause:** Polymarket can create multiple token IDs for the same outcome in a market.

**Fix:** Use `should_trigger()` which checks both token_id AND condition_id.

```python
# WRONG - only checks token_id
if not triggers.has_triggered(token_id, threshold):
    execute()

# RIGHT - use should_trigger() for combined check
if triggers.should_trigger(token_id, condition_id, threshold):
    execute()
    triggers.create(trigger)

# Note: has_triggered() now requires condition_id parameter:
# has_triggered(token_id, condition_id, threshold) -> bool
```

**Affected components:** storage, core, strategies

---

## G3: WebSocket Missing Trade Size

**What happened:** Strategies needed trade size to compute features, but WebSocket price updates don't include it. Strategies got `None` for size.

**Root cause:** WebSocket messages only contain price, not size.

**Fix:** Fetch size separately from REST API when needed.

```python
# WebSocket gives you this (NO SIZE):
{"asset_id": "0x...", "price": "0.95"}

# Must fetch size separately:
size = await client.get_trade_size_at_price(condition_id, price)
```

**Affected components:** ingestion, core, strategies

---

## G4: CLOB Balance Cache Staleness

**What happened:** Showed $1000 available when actual balance was $50 after trades.

**Root cause:** Polymarket's balance API caches aggressively. After order fills, the cached balance is stale.

**Fix:** Refresh balance after every order fill, not just on startup.

```python
# After order fills:
order_manager.sync_order_status(order_id)
balance_manager.refresh()  # MUST do this
```

**Affected components:** execution

---

## G5: Orderbook vs Trade Price Divergence

**What happened:** A spike trade showed 95¢ while the orderbook was actually at 5¢. Would have bought at 95¢ in a 5¢ market.

**Root cause:** Anomalous trades can trigger at prices that don't reflect the actual market.

**Fix:** ALWAYS verify orderbook price before executing. Reject if >10¢ deviation.

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

**Affected components:** core, execution

---

## G6: Rainbow Bug (Weather Filter)

**What happened:** "Rainbow Six Siege" esports market was incorrectly blocked as a weather market because it contained "rain".

**Root cause:** Naive substring matching for weather keywords.

**Fix:** Use word boundaries in regex matching.

```python
# WRONG
if "rain" in question.lower():
    block_as_weather()

# RIGHT
import re
weather_pattern = r'\b(rain|snow|hurricane|storm|weather)\b'
if re.search(weather_pattern, question, re.IGNORECASE):
    block_as_weather()
```

**Affected components:** strategies

---

## G7: Timezone-Aware Datetime in PostgreSQL

**What happened:** `asyncpg` raised errors when inserting timezone-aware datetimes into `timestamp without time zone` columns.

**Root cause:** PostgreSQL's `timestamp` type (without timezone) cannot accept Python's timezone-aware `datetime` objects.

**Fix:** Convert to naive UTC before inserting.

```python
def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert datetime to naive UTC for PostgreSQL."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
```

**Affected components:** ingestion, storage

---

## G8: Startup Hang (Market Fetch Blocking)

**What happened:** Bot appeared frozen during startup for 30+ seconds. Users thought it crashed.

**Root cause:** `IngestionService.start()` synchronously fetched ALL ~10,000 markets from the Polymarket API before connecting the WebSocket. With 100 markets per API call, this took 30+ seconds with no progress logging.

**Fix:** Cap initial fetch and continue in background.

```python
@dataclass
class IngestionConfig:
    # Limit initial fetch to avoid blocking startup
    startup_market_limit: int = 2000  # ~6 seconds instead of 30+

# Background task fetches remaining markets after startup
async def _background_fetch_remaining_markets(self) -> None:
    # Continues from offset where startup stopped
    # Subscribes to new tokens incrementally
```

**Behavior after fix:**
- Startup: ~2 seconds (first 2000 markets)
- Background: Remaining markets fetched and subscribed over ~30 seconds
- No more apparent freeze

**Affected components:** ingestion

---

## G9: Database Migration Syntax Incompatibility

**What happened:** PostgreSQL init failed because migration scripts used SQLite-only syntax (`INSERT OR IGNORE`, recreating tables to change PK).

**Root cause:** Early development used SQLite. Migration scripts weren't updated for PostgreSQL.

**Fix:** All migrations must use PostgreSQL-compatible syntax.

```sql
-- WRONG (SQLite)
INSERT OR IGNORE INTO table_name ...
CREATE TABLE new_table ...
DROP TABLE old_table;
ALTER TABLE new_table RENAME TO old_table;

-- RIGHT (PostgreSQL)
INSERT INTO table_name ... ON CONFLICT DO NOTHING
DO $$ BEGIN
    ALTER TABLE table_name DROP CONSTRAINT IF EXISTS pk_name;
    ALTER TABLE table_name ADD PRIMARY KEY (col1, col2);
END $$;
```

**Also fixed:**
- `setup_test_db.sh` now applies ALL `seed/*.sql` files (not just 01)
- `bootstrap_db.sh` script added for comprehensive database setup
- Database reconnect logic added with exponential backoff

**Affected components:** storage, all migrations

---

## G10: Position Import Timestamp Loss

**What happened:** Positions imported from Polymarket showed as 0 days old when they were actually 13-25 days old. Exit logic (7-day hold period) wasn't being applied to positions that should have been eligible.

**Root cause:** The Polymarket positions API does NOT return purchase timestamps. It only returns:
- `size`, `avgPrice`, `curPrice` - current state
- `cashPnl`, `percentPnl` - P&L metrics
- No `createdAt`, `purchaseDate`, or `firstTradeTimestamp`

When importing, all timestamps (`entry_timestamp`, `hold_start_at`, `imported_at`) were set to NOW.

**Impact:**
- 14 of 17 positions had wrong timestamps
- Positions that were 25 days old appeared as 0 days old
- Exit logic would never trigger because positions appeared too new
- Risk of holding positions indefinitely that should have exited

**Fix:** Added `hold_policy="actual"` option that fetches trade history from the trades API:

```python
# The trades API DOES have timestamps
url = f"{POLYMARKET_DATA_API}/trades?user={wallet_address}"

# Build mapping: token_id -> earliest BUY timestamp
for trade in trades:
    if trade["side"] == "BUY":
        token_first_buy[trade["asset"]] = trade["timestamp"]

# Use actual timestamp when importing
await sync_service.sync_positions(
    wallet_address="0x...",
    hold_policy="actual"  # Uses real trade timestamps
)
```

**Also added:** `correct_hold_timestamps()` method to fix existing positions with wrong timestamps.

**Key lesson:** Always verify what an API actually returns. The positions API returning P&L data implied it knew purchase timestamps, but it doesn't.

**Affected components:** execution/position_sync

---

## Adding New Gotchas

When you discover a new production bug:

1. Add it to this file with:
   - Clear description of what happened
   - Root cause analysis
   - Code example of the fix
   - Affected components
2. Add a regression test in the relevant component
3. Update the component's CLAUDE.md if needed
