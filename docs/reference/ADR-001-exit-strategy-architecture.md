# ADR-001: Exit Strategy Architecture Refactor

**Status:** Proposed
**Date:** 2025-12-25
**Decision:** Deferred - document now, implement later

---

## Context

The bot is designed to be **strategy-agnostic** - strategies are pluggable modules loaded from a registry. However, there's a significant architectural inconsistency:

| Decision Type | Current Owner | Should Be |
|---------------|---------------|-----------|
| Entry decisions | Strategy | Strategy |
| Exit decisions | Framework | Strategy |

### Current State

Exit logic is hardcoded in the framework layer:

```
ExitManager (execution/exit_manager.py)
├── profit_target: 0.99 (hardcoded default)
├── stop_loss: 0.90 (hardcoded default)
├── min_hold_days: 7 (hardcoded default)
└── Decision logic embedded in evaluate_exit()

BackgroundTasksManager._exit_evaluation_loop()
├── Fetches prices periodically (60s)
├── Calls ExecutionService.evaluate_exits()
├── Uses ExitManager rules (NOT strategy logic)
└── Executes exits directly
```

**The flow bypasses strategies entirely:**

```
Price Update → BackgroundTasks → ExitManager (hardcoded rules) → Execute
                                       ↑
                                  Strategy is NOT consulted
```

### Problems

1. **Inconsistent design**: Entry is strategy-driven, exit is framework-driven
2. **One-size-fits-all**: All strategies forced to use same exit rules
3. **No opt-out**: A strategy cannot say "hold to resolution, no auto-exits"
4. **Limited flexibility**: No trailing stops, time-based exits, or custom logic
5. **Config confusion**: Exit params look like strategy config but live in framework

---

## Proposed Solution

### 1. Add Strategy-Level Exit Interface

```python
# strategies/protocol.py

@dataclass
class ExitContext:
    """Context provided to strategy for exit evaluation."""
    position: Position
    current_price: Decimal
    entry_price: Decimal
    hold_duration_days: int
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    market_end_date: Optional[datetime]
    time_to_resolution_hours: Optional[float]

class ExitStrategy(Protocol):
    """Protocol for exit decision logic."""

    def evaluate_exit(self, context: ExitContext) -> Optional[ExitSignal]:
        """
        Evaluate whether to exit a position.

        Returns:
            ExitSignal if should exit, None to hold
        """
        ...
```

### 2. Built-in Exit Strategies

```python
# strategies/exit_strategies.py

class LegacyExitStrategy(ExitStrategy):
    """
    Current behavior - backwards compatible.

    - Hold < 7 days: hold to resolution
    - Hold >= 7 days: profit target (99c) or stop loss (90c)
    """
    def __init__(
        self,
        profit_target: Decimal = Decimal("0.99"),
        stop_loss: Decimal = Decimal("0.90"),
        min_hold_days: int = 7,
    ):
        ...

class NoExitStrategy(ExitStrategy):
    """Never auto-exit, always hold to resolution."""
    def evaluate_exit(self, context: ExitContext) -> None:
        return None  # Always hold

class TrailingStopStrategy(ExitStrategy):
    """Exit when price drops X% from high-water mark."""
    ...

class TimeBasedExitStrategy(ExitStrategy):
    """Exit after N days regardless of price."""
    ...
```

### 3. Strategy Composition

Strategies can either:
- Implement `evaluate_exit()` directly
- Compose with an `ExitStrategy` instance
- Default to `LegacyExitStrategy` for backwards compatibility

```python
class HighProbYesStrategy(Strategy):
    def __init__(self):
        self.exit_strategy = LegacyExitStrategy(
            profit_target=Decimal("0.99"),
            stop_loss=Decimal("0.90"),
            min_hold_days=7,
        )

    def evaluate_exit(self, context: ExitContext) -> Optional[ExitSignal]:
        return self.exit_strategy.evaluate_exit(context)

class ConservativeStrategy(Strategy):
    """A strategy that always holds to resolution."""

    def __init__(self):
        self.exit_strategy = NoExitStrategy()

    def evaluate_exit(self, context: ExitContext) -> Optional[ExitSignal]:
        return self.exit_strategy.evaluate_exit(context)
```

