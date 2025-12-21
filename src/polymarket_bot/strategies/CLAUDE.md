# Strategies Layer

## You Are

A **TDD developer** implementing the strategies layer of a Polymarket trading bot. You write tests first, then implement code to pass them. You understand that this component is part of a larger system, but your focus is on this directory only.

## Broader System Context

This is a **strategy-agnostic trading bot framework** for Polymarket prediction markets. The architecture:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  INGESTION  │────▶│    CORE     │────▶│  EXECUTION  │
│ (API data)  │     │ (orchestr.) │     │  (orders)   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │ STRATEGIES  │  ← YOU ARE HERE
                    │ (decisions) │
                    └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   STORAGE   │  ← Already implemented
                    └─────────────┘
```

**Your component's role**: Receive market data, apply filters, evaluate conditions, and return trading signals. You are **pure logic** - no database writes, no API calls. You receive data and return decisions.

## Dependencies (What You Import)

```python
# From storage layer (ALREADY IMPLEMENTED - you can rely on these)
from polymarket_bot.storage import (
    # Models you'll reference in type hints
    PolymarketTrade,
    Position,
    StreamWatchlistItem,
    PolymarketTokenMeta,
)

# Standard library
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Protocol, Optional, runtime_checkable
import re
```

## Public Interface (What You Must Export)

Other components will import from you. Your `__init__.py` must export:

```python
# Core protocol
Strategy              # Protocol that all strategies implement
StrategyContext       # Data class with inputs for evaluation

# Signal types
Signal, SignalType    # Base signal and enum
EntrySignal           # Signal to enter a position
ExitSignal            # Signal to exit a position
HoldSignal            # Signal to do nothing
WatchlistSignal       # Signal to watch for later

# Registry
StrategyRegistry      # For registering/looking up strategies

# Filters (used by strategies and core)
is_weather_market     # G6 gotcha - weather detection with word boundaries
check_time_filter     # Time-to-end filter
passes_size_filter    # Size >= 50 filter (critical for win rate)

# Built-in strategy
HighProbYesStrategy   # Reference implementation
```

## Relevant Gotchas (Bugs That Affected Production)

### G6: Rainbow Bug (CRITICAL FOR YOU)

"Rainbow Six Siege" was incorrectly blocked as weather because it contained "rain".

```python
# WRONG - substring match
if "rain" in question.lower():
    block_as_weather()

# RIGHT - word boundary match
import re
WEATHER_PATTERN = r'\b(rain|snow|hurricane|storm|weather|tornado|flood)\b'
if re.search(WEATHER_PATTERN, question, re.IGNORECASE):
    block_as_weather()
```

**You MUST have a regression test for "Rainbow Six Siege" passing the weather filter.**

### G1: Stale Trade Data (Know About It)

The ingestion layer handles this, but your strategies should expect `trade_age_seconds` in context and may want to reject very old data.

### G2: Duplicate Token IDs (Know About It)

Multiple token_ids can map to same market. The core layer handles deduplication, but be aware when reasoning about triggers.

## Directory Structure

```
strategies/
├── __init__.py           # Public exports (ALREADY EXISTS - update it)
├── CLAUDE.md             # This file
├── protocol.py           # Strategy protocol + StrategyContext
├── signals.py            # Signal types (Entry, Exit, Hold, Watchlist)
├── registry.py           # Strategy registration
├── filters/
│   ├── __init__.py
│   ├── hard_filters.py   # Weather, time, category filters
│   └── size_filter.py    # Trade size filter
├── builtin/
│   ├── __init__.py
│   └── high_prob_yes.py  # Reference strategy implementation
└── tests/
    ├── __init__.py
    ├── conftest.py       # Shared fixtures
    ├── test_protocol.py
    ├── test_signals.py
    ├── test_hard_filters.py
    ├── test_size_filter.py
    ├── test_registry.py
    └── test_high_prob_yes.py
```

## Implementation Order (TDD)

Build in this order. For each file: **write tests first**, then implement.

1. `signals.py` + `tests/test_signals.py` - Signal types are foundational
2. `protocol.py` + `tests/test_protocol.py` - Strategy protocol and context
3. `filters/hard_filters.py` + `tests/test_hard_filters.py` - Including G6 fix
4. `filters/size_filter.py` + `tests/test_size_filter.py` - Critical for win rate
5. `registry.py` + `tests/test_registry.py` - Strategy lookup
6. `builtin/high_prob_yes.py` + `tests/test_high_prob_yes.py` - Reference impl

## Key Specifications

### SignalType Enum

```python
class SignalType(Enum):
    ENTRY = "entry"           # Open a position
    EXIT = "exit"             # Close a position
    HOLD = "hold"             # Do nothing
    WATCHLIST = "watchlist"   # Add to watchlist for re-scoring
    IGNORE = "ignore"         # Filter rejected, don't process further
```

### Signal Classes

```python
@dataclass
class Signal:
    """Base signal returned by all strategies."""
    type: SignalType
    reason: str

@dataclass
class EntrySignal(Signal):
    """Signal to open a new position."""
    token_id: str
    side: str  # "BUY" or "SELL"
    price: Decimal
    size: Decimal

