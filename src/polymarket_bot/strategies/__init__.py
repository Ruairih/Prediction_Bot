"""
Strategies Layer - Pluggable trading strategy interface.

This module provides:
    - Strategy: Protocol defining the strategy interface
    - StrategyContext: Data class with all inputs for strategy evaluation
    - Signal types: EntrySignal, ExitSignal, HoldSignal, WatchlistSignal, IgnoreSignal
    - StrategyRegistry: Dynamic strategy registration and lookup
    - Hard filters: Weather (G6 fix), time-to-end, category filters
    - Size filter: Trade size >= 50 filter for high win rate

Critical Gotchas Handled:
    - G6: Rainbow Bug - Use word boundaries in weather filter regex

Design Principle:
    Strategies are PURE LOGIC - no database access, no API calls.
    They receive a StrategyContext and return a Signal.
    This makes them trivial to test without mocks.
"""

# Signals
from .signals import (
    EntrySignal,
    ExitSignal,
    HoldSignal,
    IgnoreSignal,
    Signal,
    SignalType,
    WatchlistSignal,
)

# Protocol and context
from .protocol import Strategy, StrategyContext

# Registry
from .registry import (
    DuplicateStrategyError,
    StrategyNotFoundError,
    StrategyRegistry,
    get_default_registry,
    get_strategy,
    register_strategy,
)

# Filters
from .filters import (
    BLOCKED_CATEGORIES,
    WEATHER_PATTERN,
    apply_hard_filters,
    check_category_filter,
    check_time_filter,
    check_trade_age_filter,
    is_weather_market,
    passes_size_filter,
)

# Built-in strategies
from .builtin import HighProbYesStrategy

__all__ = [
    # Signals
    "Signal",
    "SignalType",
    "EntrySignal",
    "ExitSignal",
    "HoldSignal",
    "WatchlistSignal",
    "IgnoreSignal",
    # Protocol
    "Strategy",
    "StrategyContext",
    # Registry
    "StrategyRegistry",
    "StrategyNotFoundError",
    "DuplicateStrategyError",
    "get_default_registry",
    "register_strategy",
    "get_strategy",
    # Filters
    "apply_hard_filters",
    "is_weather_market",
    "check_time_filter",
    "check_category_filter",
    "check_trade_age_filter",
    "passes_size_filter",
    "WEATHER_PATTERN",
    "BLOCKED_CATEGORIES",
    # Built-in strategies
    "HighProbYesStrategy",
]
