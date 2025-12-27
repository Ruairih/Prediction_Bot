# Strategies Layer

## You Are

A **strategy developer** implementing trading strategies for a Polymarket trading bot. Strategies are **pure logic** - no database access, no API calls. You receive data and return decisions. This makes strategies trivial to test and easy to reason about.

---

## Known Architectural Issue: Exit Logic

> **See:** `docs/reference/ADR-001-exit-strategy-architecture.md`

**Current state:** Exit logic (profit target, stop loss, hold period) is hardcoded in the framework layer (`ExitManager`), NOT in strategies. This means:
- All strategies use the same exit rules
- Strategies cannot opt-out of auto-exits
- Entry is strategy-driven but exit is framework-driven (inconsistent)

**Planned fix:** Move exit decisions into strategies via `ExitStrategy` protocol. For now, be aware that your strategy's `ExitSignal` from `evaluate()` only works for event-driven exits - the background exit loop uses hardcoded rules.

---

## Quick Start: Creating a New Strategy

Copy this template and modify:

```python
"""
my_strategy.py - Brief description of what this strategy does.
"""
from decimal import Decimal
from typing import TYPE_CHECKING

from polymarket_bot.strategies import (
    Strategy,
    StrategyContext,
    Signal,
    EntrySignal,
    ExitSignal,
    HoldSignal,
    WatchlistSignal,
    MarketQuery,
    TierRequest,
    Tier,
)

if TYPE_CHECKING:
    from polymarket_bot.storage.models import MarketUniverse


class MyStrategy:
    """
    One-line description of the strategy.

    Longer description of:
    - What markets this targets
    - Entry/exit criteria
    - Key configuration options
    """

    def __init__(
        self,
        price_threshold: Decimal = Decimal("0.90"),
        position_size: Decimal = Decimal("20"),
    ) -> None:
        self._price_threshold = price_threshold
        self._position_size = position_size

    @property
    def name(self) -> str:
        """Unique identifier for this strategy."""
        return "my_strategy"

    @property
    def default_query(self) -> MarketQuery:
        """Query for discovering markets from the universe."""
        return MarketQuery(
            min_price=0.85,  # Start watching before threshold
            min_volume=1000,
            max_days_to_end=30,
            min_days_to_end=0.25,  # At least 6 hours
            binary_only=True,
            limit=200,
        )

    def discover_markets(self, markets: list["MarketUniverse"]) -> list[TierRequest]:
        """
        Scan markets and request tier promotions.

        Called periodically (~15 min) with markets matching default_query.
        Returns markets that need closer monitoring.
        """
        requests = []
        for market in markets:
            if market.price is None:
                continue
            if market.price >= float(self._price_threshold):
                requests.append(TierRequest(
                    condition_id=market.condition_id,
                    tier=Tier.TRADES,
                    reason=f"Price {market.price:.2%} at threshold",
                ))
        return requests

    def evaluate(self, context: StrategyContext) -> Signal:
        """
        Core decision logic. Called when a trade event occurs.

        Returns one of: EntrySignal, ExitSignal, HoldSignal, WatchlistSignal
        """
        # Check for exit conditions first (if we have a position)
        if context.current_position:
            return self._evaluate_exit(context)

        # Entry logic
        if context.trigger_price >= self._price_threshold:
            if context.model_score and context.model_score >= 0.95:
                return EntrySignal(
                    reason=f"Price {context.trigger_price}, score {context.model_score:.2f}",
                    token_id=context.token_id,
                    side="BUY",
                    price=context.trigger_price,
                    size=self._position_size,
                )

        return HoldSignal(reason="Criteria not met")

    def _evaluate_exit(self, context: StrategyContext) -> Signal:
        """Exit logic for existing positions."""
        pos = context.current_position

        # Example: Exit at profit target
        if context.trigger_price >= Decimal("0.99"):
            return ExitSignal(
                reason=f"Profit target reached at {context.trigger_price}",
                position_id=str(pos.id),
            )

        # Example: Stop loss
        if context.trigger_price < Decimal("0.80"):
            return ExitSignal(
                reason=f"Stop loss triggered at {context.trigger_price}",
                position_id=str(pos.id),
            )

        return HoldSignal(reason="Holding position")
```

**Register your strategy:**

```python
from polymarket_bot.strategies import register_strategy
from .my_strategy import MyStrategy

register_strategy(MyStrategy())

# Or use via environment variable:
# STRATEGY_NAME=my_strategy python -m polymarket_bot.main
```

