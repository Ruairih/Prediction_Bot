"""
High Probability Yes Strategy - Reference Implementation.

This is the flagship strategy for the trading bot. It targets markets
where the "Yes" outcome is trading at a high probability (>= 0.95)
and has a high model score.

The strategy logic:
1. Only considers prices >= 0.95 (high confidence)
2. Requires model_score >= 0.97 for immediate entry
3. Adds to watchlist if score is 0.90-0.97 (may improve)
4. Applies size filter (>= 50) for better win rate
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..filters.size_filter import passes_size_filter
from ..protocol import StrategyContext
from ..signals import (
    EntrySignal,
    HoldSignal,
    IgnoreSignal,
    Signal,
    WatchlistSignal,
)

if TYPE_CHECKING:
    pass


class HighProbYesStrategy:
    """
    Strategy that trades high-probability "Yes" outcomes.

    Configuration:
        price_threshold: Minimum price to consider (default 0.95)
        entry_score_threshold: Minimum score for immediate entry (default 0.97)
        watchlist_score_min: Minimum score for watchlist (default 0.90)
        position_size: Default position size in dollars (default 20)
        require_size_filter: Whether to apply size >= 50 filter (default True)

    Signal Logic:
        - ENTRY: price >= 0.95 AND model_score >= 0.97 AND size >= 50
        - WATCHLIST: price >= 0.95 AND 0.90 <= model_score < 0.97
        - HOLD: price < 0.95 OR score < 0.90
        - IGNORE: size filter fails (if required)
    """

    def __init__(
        self,
        price_threshold: Decimal = Decimal("0.95"),
        entry_score_threshold: float = 0.97,
        watchlist_score_min: float = 0.90,
        position_size: Decimal = Decimal("20"),
        require_size_filter: bool = True,
    ) -> None:
        self._price_threshold = price_threshold
        self._entry_score_threshold = entry_score_threshold
        self._watchlist_score_min = watchlist_score_min
        self._position_size = position_size
        self._require_size_filter = require_size_filter

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "high_prob_yes"

    def evaluate(self, context: StrategyContext) -> Signal:
        """
        Evaluate the context and return a trading signal.

        Args:
            context: Market data and state for decision making

        Returns:
            Signal indicating what action to take
        """
        # Check price threshold first
        if context.trigger_price < self._price_threshold:
            return HoldSignal(
                reason=f"Price {context.trigger_price} < {self._price_threshold}"
            )

        # Apply size filter if required
        if self._require_size_filter:
            if not passes_size_filter(context.trade_size):
                return IgnoreSignal(
                    reason=f"Trade size {context.trade_size} below minimum",
                    filter_name="trade_size",
                )

        # Check model score
        if context.model_score is None:
            return HoldSignal(reason="No model score available")

        # High score → Entry
        if context.model_score >= self._entry_score_threshold:
            return EntrySignal(
                reason=f"High probability entry (score={context.model_score:.2f})",
                token_id=context.token_id,
                side="BUY",
                price=context.trigger_price,
                size=self._position_size,
            )

        # Medium score → Watchlist
        if context.model_score >= self._watchlist_score_min:
            return WatchlistSignal(
                reason=f"Score {context.model_score:.2f} below entry threshold, watching",
                token_id=context.token_id,
                current_score=context.model_score,
            )

        # Low score → Hold
        return HoldSignal(
            reason=f"Score {context.model_score:.2f} below watchlist threshold"
        )

    def __repr__(self) -> str:
        return (
            f"HighProbYesStrategy("
            f"price={self._price_threshold}, "
            f"entry_score={self._entry_score_threshold}, "
            f"watchlist_min={self._watchlist_score_min})"
        )
