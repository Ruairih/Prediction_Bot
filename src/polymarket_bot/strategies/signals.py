"""
Signal types returned by strategies.

Signals represent the decision made by a strategy. They are immutable
data classes that the core layer uses to determine next actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


class SignalType(Enum):
    """Types of signals a strategy can emit."""

    ENTRY = "entry"  # Open a position
    EXIT = "exit"  # Close a position
    HOLD = "hold"  # Do nothing
    WATCHLIST = "watchlist"  # Add to watchlist for re-scoring
    IGNORE = "ignore"  # Filter rejected, don't process further


@dataclass(frozen=True)
class Signal:
    """
    Base signal returned by all strategies.

    All signals have a type and a reason explaining the decision.
    """

    type: SignalType
    reason: str


@dataclass(frozen=True)
class EntrySignal(Signal):
    """
    Signal to open a new position.

    Includes all information needed to execute the trade.
    """

    type: SignalType = field(default=SignalType.ENTRY, init=False)
    token_id: str = ""
    side: str = "BUY"  # "BUY" or "SELL"
    price: Decimal = Decimal("0")
    size: Decimal = Decimal("0")


@dataclass(frozen=True)
class ExitSignal(Signal):
    """
    Signal to close an existing position.

    References the position to close and the reason.
    """

    type: SignalType = field(default=SignalType.EXIT, init=False)
    position_id: int = 0


@dataclass(frozen=True)
class HoldSignal(Signal):
    """
    Signal to do nothing.

    Market doesn't meet criteria but isn't rejected by filters.
    """

    type: SignalType = field(default=SignalType.HOLD, init=False)


@dataclass(frozen=True)
class WatchlistSignal(Signal):
    """
    Signal to add to watchlist for later re-scoring.

    Used when score is promising but below threshold (e.g., 0.90-0.97).
    """

    type: SignalType = field(default=SignalType.WATCHLIST, init=False)
    token_id: str = ""
    current_score: float = 0.0


@dataclass(frozen=True)
class IgnoreSignal(Signal):
    """
    Signal that market was filtered out by hard filters.

    This means the market was rejected BEFORE strategy evaluation.
    The filter_name tells you which filter rejected it.
    """

    type: SignalType = field(default=SignalType.IGNORE, init=False)
    filter_name: str = ""  # e.g., "weather", "time_to_end", "trade_size"