---

## Broader System Context

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
                    │   STORAGE   │
                    └─────────────┘
```

**Your component's role**: Receive market data via `StrategyContext`, apply logic, return `Signal`. No side effects.

---

## Strategy Lifecycle: How Your Code Gets Called

Understanding when and how your strategy methods are called:

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGY LIFECYCLE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. STARTUP                                                      │
│     └─▶ Strategy loaded from registry by name                   │
│                                                                  │
│  2. DISCOVERY PHASE (every ~15 minutes)                          │
│     └─▶ Core calls: strategy.default_query                       │
│         └─▶ Fetches matching markets from universe               │
│             └─▶ Core calls: strategy.discover_markets(markets)   │
│                 └─▶ Your code requests tier promotions           │
│                                                                  │
│  3. EVALUATION PHASE (on each trade event)                       │
│     └─▶ Trade event arrives (WebSocket or REST)                  │
│         └─▶ Core applies HARD FILTERS (weather, time, age)       │
│             └─▶ If passes: Core builds StrategyContext           │
│                 └─▶ Core calls: strategy.evaluate(context)       │
│                     └─▶ Your code returns Signal                 │
│                                                                  │
│  4. SIGNAL HANDLING (by Core/Execution)                          │
│     └─▶ EntrySignal  → Order submitted to CLOB                  │
│     └─▶ ExitSignal   → Position closed                          │
│     └─▶ WatchlistSignal → Added to watchlist for re-scoring     │
│     └─▶ HoldSignal   → Nothing happens                          │
│     └─▶ IgnoreSignal → Logged, no action                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Points:**
- `evaluate()` is called for EACH trade event that passes hard filters
- You may receive many calls per second during active trading
- `discover_markets()` is called periodically, not on every event
- Hard filters run BEFORE your strategy - you won't see filtered markets

---

## Tiered Data Architecture

Strategies can request different levels of data monitoring for markets:

```python
class Tier(IntEnum):
    UNIVERSE = 1  # Metadata only (all ~3000 markets)
    HISTORY = 2   # Price candles (interesting markets, ~200)
    TRADES = 3    # Full trade data (active targets, ~20)
```

**How it works:**

1. **Tier 1 (Universe)**: All markets have basic metadata (question, category, end date, last price)
2. **Tier 2 (History)**: Markets you want to watch get 1-minute candles
3. **Tier 3 (Trades)**: Markets ready for execution get full trade stream

**Your role:**
- Define `default_query` to scan the universe
- Use `discover_markets()` to promote markets to higher tiers
- Only Tier 3 markets trigger `evaluate()` calls with full trade data

```python
@property
def default_query(self) -> MarketQuery:
    """What markets to scan from the universe."""
    return MarketQuery(
        min_price=0.93,        # Only high-probability
        min_volume=5000,       # Needs liquidity
        max_days_to_end=90,    # Not too far out
        min_days_to_end=0.25,  # At least 6 hours (hard filter)
        binary_only=True,      # Only YES/NO markets
        limit=500,
    )

def discover_markets(self, markets: list[MarketUniverse]) -> list[TierRequest]:
    """Promote interesting markets to higher tiers."""
    requests = []
    for m in markets:
        if m.price and m.price >= 0.95:
            # Ready for trading - need full trade data
            requests.append(TierRequest(m.condition_id, Tier.TRADES, "At threshold"))
        elif m.price and m.price >= 0.93:
            # Getting close - track price history
            requests.append(TierRequest(m.condition_id, Tier.HISTORY, "Approaching"))
    return requests
