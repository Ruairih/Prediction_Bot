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

With tiered data architecture:
- Discovery: Scans universe for markets approaching 95¢
- Tier requests: Promotes markets at 93¢+ to Tier 2 (History)
- Tier requests: Promotes markets at 95¢+ to Tier 3 (Trades)
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..filters.size_filter import passes_size_filter
from ..protocol import MarketQuery, StrategyContext, Tier, TierRequest
from ..signals import (
    EntrySignal,
    HoldSignal,
    IgnoreSignal,
    Signal,
    WatchlistSignal,
)

if TYPE_CHECKING:
    from polymarket_bot.storage.models import MarketUniverse


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

    @property
    def default_query(self) -> MarketQuery:
        """
        Default query for market discovery.

        Scans for markets approaching our price threshold.
        We start watching at 93¢ to catch markets before they hit 95¢.
        """
        return MarketQuery(
            min_price=0.93,  # Start watching 2¢ below trigger
            min_volume=5000,  # Need some liquidity
            max_days_to_end=90,  # Not too far out
            min_days_to_end=0.25,  # At least 6 hours remaining
            binary_only=True,  # Only YES/NO markets
            limit=500,
        )

    def discover_markets(
        self, markets: list["MarketUniverse"]
    ) -> list[TierRequest]:
        """
        Scan markets and request tier promotions.

        Promotion logic:
        - >= 95¢: Promote to Tier 3 (full trade data for execution)
        - >= 93¢: Promote to Tier 2 (price history for monitoring)
        """
        requests = []

        for market in markets:
            if market.price is None:
                continue

            # >= 95¢: Ready for execution, need full trade data
            if market.price >= float(self._price_threshold):
                requests.append(
                    TierRequest(
                        condition_id=market.condition_id,
                        tier=Tier.TRADES,
                        reason=f"Price {market.price:.2%} >= {self._price_threshold}, ready for execution",
                    )
                )
            # >= 93¢: Getting close, track price history
            elif market.price >= 0.93:
                requests.append(
                    TierRequest(
                        condition_id=market.condition_id,
                        tier=Tier.HISTORY,
                        reason=f"Price {market.price:.2%} approaching threshold, monitoring",
                    )
                )

        return requests

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
