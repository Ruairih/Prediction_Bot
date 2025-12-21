"""
Event processor for parsing and filtering incoming events.

Handles the transformation from raw WebSocket/ingestion events
to StrategyContext objects that strategies can evaluate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

from polymarket_bot.strategies import StrategyContext, apply_hard_filters


@dataclass
class TriggerData:
    """Extracted trigger information from an event."""

    token_id: str
    condition_id: str
    price: Decimal
    size: Optional[Decimal]
    timestamp: datetime
    trade_age_seconds: float


class EventProcessor:
    """
    Processes incoming events and builds strategy contexts.

    Responsibilities:
    1. Filter events by type (only process price changes)
    2. Extract trigger information from events
    3. Validate price threshold
    4. Build complete StrategyContext from event + database lookups
    5. Apply hard filters before strategy evaluation
    """

    # Event types we process
    PROCESSABLE_TYPES = frozenset(["price_change", "trade", "price_update"])

    def __init__(
        self,
        threshold: Decimal = Decimal("0.95"),
        max_trade_age_seconds: float = 300.0,
    ) -> None:
        """
        Initialize the event processor.

        Args:
            threshold: Minimum price to consider for triggers
            max_trade_age_seconds: Maximum age of trade to process (G1)
        """
        self._threshold = threshold
        self._max_trade_age_seconds = max_trade_age_seconds

    def should_process(self, event: dict[str, Any]) -> bool:
        """
        Check if an event should be processed.

        Args:
            event: Raw event from WebSocket/ingestion

        Returns:
            True if this event type should be processed
        """
        event_type = event.get("type", event.get("event_type", ""))
        return event_type in self.PROCESSABLE_TYPES

    def extract_trigger(self, event: dict[str, Any]) -> Optional[TriggerData]:
        """
        Extract trigger information from an event.

        Args:
            event: Raw event data

        Returns:
            TriggerData if extraction successful, None otherwise
        """
        try:
            # Handle different event formats
            token_id = event.get("token_id", event.get("asset_id", ""))
            condition_id = event.get("condition_id", "")

            # Parse price
            price_str = event.get("price", "0")
            price = Decimal(str(price_str))

            # Parse size (may be None - G3)
            size_str = event.get("size", event.get("trade_size"))
            size = Decimal(str(size_str)) if size_str else None

            # Parse timestamp - G1 protection: reject events without valid timestamps
            ts = event.get("timestamp")
            if isinstance(ts, datetime):
                timestamp = ts
            elif isinstance(ts, (int, float)):
                # Assume milliseconds if > year 2100 in seconds
                if ts > 4102444800:
                    ts = ts / 1000
                timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                # Try parsing ISO format string
                try:
                    timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    # G1: Reject events with unparseable timestamp to prevent stale trades
                    return None
            else:
                # G1: Reject events without timestamp - prevents Belichick bug
                # where stale trades appear fresh by defaulting to now()
                return None

            # Calculate trade age
            now = datetime.now(timezone.utc)
            trade_age_seconds = (now - timestamp).total_seconds()

            return TriggerData(
                token_id=token_id,
                condition_id=condition_id,
                price=price,
                size=size,
                timestamp=timestamp,
                trade_age_seconds=max(0, trade_age_seconds),
            )

        except (ValueError, KeyError, TypeError):
            return None

    def meets_threshold(self, price: Decimal) -> bool:
        """
        Check if price meets the threshold for triggering.

        Args:
            price: The price to check

        Returns:
            True if price >= threshold
        """
        return price >= self._threshold

    async def build_context(
        self,
        event: dict[str, Any],
        db: "Database",
        trigger_data: Optional[TriggerData] = None,
    ) -> Optional[StrategyContext]:
        """
        Build a complete StrategyContext from an event.

        Fetches additional data from the database as needed.

        Args:
            event: Raw event data
            db: Database for lookups
            trigger_data: Pre-extracted trigger data (optional)

        Returns:
            StrategyContext if successful, None otherwise
        """
        if trigger_data is None:
            trigger_data = self.extract_trigger(event)

        if trigger_data is None:
            return None

        # Fetch token metadata
        query = """
            SELECT question, outcome, outcome_index, market_id
            FROM polymarket_token_meta
            WHERE token_id = $1
        """
        meta = await db.fetchrow(query, trigger_data.token_id)

        question = meta["question"] if meta else event.get("question", "")
        outcome = meta["outcome"] if meta else event.get("outcome")
        outcome_index = meta["outcome_index"] if meta else event.get("outcome_index")

        # Get category from market data
        category = event.get("category")
        market_id = meta.get("market_id") if meta and hasattr(meta, "get") else (meta["market_id"] if meta and "market_id" in meta else None)
        if not category and market_id:
            market_query = "SELECT category FROM stream_watchlist WHERE market_id = $1"
            market = await db.fetchrow(market_query, market_id)
            category = market.get("category") if market and hasattr(market, "get") else (market["category"] if market and "category" in market else None)

        # Calculate time to end
        time_to_end_hours = event.get("time_to_end_hours", 720.0)  # Default 30 days
        if "end_date" in event and event["end_date"]:
            try:
                end_date = datetime.fromisoformat(str(event["end_date"]).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                time_to_end_hours = max(0, (end_date - now).total_seconds() / 3600)
            except (ValueError, TypeError):
                pass

        # Get model score
        model_score = event.get("model_score")

        return StrategyContext(
            condition_id=trigger_data.condition_id,
            token_id=trigger_data.token_id,
            question=question,
            category=category,
            trigger_price=trigger_data.price,
            trade_size=trigger_data.size,
            time_to_end_hours=time_to_end_hours,
            trade_age_seconds=trigger_data.trade_age_seconds,
            model_score=model_score,
            outcome=outcome,
            outcome_index=outcome_index,
        )

    def apply_filters(
        self,
        context: StrategyContext,
    ) -> tuple[bool, str]:
        """
        Apply hard filters to a context.

        Args:
            context: The strategy context to filter

        Returns:
            (should_reject, reason) tuple
        """
        return apply_hard_filters(context)