```

---

## Public Interface (What's Exported)

Your `__init__.py` imports these - you can use them directly:

```python
from polymarket_bot.strategies import (
    # Signals
    Signal,
    SignalType,
    EntrySignal,
    ExitSignal,
    HoldSignal,
    WatchlistSignal,
    IgnoreSignal,

    # Protocol and context
    Strategy,
    StrategyContext,

    # Tiered data architecture
    Tier,
    MarketQuery,
    TierRequest,

    # Registry
    StrategyRegistry,
    StrategyNotFoundError,
    DuplicateStrategyError,
    get_default_registry,
    register_strategy,
    get_strategy,

    # Filters (use in your strategy if needed)
    apply_hard_filters,
    is_weather_market,
    check_time_filter,
    check_category_filter,
    check_trade_age_filter,
    passes_size_filter,
    WEATHER_PATTERN,
    BLOCKED_CATEGORIES,

    # Built-in strategy (reference implementation)
    HighProbYesStrategy,
)
```

---

## StrategyContext: Your Input Data

This is everything you receive for making a decision:

```python
@dataclass
class StrategyContext:
    # Market identification
    condition_id: str              # Unique market ID
    token_id: str                  # Token being traded
    question: str                  # "Will X happen by Y?"
    category: Optional[str]        # "Crypto", "Politics", etc.

    # Price and trade info
    trigger_price: Decimal         # Price that triggered this evaluation
    trade_size: Optional[Decimal]  # Size of triggering trade (may be None - see G3)

    # Timing
    time_to_end_hours: float       # Hours until market resolves
    trade_age_seconds: float       # Age of triggering trade (G1 protection)

    # Scoring
    model_score: Optional[float]   # External model's probability estimate

    # Position state (for exit evaluation)
    current_position: Optional[Position] = None

    # Outcome info
    outcome: Optional[str] = None      # "Yes" or "No"
    outcome_index: Optional[int] = None  # 0 or 1
```

**Common patterns:**

```python
def evaluate(self, context: StrategyContext) -> Signal:
    # Check if we're evaluating entry or exit
    if context.current_position:
        return self._evaluate_exit(context)

    # Access price (Decimal - use for comparisons)
    if context.trigger_price >= Decimal("0.95"):
        ...

    # Access model score (may be None!)
    if context.model_score and context.model_score >= 0.97:
        ...

    # Access trade size (may be None due to G3!)
    if context.trade_size and context.trade_size >= 50:
        ...

    # Access timing
    if context.time_to_end_hours < 24:
        ...  # Market resolving soon
```

---

## Signal Types: Your Output

All signals are **frozen dataclasses** (immutable). Here's how to create each:

```python
# ENTRY: Open a new position
return EntrySignal(
    reason="High probability entry (score=0.98)",
    token_id=context.token_id,
    side="BUY",  # or "SELL"
    price=context.trigger_price,
    size=Decimal("20"),  # Position size in dollars
)

# EXIT: Close an existing position
return ExitSignal(
    reason="Profit target reached at 0.99",
    position_id=str(context.current_position.id),
)

# HOLD: Do nothing (criteria not met, but not rejected)
return HoldSignal(reason="Score too low (0.85)")

# WATCHLIST: Track for later (promising but not ready)
return WatchlistSignal(
    reason="Score 0.94, watching for improvement",
    token_id=context.token_id,
    current_score=context.model_score,
)

# IGNORE: Filtered out (use for strategy-specific filters)
return IgnoreSignal(
    reason="Trade size below minimum",
    filter_name="trade_size",
)
```

---

## Entry vs Exit Logic

Strategies handle **both** entry and exit decisions. The pattern:

```python
def evaluate(self, context: StrategyContext) -> Signal:
    # ROUTE: Entry or Exit?
    if context.current_position is not None:
        return self._evaluate_exit(context)
    return self._evaluate_entry(context)

def _evaluate_entry(self, context: StrategyContext) -> Signal:
    """Decide whether to open a new position."""
    # Your entry logic here
    if meets_entry_criteria(context):
        return EntrySignal(...)
    return HoldSignal(reason="Entry criteria not met")

def _evaluate_exit(self, context: StrategyContext) -> Signal:
    """Decide whether to close an existing position."""
    pos = context.current_position

    # Profit target
    if context.trigger_price >= Decimal("0.99"):
        return ExitSignal(
            reason="Profit target",
            position_id=str(pos.id),
        )

    # Stop loss
    if context.trigger_price <= pos.entry_price - Decimal("0.10"):
        return ExitSignal(
            reason="Stop loss",
            position_id=str(pos.id),
        )

    # Time-based exit
    if pos.created_at and (datetime.now() - pos.created_at).days > 30:
        return ExitSignal(
            reason="Max hold time exceeded",
            position_id=str(pos.id),
        )

    return HoldSignal(reason="Holding position")
