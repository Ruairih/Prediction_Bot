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

## G11: Docker Dashboard Port Binding

**What happened:** Dashboard was inaccessible from outside the Docker container even when running correctly inside.

**Root causes (multiple issues):**
1. **Localhost binding:** Default `DASHBOARD_HOST=127.0.0.1` only listens on container's localhost, not accessible from host or network
2. **Port mapping mismatch:** Code used port 5050, but docker-compose.yml mapped different ports
3. **Port conflict inside container:** Port 8080 was in use by Codex MCP server
4. **Port conflict on host:** Port 5050 was in use on the host machine (outside the container)

**Understanding Docker port mapping:**
```
docker-compose ports: "EXTERNAL:INTERNAL"
                        ↓        ↓
                    HOST port  CONTAINER port
                    (outside)  (inside)
```

- `EXTERNAL` = port on the HOST machine - must be FREE on the host
- `INTERNAL` = port inside the container - must match `DASHBOARD_PORT`
- Access from Tailscale/network: `http://<host-ip>:EXTERNAL`

**Fix:**

```yaml
# docker-compose.yml
services:
  dev:
    ports:
      - "9050:9050"   # Dashboard accessible on port 9050
    environment:
      - DASHBOARD_HOST=0.0.0.0  # Bind to ALL interfaces (required for Docker/Tailscale)
      - DASHBOARD_PORT=9050     # Use a port FREE on host (not 5050!)
```

**Access (same for both inside and outside container):**
- Local: `curl http://localhost:9050/health`
- Tailscale: `http://<tailscale-ip>:9050`

**Running OUTSIDE container (directly on host):**
```bash
DATABASE_URL=postgresql://predict:predict@localhost:5433/predict \
DRY_RUN=false \
python -m polymarket_bot.main
```
- Defaults: `DASHBOARD_HOST=0.0.0.0`, `DASHBOARD_PORT=9050`
- No Docker port mapping needed - bot listens directly on host
- Use `localhost:5433` for DB (the mapped PostgreSQL port)
- Access via Tailscale: `http://<tailscale-ip>:9050`

**Key lessons:**
- `127.0.0.1` in Docker = only accessible from INSIDE that container
- `0.0.0.0` = accessible from outside (host, network, Tailscale)
- EXTERNAL port must be FREE on the HOST machine
- INTERNAL port must match `DASHBOARD_PORT` env var
- Check BOTH container AND host for port conflicts

**Debug commands:**
```bash
# Check inside container
curl http://localhost:5055/health

# Check from host (after container recreation)
curl http://localhost:9050/health

# Check what's using a port on host
lsof -i :5050  # or ss -tlnp | grep 5050

# Check if dashboard started
grep "Dashboard:" /tmp/bot.log
```

**Affected components:** monitoring/dashboard, docker-compose.yml

---

## G12: Stale Position Data ("Not Enough Balance" Bug)

**What happened:** Exit sell orders failed with `not enough balance / allowance` even though wallet had tokens.

**Root cause:** Positions were sold externally (via Polymarket website, another bot, or previous runs), but the database wasn't updated. Two scenarios:
1. **Partial sells**: Bot tried to sell 20 shares when only 15 remained
2. **Complete sells**: Bot tried to sell positions that no longer existed at all

**Impact:**
- Exit orders fail repeatedly with `PolyApiException[status_code=400]`
- Positions at profit target (99.8¢) stuck indefinitely
- "Not enough balance / allowance" errors in logs

**Fix:** Added `quick_sync_sizes()` method that syncs position state from Polymarket Data API before exit evaluation:

```python
# Before evaluating exits, sync with Polymarket
await execution_service.sync_position_sizes()

# Data API returns actual on-chain positions
GET https://data-api.polymarket.com/positions?user=0x...
# Response: [{ "asset": "...", "size": 15.0 }, ...]
```

**What the sync does:**
1. Fetches actual positions from Polymarket
2. Updates size mismatches in DB (partial sells)
3. Closes positions that no longer exist (complete sells)
4. Updates in-memory PositionTracker cache

**Key changes:**
1. `PositionSyncService.quick_sync_sizes()` - Fast sync before exits
2. `ExecutionService.sync_position_sizes()` - Wrapper with wallet address
3. `BackgroundTasksManager` - Calls sync before exit evaluation (60s interval)
4. `ExecutionConfig.wallet_address` - From `funder` in credentials

**Also applies when:**
- Positions manually sold on Polymarket website
- Another bot/script sold positions
- Markets resolved externally
- Partial fills on previous exit attempts

**Debug output:**
```
Quick sync: 10734760525... not found on Polymarket, marking closed
Quick sync: updated 0 sizes, closed 4 missing positions
```

**Affected components:** execution/position_sync, execution/service, core/background_tasks

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
