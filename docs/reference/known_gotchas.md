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

**Fix:** Deduplicate by (condition_id, threshold), not just token_id.

```python
# WRONG - only checks token_id
if not triggers.has_triggered(token_id, threshold):
    execute()

# RIGHT - checks both
if not triggers.has_triggered(token_id, threshold) and \
   not triggers.has_condition_triggered(condition_id, threshold):
    execute()
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

## Adding New Gotchas

When you discover a new production bug:

1. Add it to this file with:
   - Clear description of what happened
   - Root cause analysis
   - Code example of the fix
   - Affected components
2. Add a regression test in the relevant component
3. Update the component's CLAUDE.md if needed
