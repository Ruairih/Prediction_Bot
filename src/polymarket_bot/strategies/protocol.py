"""
Strategy protocol and context definitions.

Strategies are pure logic - they receive a StrategyContext and return a Signal.
No database access, no API calls. This makes them trivial to test.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from polymarket_bot.storage.models import Position

from .signals import Signal


@dataclass
class StrategyContext:
    """
    All data a strategy needs to make a decision.

    This is the complete input to strategy.evaluate().
    The core layer builds this from events and database lookups.
    """

    # Market identification
    condition_id: str
    token_id: str
    question: str
    category: Optional[str]

    # Price and trade info
    trigger_price: Decimal
    trade_size: Optional[Decimal]  # May be None (G3 - WebSocket doesn't have it)

    # Timing
    time_to_end_hours: float
    trade_age_seconds: float  # How old is the triggering trade (G1 protection)

    # Model score (from external scoring system)
    model_score: Optional[float]

    # Existing position (for exit evaluation)
    current_position: Optional["Position"] = None

    # Outcome info
    outcome: Optional[str] = None  # "Yes" or "No"
    outcome_index: Optional[int] = None  # 0 or 1


@runtime_checkable
class Strategy(Protocol):
    """
    Protocol that all strategies must implement.

    Strategies are designed to be:
    - Pure: No side effects, no I/O
    - Testable: No mocks needed since there's no I/O
    - Pluggable: Swap strategies without changing core logic

    Example implementation:
        class MyStrategy:
            @property
            def name(self) -> str:
                return "my_strategy"

            def evaluate(self, context: StrategyContext) -> Signal:
                if context.model_score and context.model_score > 0.97:
                    return EntrySignal(...)
                return HoldSignal(reason="Score too low")
    """

    @property
    def name(self) -> str:
        """
        Unique strategy identifier.

        Used for logging, metrics, and strategy selection.
        """
        ...

    def evaluate(self, context: StrategyContext) -> Signal:
        """
        Evaluate the context and return a trading signal.

        Args:
            context: All market and position data needed for decision

        Returns:
            Signal indicating what action to take (Entry, Exit, Hold, etc.)
        """
        ...
