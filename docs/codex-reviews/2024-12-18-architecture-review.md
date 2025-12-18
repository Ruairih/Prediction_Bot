# Codex Architecture Review - 2024-12-18

## Overview

External review of the Polymarket Trading Bot framework using OpenAI Codex.
This document captures findings, recommendations, and tracks remediation progress.

**Review Scope:** Full codebase architecture, storage layer, ingestion layer
**Reviewed By:** Codex (via MCP)
**Status:** Action Required

---

## Executive Summary

The codebase has solid architectural foundations with clean component separation and
well-documented gotcha protections (G1-G6). However, several correctness and safety
issues were identified that require immediate attention before production use.

**Critical Issues:** 4
**Medium Issues:** 3
**Low Priority:** 3

---

## Critical Issues (Must Fix)

### CRIT-001: Float Precision for Monetary Fields

**Severity:** CRITICAL
**Component:** Storage Layer
**Files:** `src/polymarket_bot/storage/models.py`

**Problem:**
All price, size, and PnL fields use Python `float` type, which causes precision
drift in financial calculations. Example: `0.1 + 0.2 = 0.30000000000000004`

**Impact:**
- Trigger comparisons to thresholds like `0.95` may fail spuriously
- PnL calculations will drift over thousands of trades
- Inconsistent with ingestion layer which correctly uses `Decimal`

**Affected Fields:**
```python
# Lines 27-30, 42-43, 87-88, 113-114, 130, 157-158, 177-180, 198-204, etc.
best_bid: Optional[float]    # Should be Decimal
price: Optional[float]       # Should be Decimal
size: Optional[float]        # Should be Decimal
entry_price: float           # Should be Decimal
realized_pnl: float          # Should be Decimal
```

**Fix:**
```python
from decimal import Decimal

class PolymarketTrade(BaseModel):
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None

class Position(BaseModel):
    size: Decimal
    entry_price: Decimal
    entry_cost: Decimal
    current_price: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Decimal = Decimal("0")
```

**Tracking:**
- [ ] Update `PolymarketTrade` model
- [ ] Update `Position` model
- [ ] Update `ExitEvent` model
- [ ] Update `DailyPnl` model
- [ ] Update `PaperTrade` model
- [ ] Update `LiveOrder` model
- [ ] Update all other models with price/size/pnl fields
- [ ] Add precision tests for boundary conditions
- [ ] Verify database schema uses NUMERIC type

---

### CRIT-002: Candidate Watermark Non-Monotonic

**Severity:** CRITICAL
**Component:** Storage Layer
**File:** `src/polymarket_bot/storage/repositories/candidate_repo.py:144-154`

**Problem:**
The candidate watermark update can move backwards if out-of-order processing occurs.
Unlike `TriggerWatermarkRepository` which correctly uses `GREATEST()`, the candidate
watermark blindly overwrites.

**Impact:**
- Breaks idempotent processing guarantees
- Can cause duplicate candidate processing
- May lead to duplicate trade execution

**Current Code (BROKEN):**
```python
async def update(self, threshold: float, created_at: str) -> CandidateWatermark:
    query = """
        INSERT INTO candidate_watermarks (threshold, last_created_at, updated_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (threshold) DO UPDATE
        SET last_created_at = $2, updated_at = $3  -- BUG: No monotonic guard!
        RETURNING *
    """
```

**Fix:**
```python
async def update(self, threshold: float, created_at: str) -> CandidateWatermark:
    query = """
        INSERT INTO candidate_watermarks (threshold, last_created_at, updated_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (threshold) DO UPDATE
        SET last_created_at = GREATEST(candidate_watermarks.last_created_at, $2),
            updated_at = $3
        RETURNING *
    """
```

**Tracking:**
- [ ] Fix `CandidateWatermarkRepository.update()` to use `GREATEST()`
- [ ] Add regression test for out-of-order processing
- [ ] Verify existing trigger watermark pattern is correct (it is)

---

### CRIT-003: SQL Injection in ApprovalAlertRepository