@dataclass
class ExitSignal(Signal):
    """Signal to close an existing position."""
    position_id: str

@dataclass
class HoldSignal(Signal):
    """Signal to do nothing (market doesn't meet criteria)."""
    pass

@dataclass
class WatchlistSignal(Signal):
    """Signal to add to watchlist for later re-scoring."""
    token_id: str
    current_score: float

@dataclass
class IgnoreSignal(Signal):
    """Signal that market was filtered out by hard filters."""
    filter_name: str  # Which filter rejected it
```

**IMPORTANT:** `IgnoreSignal` is used when hard filters reject a market BEFORE
strategy evaluation. The `filter_name` field tells you which filter rejected it
(e.g., "weather", "time_to_end", "trade_size").

### StrategyContext (Input to Strategies)

```python
@dataclass
class StrategyContext:
    """All data a strategy needs to make a decision."""
    # Market info
    condition_id: str
    token_id: str
    question: str
    category: Optional[str]

    # Price/trade info
    trigger_price: Decimal
    trade_size: Optional[Decimal]  # May be None (G3 - WebSocket doesn't have it)

    # Timing
    time_to_end_hours: float
    trade_age_seconds: float  # How old is the triggering trade

    # Model score (from external scoring system)
    model_score: Optional[float]

    # Existing position (for exit evaluation)
    current_position: Optional[Position] = None
```

### Strategy Protocol

```python
@runtime_checkable
class Strategy(Protocol):
    """All strategies must implement this interface."""

    @property
    def name(self) -> str:
        """Unique strategy identifier."""
        ...

    def evaluate(self, context: StrategyContext) -> Signal:
        """Evaluate context and return a signal."""
        ...
```

### Hard Filters (Pre-Strategy Rejection)

These run BEFORE strategy evaluation. If they reject, strategy.evaluate() is never called.

```python
def apply_hard_filters(context: StrategyContext) -> tuple[bool, str]:
    """
    Returns (should_reject, reason).

    Filters checked:
    1. Weather market (G6 - use word boundaries!)
    2. Time to end < 6 hours
    3. Category blocklist (if configured)
    """
```

### Size Filter (Critical)

The size >= 50 filter adds **+3.5 percentage points** to win rate (95.7% → 99%+).

```python
def passes_size_filter(trade_size: Optional[Decimal], min_size: int = 50) -> bool:
    """
    Returns True if trade_size >= min_size.
    Returns False if trade_size is None or below threshold.
    """
    if trade_size is None:
        return False
    return trade_size >= min_size
```

## Test Fixtures (conftest.py)

```python
"""Strategy layer test fixtures. Strategies are pure logic - no mocking needed."""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

@pytest.fixture
def base_context():
    """Standard context for testing."""
    return StrategyContext(
        condition_id="0xtest123",
        token_id="tok_yes_abc",
        question="Will BTC hit $100k by end of 2025?",
        category="Crypto",
        trigger_price=Decimal("0.95"),
        trade_size=Decimal("75"),
        time_to_end_hours=720,  # 30 days
        trade_age_seconds=10,
        model_score=0.98,
        current_position=None,
    )

@pytest.fixture
def weather_context(base_context):
    """Context for weather market (should be rejected)."""
    base_context.question = "Will it rain in NYC tomorrow?"
    base_context.category = None  # Often None in API
    return base_context

@pytest.fixture
def rainbow_context(base_context):
    """
    REGRESSION TEST: Rainbow Six is NOT weather.
    Must pass weather filter despite containing 'rain'.
    """
    base_context.question = "Will Team A win Rainbow Six Siege tournament?"
    base_context.category = "Esports"
    return base_context

@pytest.fixture
def expiring_soon_context(base_context):
    """Market expiring in 5 hours (should be rejected)."""
    base_context.time_to_end_hours = 5
    return base_context

@pytest.fixture
def small_trade_context(base_context):
    """Trade size below 50 (should be rejected for high-prob strategy)."""
    base_context.trade_size = Decimal("25")
    return base_context
```

## Running Tests

```bash
# From this directory or project root
pytest tests/ -v

# Specific test file
pytest tests/test_hard_filters.py -v

# Rainbow bug regression test
pytest -k "rainbow" -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing
```

## Definition of Done

- [ ] All signal types implemented with proper fields
- [ ] Strategy protocol is runtime_checkable
- [ ] StrategyContext has all required fields
- [ ] Weather filter uses word boundaries (G6 fix)
- [ ] Rainbow Six regression test passes
- [ ] Size filter boundary tests pass (49=fail, 50=pass, 51=pass)
- [ ] Time filter boundary tests pass
- [ ] Registry prevents duplicate names
- [ ] HighProbYesStrategy demonstrates full pattern
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Coverage > 90%
- [ ] `__init__.py` exports all public interface items

## Notes for Claude

- You are working in `/workspace/src/polymarket_bot/strategies/`
- Storage layer is already implemented - just import from it
- This is pure logic - no database connections, no API calls
- Tests don't need mocks because there's no I/O
- Focus on correctness and edge cases
- The size filter is the most important filter for production win rate
