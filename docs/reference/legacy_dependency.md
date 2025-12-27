# Legacy System Dependency

> **Status:** Active dependency on legacy SQLite database for model scores.

## Overview

The new trading bot (Predict_V3) has a **read-only dependency** on the legacy trading system (nextgen_pipeline) for model scores used in trading decisions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     HOST MACHINE                                 │
│                                                                  │
│  ┌──────────────────────┐      ┌──────────────────────────────┐ │
│  │  Legacy Bot          │      │  Docker Container            │ │
│  │  (nextgen_pipeline)  │      │  (Predict_V3)                │ │
│  │                      │      │                              │ │
│  │  - Calculates scores │      │  - Reads scores via          │ │
│  │  - Writes to SQLite  │─────▶│    ScoreBridge (read-only)   │ │
│  │                      │      │  - Executes trades           │ │
│  └──────────────────────┘      │  - Manages positions         │ │
│           │                    └──────────────────────────────┘ │
│           ▼                                                      │
│  ┌──────────────────────┐                                       │
│  │  guardrail.sqlite    │  ◀── Mounted read-only into Docker   │
│  │  (64GB)              │                                       │
│  └──────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
```

## File Locations

| Component | Host Path | Container Path |
|-----------|-----------|----------------|
| New bot codebase | `/home/z/Projects/Firinne/Github/Predict_V3` | `/workspace` |
| Legacy bot | `/home/z/Projects/Firinne/Github/PredictionM/nextgen_pipeline/` | N/A (outside container) |
| SQLite database | `.../nextgen_pipeline/data/guardrail.sqlite` | `/data/guardrail.sqlite` (ro) |

## What the New Bot Reads

The `ScoreBridge` class (`src/polymarket_bot/core/score_bridge.py`) reads from the legacy SQLite:

```sql
SELECT model_score, model_version
FROM polymarket_first_triggers
WHERE token_id = ? OR condition_id = ?
ORDER BY trigger_timestamp DESC
LIMIT 1
```

**Fields used:**
- `model_score` (float): ML model probability estimate (0.0-1.0)
- `model_version` (str): Model identifier, e.g., "logit-trained-20251125"

## Trading Decision Flow

```
1. Price crosses threshold (0.95)
2. ScoreBridge.get_score(token_id) → queries SQLite
3. Strategy checks: model_score >= 0.97?
   - YES → Generate EntrySignal
   - NO (0.90-0.97) → Add to watchlist
   - NO (< 0.90) → Hold
4. If no score available → Hold (no trade)
```

## Impact Analysis

### If Legacy Bot Stops Writing Scores

| Timeframe | Impact |
|-----------|--------|
| Immediate | Cached scores still work |
| Hours | Scores become stale, may miss opportunities |
| Days | Most scores outdated, reduced trading activity |

### If SQLite File Removed

- ScoreBridge logs warning: "SQLite not available"
- `model_score` returns `None` for all lookups
- Strategy returns `HoldSignal` (score below threshold)
- **Result:** Bot stops trading but doesn't crash

## Safe Operations on Legacy Bot

### Can Stop:
- Trading/execution (new bot handles this)
- Order management
- Position tracking
- Legacy dashboards
- Alert systems

### Must Keep Running:
- **Score calculation process** - Whatever writes `model_score` to `polymarket_first_triggers`
- Any data ingestion that feeds the scoring model

## Future: Removing Legacy Dependency

To fully decouple from legacy system:

1. **Option A:** Port the scoring model to new bot
   - Implement logistic regression model
   - Add feature extraction from market data
   - Remove ScoreBridge

2. **Option B:** External scoring service
   - Create API endpoint for scores
   - Replace SQLite reads with HTTP calls

3. **Option C:** Simplified scoring
   - Use price + time-to-end as proxy
   - Reduce accuracy but gain independence

## Docker Compose Mount

From `docker-compose.yml`:
```yaml
volumes:
  - /home/z/Projects/Firinne/Github/PredictionM/nextgen_pipeline/data/guardrail.sqlite:/data/guardrail.sqlite:ro
```

Note: Mounted as **read-only** (`:ro`) to prevent accidental writes.

---

*Last updated: 2025-12-27*