```

**Position Fields Available** (when `context.current_position` is set):
- `id`: Position identifier
- `token_id`: Token being held
- `entry_price`: Price we entered at
- `size`: Position size
- `side`: "BUY" or "SELL"
- `created_at`: When position was opened

---

## Configuration Best Practices

Make your strategy configurable via `__init__`:

```python
class MyStrategy:
    """
    Strategy with configurable parameters.

    Configuration:
        price_threshold: Minimum price to trigger (default 0.95)
        entry_score: Minimum model score for entry (default 0.97)
        watchlist_score: Minimum score for watchlist (default 0.90)
        position_size: Default position size in dollars (default 20)
        require_size_filter: Whether trade size >= 50 is required (default True)
    """

    def __init__(
        self,
        price_threshold: Decimal = Decimal("0.95"),
        entry_score: float = 0.97,
        watchlist_score: float = 0.90,
        position_size: Decimal = Decimal("20"),
        require_size_filter: bool = True,
    ) -> None:
        self._price_threshold = price_threshold
        self._entry_score = entry_score
        self._watchlist_score = watchlist_score
        self._position_size = position_size
        self._require_size_filter = require_size_filter
```

**Best practices:**
1. Use descriptive parameter names
2. Provide sensible defaults
3. Document each parameter in the docstring
4. Use private attributes (`self._param`) to store config
5. Make parameters affect behavior, not structure

---

## Hard Filters (Run Before Your Strategy)

These filters reject markets BEFORE `evaluate()` is called:

| Filter | Rule | Gotcha |
|--------|------|--------|
| Trade age | < 300 seconds | G1: "Recent" trades can be months old |
| Weather | Word-boundary regex | G6: "Rainbow Six" isn't weather |
| Time to end | > 6 hours remaining | Markets need resolution time |
| Category | Not in blocklist | Blocks "Weather", "Adult" |

**You don't need to implement these** - they run automatically. But know they exist!

If you need custom filtering, return `IgnoreSignal` from your strategy:

```python
def evaluate(self, context: StrategyContext) -> Signal:
    # Custom filter: require minimum trade size
    if not passes_size_filter(context.trade_size, min_size=50):
        return IgnoreSignal(
            reason="Trade size below minimum",
            filter_name="trade_size",
        )

    # Continue with normal logic...
```

---

## Critical Gotchas

### G6: Rainbow Bug (CRITICAL)

"Rainbow Six Siege" was blocked as weather because it contained "rain".

```python
# WRONG - substring match
if "rain" in question.lower():
    block_as_weather()

# RIGHT - word boundary match (what is_weather_market does)
import re
WEATHER_PATTERN = r'\b(rain|snow|hurricane|storm)\b'
if re.search(WEATHER_PATTERN, question, re.IGNORECASE):
    block_as_weather()
```

**The `is_weather_market()` function handles this correctly. Use it if you need weather detection.**

### G1: Stale Trade Data

Polymarket's "recent trades" can be months old for low-volume markets.

- The `trade_age_seconds` field in context tells you how old the trade is
- Hard filters reject trades > 300 seconds old
- If you bypass hard filters, check age yourself!

### G3: WebSocket Missing Trade Size

WebSocket price updates don't include trade size.

- `context.trade_size` may be `None`
- Always check before using: `if context.trade_size and context.trade_size >= 50`

---

## Testing Your Strategy

Strategies are pure logic - test without mocks:

```python
"""tests/test_my_strategy.py"""
import pytest
from decimal import Decimal
from polymarket_bot.strategies import StrategyContext, SignalType
from .my_strategy import MyStrategy


@pytest.fixture
def strategy():
    """Strategy with default configuration."""
    return MyStrategy()


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


class TestEntryLogic:
    """Test entry signal generation."""

    def test_entry_when_criteria_met(self, strategy, base_context):
        """Should enter when price and score thresholds met."""
        signal = strategy.evaluate(base_context)

        assert signal.type == SignalType.ENTRY
        assert "0.98" in signal.reason  # Score mentioned
        assert signal.token_id == base_context.token_id

    def test_hold_when_price_too_low(self, strategy, base_context):
        """Should hold when price below threshold."""
        base_context.trigger_price = Decimal("0.90")

        signal = strategy.evaluate(base_context)

        assert signal.type == SignalType.HOLD
        assert "0.90" in signal.reason

    def test_hold_when_score_too_low(self, strategy, base_context):
        """Should hold when model score below threshold."""
        base_context.model_score = 0.85

        signal = strategy.evaluate(base_context)

        assert signal.type == SignalType.HOLD

    def test_handles_missing_model_score(self, strategy, base_context):
        """Should handle None model score gracefully."""
        base_context.model_score = None

        signal = strategy.evaluate(base_context)

        assert signal.type == SignalType.HOLD