**Severity:** CRITICAL (Security)
**Component:** Storage Layer
**File:** `src/polymarket_bot/storage/repositories/approval_repo.py:176-186`

**Problem:**
The `delete_old` method uses f-string interpolation instead of parameterized queries.

**Current Code (VULNERABLE):**
```python
async def delete_old(self, days: int = 7) -> int:
    query = """
        DELETE FROM approval_alerts
        WHERE alerted_at < NOW() - INTERVAL '$1 days'
    """
    # Note: PostgreSQL interval syntax
    result = await self.db.execute(
        f"DELETE FROM approval_alerts WHERE alerted_at < NOW() - INTERVAL '{days} days'"
    )
```

**Impact:**
- While `days` is typed as `int`, the pattern is dangerous
- Inconsistent with parameterized queries used elsewhere
- Sets bad precedent for future code

**Fix:**
```python
async def delete_old(self, days: int = 7) -> int:
    """Delete alerts older than N days. Returns count deleted."""
    query = """
        DELETE FROM approval_alerts
        WHERE alerted_at < NOW() - make_interval(days => $1)
    """
    result = await self.db.execute(query, days)
    return int(result.split()[-1]) if result else 0
```

**Tracking:**
- [ ] Fix `ApprovalAlertRepository.delete_old()` to use parameterized query
- [ ] Audit all repositories for similar patterns
- [ ] Add test for the fix

---

### CRIT-004: Async Callbacks Not Awaited

**Severity:** CRITICAL
**Component:** Ingestion Layer
**File:** `src/polymarket_bot/ingestion/service.py:449-454`

**Problem:**
External callbacks are invoked synchronously, so async callbacks silently fail.

**Current Code (BROKEN):**
```python
# Line 449-454
if self._external_callback:
    try:
        self._external_callback(update)  # NOT AWAITED!
    except Exception as e:
        logger.error(f"Error in external callback: {e}")
```

**Impact:**
- Any async callback passed to `IngestionService` will silently no-op
- Coroutines are created but never executed
- No error is raised, making debugging extremely difficult

**Fix:**
```python
if self._external_callback:
    try:
        result = self._external_callback(update)
        if asyncio.iscoroutine(result):
            await result
    except Exception as e:
        logger.error(f"Error in external callback: {e}")
```

**Also update the type hint:**
```python
# Line 118
EventCallback = Callable[[PriceUpdate], Union[None, Awaitable[None]]]
```

**Tracking:**
- [ ] Fix callback invocation to await coroutines
- [ ] Update `EventCallback` type hint
- [ ] Add test with async callback

---

## Medium Issues (Should Fix)

### MED-001: Dashboard Not Runnable

**Severity:** MEDIUM
**Component:** Ingestion Layer
**Files:** `pyproject.toml`, `src/polymarket_bot/ingestion/service.py:215`

**Problem:**
1. FastAPI and Uvicorn are imported in `dashboard.py` but not declared in dependencies
2. The service never starts the dashboard even when `dashboard_enabled=True`

**Impact:**
- Monitoring dashboard is completely non-functional
- Import errors will occur if dashboard code is reached

**Fix:**

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
dashboard = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
]
```

Wire dashboard startup in `service.py`:
```python
async def start(self) -> None:
    # ... existing code ...

    # Start dashboard if enabled
    if self._config.dashboard_enabled:
        from .dashboard import create_dashboard_app, run_dashboard
        self._dashboard_app = create_dashboard_app(self)
        self._dashboard_task = asyncio.create_task(
            run_dashboard(
                self._dashboard_app,
                host=self._config.dashboard_host,
                port=self._config.dashboard_port,
            )
        )