### 4. Updated Exit Flow

```
BackgroundTasksManager._exit_evaluation_loop()
    │
    ├── Fetch prices for open positions
    │
    ├── For each position:
    │   ├── Build ExitContext
    │   ├── Get strategy (from position.strategy_name or active)
    │   ├── Call strategy.evaluate_exit(context)  # STRATEGY DECIDES
    │   └── If ExitSignal returned → execute
    │
    └── ExecutionService.execute_exit() handles mechanics only
```

### 5. Store Strategy Name on Positions

Add `strategy_name` column to positions table:

```sql
ALTER TABLE positions ADD COLUMN strategy_name VARCHAR(100);
```

Set on entry:
```python
# In ExecutionService.execute_entry()
position.strategy_name = self._current_strategy.name
```

Lookup on exit:
```python
# In exit evaluation
strategy = registry.get(position.strategy_name) or active_strategy
exit_signal = strategy.evaluate_exit(context)
```

---

## Implementation Plan

### Phase 1: Infrastructure (Low Risk)
1. Add `strategy_name` column to positions table
2. Set `strategy_name` when creating positions
3. No behavior change yet

### Phase 2: Interface Definition
1. Define `ExitContext` dataclass in `strategies/protocol.py`
2. Define `ExitStrategy` protocol
3. Add optional `evaluate_exit()` to `Strategy` protocol
4. Create `LegacyExitStrategy` with current logic
5. Create `NoExitStrategy`

### Phase 3: Core Exit Evaluator
1. Create `ExitEvaluator` in `core/` that:
   - Builds `ExitContext` for positions
   - Looks up strategy by `position.strategy_name`
   - Calls `strategy.evaluate_exit()`
   - Falls back to `LegacyExitStrategy` if not implemented
2. Keep `ExitManager` for execution mechanics only

### Phase 4: Integration
1. Update `BackgroundTasksManager._exit_evaluation_loop()` to use new evaluator
2. Update `ExecutionService` to remove decision logic
3. Update existing strategies to use `LegacyExitStrategy` explicitly

### Phase 5: Cleanup
1. Deprecate exit config at framework level
2. Move exit config into strategy config
3. Update documentation

---

## Backwards Compatibility

| Scenario | Behavior |
|----------|----------|
| Strategy doesn't implement `evaluate_exit()` | Use `LegacyExitStrategy` with framework config |
| Position has no `strategy_name` | Use active strategy or `LegacyExitStrategy` |
| Existing config (profit_target, etc.) | Still works, initializes `LegacyExitStrategy` |

---

## Open Questions (Decided)

| Question | Decision |
|----------|----------|
| Per-strategy exit intervals? | No - keep global interval (simpler) |
| Store strategy_name on positions? | Yes - needed for proper routing |
| Priority? | Deferred - document now, implement later |

---

## Files Affected

```
strategies/
├── protocol.py          # Add ExitContext, ExitStrategy, update Strategy
├── exit_strategies.py   # NEW: LegacyExitStrategy, NoExitStrategy, etc.
└── builtin/
    └── high_prob_yes.py # Add exit_strategy composition

core/
├── exit_evaluator.py    # NEW: Strategy-aware exit evaluation
└── background_tasks.py  # Update to use ExitEvaluator

execution/
├── exit_manager.py      # Remove decision logic, keep execution
└── service.py           # Remove exit decision logic

storage/
└── models.py            # Add strategy_name to Position

seed/
└── XX_add_strategy_name.sql  # Migration
```

---

## References

- Root CLAUDE.md: Strategy-agnostic architecture description
- strategies/CLAUDE.md: Strategy protocol documentation
- execution/CLAUDE.md: Current exit manager documentation
