# Architecture Decisions

This document explains key architectural choices and their rationale.

## Strategy-Agnostic Framework

**Decision:** The framework handles infrastructure while strategies are pluggable modules.

**Rationale:**
- Strategies are the differentiator - everything else is commodity infrastructure
- Multiple strategies can be tested without framework changes
- Clear separation of concerns makes testing easier

**Trade-off:** More abstraction overhead vs. flexibility.

---

## Build Phases

**Decision:** Strict dependency-ordered build phases (Storage → Ingestion/Strategies → Core → Execution/Monitoring).

**Rationale:**
- Prevents circular dependencies
- Enables parallel work within phases
- Each phase can be tested independently

**Trade-off:** Sequential bottleneck at phase boundaries vs. clean dependencies.

---

## PostgreSQL with asyncpg

**Decision:** Use PostgreSQL with asyncpg for async database access.

**Rationale:**
- High-performance async connection pooling
- ACID compliance for financial data
- Robust concurrent write support
- Production-ready scalability
- Rich query capabilities (JSONB, window functions, CTEs)

**History:** Originally started with SQLite for prototyping, migrated to PostgreSQL for production reliability. See `migrate_sqlite_to_postgres.py` for migration tooling.

**Trade-off:** Requires PostgreSQL server vs. simpler single-file SQLite deployment.

---

## Pure Strategy Layer

**Decision:** Strategies have no I/O - they receive data and return signals.

**Rationale:**
- Strategies are easy to test (no mocks needed)
- Strategies can be backtested offline
- Clear data flow makes debugging easier

**Trade-off:** More data passing vs. strategy simplicity.

---

## Dual-Key Trigger Deduplication

**Decision:** Use both (token_id, threshold) AND (condition_id, threshold) for deduplication.

**Rationale:**
- Learned from G2 gotcha - multiple token_ids can map to same market
- Prevents duplicate trades that would have lost money

**Trade-off:** More complex queries vs. correctness.

---

## Exit Strategy Based on Hold Duration

**Decision:** Short positions (<7 days) hold to resolution; long positions use profit target/stop loss.

**Rationale:**
- Short-duration positions have very high win rates (99%+)
- Long-duration positions tie up capital
- Exit strategies improve capital efficiency for longer holds

**Trade-off:** Complexity vs. capital efficiency.