```

**Tracking:**
- [ ] Add `fastapi` and `uvicorn` to optional dependencies
- [ ] Wire dashboard startup in `IngestionService.start()`
- [ ] Test dashboard functionality

---

### MED-002: WebSocket URL Config Ignored

**Severity:** MEDIUM
**Component:** Ingestion Layer
**Files:** `src/polymarket_bot/ingestion/service.py:52`, `src/polymarket_bot/ingestion/websocket.py:77`

**Problem:**
`IngestionConfig.websocket_url` is defined but never passed to `PolymarketWebSocket`,
which uses a hardcoded class constant.

**Impact:**
- Cannot override WebSocket URL for testing
- Cannot use alternative endpoints (staging, etc.)

**Fix:**

Update `PolymarketWebSocket.__init__`:
```python
def __init__(
    self,
    on_price_update: PriceCallback,
    # ... other params ...
    url: Optional[str] = None,  # NEW
):
    self._url = url or self.WS_URL
```

Update `IngestionService.start()`:
```python
self._websocket = PolymarketWebSocket(
    on_price_update=self._handle_price_update,
    # ... other params ...
    url=self._config.websocket_url,  # NEW
)
```

**Tracking:**
- [ ] Add `url` parameter to `PolymarketWebSocket`
- [ ] Pass config URL in `IngestionService`
- [ ] Add test verifying URL override works

---

### MED-003: Documentation Drift

**Severity:** MEDIUM
**Component:** Documentation
**Files:** `CLAUDE.md:40`, `src/polymarket_bot/storage/CLAUDE.md:5`

**Problem:**
Documentation references SQLite in the architecture diagram, but the system uses PostgreSQL.

**Impact:**
- Confuses new developers
- May lead to incorrect deployment decisions

**Fix:**
Update `CLAUDE.md` line 40:
```
│  PostgreSQL │  (was: SQLite)
```

**Tracking:**
- [ ] Update architecture diagram in root `CLAUDE.md`
- [ ] Verify all SQLite references are removed
- [ ] Update any deployment docs

---

## Low Priority Issues (Nice to Have)

### LOW-001: MetricsCollector Lock Unused

**File:** `src/polymarket_bot/ingestion/metrics.py:155`
**Problem:** Defines `self._lock = asyncio.Lock()` but never uses it
**Impact:** Low - async is single-threaded by default
**Tracking:**
- [ ] Either use the lock in update methods or remove it

---

### LOW-002: create_many Return Count Inaccurate

**File:** `src/polymarket_bot/storage/repositories/trade_repo.py:48`
**Problem:** Returns `len(trades)` even when conflicts are ignored
**Impact:** Low - nothing currently uses the return value
**Tracking:**
- [ ] Fix to return actual inserted count if needed

---

### LOW-003: Public API Name Mismatches

**Files:** `src/polymarket_bot/ingestion/CLAUDE.md:56` vs `src/polymarket_bot/ingestion/__init__.py`
**Problem:** Doc mentions `PolymarketClient`, exports `PolymarketRestClient`
**Impact:** Low - causes confusion when reading docs
**Tracking:**
- [ ] Align documentation with actual exports

---

## Open Questions

These require clarification before implementation:

1. **Timestamp Units:** What is the canonical unit for stored trade timestamps
   (seconds vs milliseconds)? Does it align with ingestion filters?

2. **WebSocket Subscription Key:** Is `assets_ids` correct for Polymarket, or
   should it be `asset_ids`? (See `websocket.py:461`)

3. **Ingestion Persistence:** Should ingestion persist trades directly to storage,
   or is that intentionally deferred to core/execution?

4. **Dashboard Deployment:** Should the dashboard run as a separate service or
   embedded in ingestion?

---

## Remediation Priority

**Phase 1 - Critical (Do First):**
1. CRIT-001: Float → Decimal conversion
2. CRIT-002: Candidate watermark monotonicity
3. CRIT-003: SQL injection fix
4. CRIT-004: Async callback fix

**Phase 2 - Medium (Do Second):**
5. MED-001: Dashboard dependencies and wiring
6. MED-002: WebSocket URL configuration
7. MED-003: Documentation updates

**Phase 3 - Low (As Time Permits):**
8. LOW-001 through LOW-003

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2024-12-18 | Codex/Claude | Initial review |

