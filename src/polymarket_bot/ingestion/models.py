"""
Data models for the ingestion layer.

These models represent data structures for:
- Price updates from WebSocket
- Trades from REST API
- Market metadata
- Orderbook snapshots

Note on G3 (WebSocket Missing Trade Size):
    PriceUpdate does NOT include size because WebSocket doesn't provide it.
    Use PolymarketRestClient.get_trade_size_at_price() to fetch size separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class TradeSide(str, Enum):
    """Side of a trade."""
    BUY = "BUY"
    SELL = "SELL"


class OutcomeType(str, Enum):
    """Outcome type for a token."""
    YES = "Yes"
    NO = "No"


@dataclass(frozen=True)
class PriceUpdate:
    """
    Real-time price update from WebSocket.

    IMPORTANT (G3 Gotcha):
        Size is NOT available from WebSocket. If you need trade size
        (e.g., for the >= 50 shares filter), you must fetch it separately
        via REST API using get_trade_size_at_price().

    Attributes:
        token_id: The token's unique identifier (asset_id)
        price: Current price as Decimal (0.00 to 1.00)
        timestamp: When the update was received
        condition_id: The market's condition ID (if known)
        market_slug: Human-readable market slug (if known)
    """
    token_id: str
    price: Decimal
    timestamp: datetime
    condition_id: Optional[str] = None
    market_slug: Optional[str] = None

    def __post_init__(self):
        # Validate price range
        if not (Decimal("0") <= self.price <= Decimal("1")):
            raise ValueError(f"Price must be between 0 and 1, got {self.price}")

    @property
    def age_seconds(self) -> float:
        """Seconds since this update was received."""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()

    def is_fresh(self, max_age_seconds: float = 60.0) -> bool:
        """Check if update is recent enough."""
        return self.age_seconds <= max_age_seconds


@dataclass(frozen=True)
class Trade:
    """
    Trade record from REST API.

    Unlike PriceUpdate, Trade includes size because it comes from REST API.

    Attributes:
        id: Unique trade identifier
        token_id: The token's unique identifier
        price: Trade price as Decimal
        size: Trade size (number of shares)
        side: BUY or SELL
        timestamp: When the trade occurred
        condition_id: The market's condition ID (if known)
    """
    id: str
    token_id: str
    price: Decimal
    size: Decimal
    side: TradeSide
    timestamp: datetime
    condition_id: Optional[str] = None

    @property
    def age_seconds(self) -> float:
        """Seconds since this trade occurred."""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()

    def is_fresh(self, max_age_seconds: float = 300.0) -> bool:
        """
        Check if trade is recent enough.

        G1 Protection: Default max age is 300 seconds (5 minutes).
        The Belichick Bug was caused by trusting "recent" trades
        that were actually months old.
        """
        return self.age_seconds <= max_age_seconds


@dataclass(frozen=True)
class OrderbookLevel:
    """Single price level in an orderbook."""
    price: Decimal
    size: Decimal


@dataclass
class OrderbookSnapshot:
    """
    Orderbook state at a point in time.

    Used for G5 protection: verifying that orderbook price
    matches the trigger price before execution.

    Attributes:
        token_id: The token's unique identifier
        bids: List of bid levels (sorted by price descending)
        asks: List of ask levels (sorted by price ascending)
        timestamp: When the snapshot was taken
    """
    token_id: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    timestamp: datetime

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Highest bid price, or None if no bids."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Lowest ask price, or None if no asks."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Mid-point between best bid and ask."""
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> Optional[Decimal]:
        """Spread between best ask and best bid."""
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    def price_within_tolerance(
        self,
        expected_price: Decimal,
        max_deviation: Decimal = Decimal("0.10"),
    ) -> tuple[bool, str]:
        """
        G5 Protection: Check if orderbook price is within tolerance.

        Returns:
            (is_valid, reason): True if within tolerance, with explanation
        """
        if self.best_bid is None:
            return False, "No bids in orderbook"

        deviation = abs(self.best_bid - expected_price)
        if deviation <= max_deviation:
            return True, f"Best bid {self.best_bid} within {max_deviation} of {expected_price}"

        return False, (
            f"Orderbook divergence: best bid {self.best_bid} "
            f"deviates {deviation} from expected {expected_price} "
            f"(max allowed: {max_deviation})"
        )


@dataclass(frozen=True)
class TokenInfo:
    """Token information within a market."""
    token_id: str
    outcome: OutcomeType
    price: Optional[Decimal] = None


@dataclass
class Market:
    """
    Market metadata from Polymarket.

    Attributes:
        condition_id: Unique market identifier
        question: The market question
        slug: URL-friendly identifier
        end_date: When the market closes
        tokens: YES and NO tokens for this market
        active: Whether the market is active for trading
        category: Market category (e.g., "Politics", "Sports")
        volume: Total trading volume
    """
    condition_id: str
    question: str
    slug: str
    end_date: datetime
    tokens: list[TokenInfo]
    active: bool = True
    category: Optional[str] = None
    volume: Optional[Decimal] = None

    @property
    def yes_token(self) -> Optional[TokenInfo]:
        """Get the YES token."""
        for token in self.tokens:
            if token.outcome == OutcomeType.YES:
                return token
        return None

    @property
    def no_token(self) -> Optional[TokenInfo]:
        """Get the NO token."""
        for token in self.tokens:
            if token.outcome == OutcomeType.NO:
                return token
        return None

    @property
    def time_to_end(self) -> float:
        """Hours until market ends."""
        now = datetime.now(timezone.utc)
        delta = self.end_date - now
        return delta.total_seconds() / 3600

    @property
    def is_expired(self) -> bool:
        """Check if market has ended."""
        return self.time_to_end <= 0


@dataclass
class ProcessedEvent:
    """
    Result of processing an ingestion event.

    Tracks what happened during processing for metrics and debugging.
    """
    event_type: str  # "price_update", "trade"
    token_id: str
    timestamp: datetime
    accepted: bool
    stored: bool
    reason: Optional[str] = None

    # Gotcha tracking
    g1_filtered: bool = False  # Filtered for staleness
    g3_backfilled: bool = False  # Size was backfilled via REST
    g5_flagged: bool = False  # Price divergence detected

    # Original data
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    condition_id: Optional[str] = None

    # Market metadata
    question: Optional[str] = None  # Human-readable market question


@dataclass
class ErrorRecord:
    """Record of an error that occurred during ingestion."""
    timestamp: datetime
    error_type: str
    message: str
    component: str  # "websocket", "rest", "processor", "storage"
    token_id: Optional[str] = None
    recoverable: bool = True

    @property
    def age_seconds(self) -> float:
        """Seconds since this error occurred."""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()


# Type alias for callbacks
PriceUpdateCallback = "Callable[[PriceUpdate], Awaitable[None]]"