class TestExitLogic:
    """Test exit signal generation."""

    @pytest.fixture
    def context_with_position(self, base_context):
        """Context with an existing position."""
        from unittest.mock import MagicMock
        position = MagicMock()
        position.id = 123
        position.entry_price = Decimal("0.95")
        base_context.current_position = position
        return base_context

    def test_exit_at_profit_target(self, strategy, context_with_position):
        """Should exit when profit target reached."""
        context_with_position.trigger_price = Decimal("0.99")

        signal = strategy.evaluate(context_with_position)

        assert signal.type == SignalType.EXIT
        assert signal.position_id == "123"

    def test_exit_at_stop_loss(self, strategy, context_with_position):
        """Should exit when stop loss hit."""
        context_with_position.trigger_price = Decimal("0.80")

        signal = strategy.evaluate(context_with_position)

        assert signal.type == SignalType.EXIT

    def test_hold_position_in_range(self, strategy, context_with_position):
        """Should hold when price in acceptable range."""
        context_with_position.trigger_price = Decimal("0.96")

        signal = strategy.evaluate(context_with_position)

        assert signal.type == SignalType.HOLD


class TestConfiguration:
    """Test configurable behavior."""

    def test_custom_price_threshold(self, base_context):
        """Strategy respects custom price threshold."""
        strategy = MyStrategy(price_threshold=Decimal("0.90"))
        base_context.trigger_price = Decimal("0.92")

        signal = strategy.evaluate(base_context)

        assert signal.type == SignalType.ENTRY

    def test_custom_position_size(self, base_context):
        """Entry signal uses configured position size."""
        strategy = MyStrategy(position_size=Decimal("50"))

        signal = strategy.evaluate(base_context)

        assert signal.size == Decimal("50")


class TestRainbowBugRegression:
    """G6: Ensure Rainbow Six isn't blocked as weather."""

    def test_rainbow_six_passes_weather_filter(self):
        from polymarket_bot.strategies import is_weather_market

        # This MUST pass (return False = not weather)
        assert is_weather_market("Will Team A win Rainbow Six Siege?") is False

        # These MUST be blocked (return True = is weather)
        assert is_weather_market("Will it rain in NYC tomorrow?") is True
        assert is_weather_market("Hurricane makes landfall?") is True
```

**Run tests:**

```bash
pytest src/polymarket_bot/strategies/tests/ -v
pytest -k "rainbow" -v  # Regression test
pytest --cov=src/polymarket_bot/strategies --cov-report=term-missing
```

---

## Directory Structure

```
strategies/
├── __init__.py           # Public exports
├── CLAUDE.md             # This file
├── protocol.py           # Strategy protocol, StrategyContext, Tier types
├── signals.py            # Signal types (Entry, Exit, Hold, etc.)
├── registry.py           # Strategy registration and lookup
├── filters/
│   ├── __init__.py       # Filter exports
│   ├── hard_filters.py   # Weather (G6), time, category, trade age (G1)
│   └── size_filter.py    # Trade size filter
├── builtin/
│   ├── __init__.py
│   └── high_prob_yes.py  # Reference implementation
└── tests/
    ├── __init__.py
    ├── conftest.py       # Shared fixtures
    ├── test_signals.py
    ├── test_protocol.py
    ├── test_filters.py
    └── test_high_prob_yes.py
```

---

## Checklist: Before Submitting Your Strategy

- [ ] `name` property returns a unique identifier
- [ ] `default_query` defines what markets to scan
- [ ] `discover_markets` promotes markets to appropriate tiers
- [ ] `evaluate` handles both entry and exit (check `current_position`)
- [ ] Entry signals include all required fields (token_id, side, price, size)
- [ ] Exit signals reference valid position_id
- [ ] Handles `None` values gracefully (model_score, trade_size)
- [ ] Configuration via `__init__` with sensible defaults
- [ ] Tests cover entry, exit, edge cases, and configuration
- [ ] Rainbow Six regression test passes (G6)
- [ ] Strategy registered in registry

---

## Reference: HighProbYesStrategy

See `builtin/high_prob_yes.py` for a complete, production-ready example showing:
- Tiered discovery with progressive promotion
- Entry logic with score thresholds
- Watchlist for promising-but-not-ready markets
- Configuration with reasonable defaults
- Complete docstrings

---

## Need Help?

1. **Interface questions**: Check `protocol.py` for exact signatures
2. **Signal questions**: Check `signals.py` for field requirements
3. **Filter behavior**: Check `filters/hard_filters.py`
4. **Registration**: Check `registry.py` for how strategies are loaded
5. **Real example**: Study `builtin/high_prob_yes.py`
