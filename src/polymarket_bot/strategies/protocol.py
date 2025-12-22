"""
Strategy protocol and context definitions.

Strategies are pure logic - they receive a StrategyContext and return a Signal.
No database access, no API calls. This makes them trivial to test.

With the tiered data architecture, strategies can also:
- Define discovery queries for scanning the market universe
- Request specific markets be promoted to higher tiers
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from polymarket_bot.storage.models import Position, MarketUniverse

from .signals import Signal


class Tier(IntEnum):
    """Data tier levels for market monitoring."""

    UNIVERSE = 1  # Metadata only (all markets)
    HISTORY = 2  # Price candles (interesting markets)
    TRADES = 3  # Full trade data (active markets)


@dataclass
class MarketQuery:
    """Query parameters for market discovery in the universe."""

    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[float] = None
    max_volume: Optional[float] = None
    categories: Optional[list[str]] = None
    exclude_categories: Optional[list[str]] = None
    min_interestingness: Optional[float] = None
    max_days_to_end: Optional[float] = None
    min_days_to_end: Optional[float] = None
    min_market_age_days: Optional[float] = None
    max_market_age_days: Optional[float] = None
    binary_only: bool = False
    limit: int = 100


@dataclass
class TierRequest:
    """Request to promote a market to a specific tier."""

    condition_id: str
    tier: Tier
    reason: str


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

    With tiered data architecture, strategies can also:
    - Define discovery queries for scanning the market universe
    - Request specific markets be promoted to higher tiers

    Example implementation:
        class MyStrategy:
            @property
            def name(self) -> str:
                return "my_strategy"

            @property
            def default_query(self) -> MarketQuery:
                return MarketQuery(min_price=0.93, min_volume=5000)

            def discover_markets(self, markets: list[MarketUniverse]) -> list[TierRequest]:
                requests = []
                for m in markets:
                    if m.price and m.price >= 0.95:
                        requests.append(TierRequest(m.condition_id, Tier.TRADES, "Ready"))
                return requests

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

    @property
    def default_query(self) -> MarketQuery:
        """
        Default query for market discovery.

        Override to customize which markets this strategy scans.
        Called periodically (every 15 min) to discover new opportunities.
        """
        ...

    def discover_markets(self, markets: list["MarketUniverse"]) -> list[TierRequest]:
        """
        Scan markets from the universe and request tier promotions.

        Called periodically with markets matching default_query.
        Returns list of markets that should be promoted for closer monitoring.

        Args:
            markets: Markets from universe matching default_query

        Returns:
            List of TierRequest for markets needing promotion
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
