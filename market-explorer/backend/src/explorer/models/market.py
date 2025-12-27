"""
Core domain models for the Market Explorer.

These models represent the core entities in the Polymarket ecosystem:
- Market: A prediction market with pricing and liquidity data
- Orderbook: Bid/ask levels for a market
- Trade: An executed trade
- OHLCV: Candlestick data for historical analysis

Design principles:
- Use Decimal for all prices to avoid floating-point drift
- Validate invariants at construction time
- Timezone-aware datetimes only
- Computed properties for derived values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional


# Valid timeframes for OHLCV data
VALID_TIMEFRAMES = frozenset(["1m", "5m", "15m", "1h", "4h", "1d", "1w"])

# Valid sides for trades/orderbooks
VALID_SIDES = frozenset(["YES", "NO"])


class MarketStatus(Enum):
    """Status of a prediction market."""

    ACTIVE = "active"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


def _validate_price_range(value: Decimal, field_name: str) -> None:
    """Validate that a price is within [0, 1]."""
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be between 0 and 1, got {value}")


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    """Validate that a value is non-negative."""
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative, got {value}")


def _validate_positive(value: Decimal, field_name: str) -> None:
    """Validate that a value is positive (> 0)."""
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive, got {value}")


def _validate_timezone_aware(dt: datetime, field_name: str) -> None:
    """Validate that a datetime is timezone-aware."""
    if dt.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _validate_side(side: str) -> None:
    """Validate that side is YES or NO."""
    if side not in VALID_SIDES:
        raise ValueError(f"side must be YES or NO, got {side}")


@dataclass
class PriceData:
    """Pricing information for a market.

    Stores YES/NO prices and best bid/ask for spread calculation.
    All prices must be in [0, 1].
    """

    yes_price: Decimal
    no_price: Optional[Decimal] = None
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None

    def __post_init__(self) -> None:
        """Validate price constraints."""
        _validate_price_range(self.yes_price, "yes_price")
        if self.no_price is not None:
            _validate_price_range(self.no_price, "no_price")

        if self.best_bid is not None:
            _validate_price_range(self.best_bid, "best_bid")
        if self.best_ask is not None:
            _validate_price_range(self.best_ask, "best_ask")

        # Invariant: bid <= ask
        if self.best_bid is not None and self.best_ask is not None:
            if self.best_bid > self.best_ask:
                raise ValueError(
                    f"best_bid ({self.best_bid}) must be <= best_ask ({self.best_ask})"
                )

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid price between bid and ask."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    def prices_sum_valid(self, tolerance: Decimal = Decimal("0.05")) -> bool:
        """Check if yes + no prices sum to approximately 1.

        Args:
            tolerance: Maximum allowed deviation from 1.0

        Returns:
            True if sum is within tolerance of 1.0
        """
        price_sum = self.yes_price + self.no_price
        return abs(price_sum - Decimal("1.0")) <= tolerance


@dataclass
class LiquidityData:
    """Liquidity metrics for a market.

    Note: liquidity_score is the raw liquidity in dollars from Polymarket,
    not a percentage score. Higher values indicate more liquid markets.
    """

    volume_24h: Decimal
    volume_7d: Decimal
    open_interest: Decimal
    liquidity_score: Decimal  # Raw liquidity in dollars

    def __post_init__(self) -> None:
        """Validate liquidity constraints."""
        _validate_non_negative(self.volume_24h, "volume_24h")
        _validate_non_negative(self.volume_7d, "volume_7d")
        _validate_non_negative(self.open_interest, "open_interest")
        _validate_non_negative(self.liquidity_score, "liquidity_score")


@dataclass
class Market:
    """A Polymarket prediction market.

    Required fields:
        condition_id: Unique identifier for the market condition
        question: The question being predicted

    Optional fields include pricing, liquidity, timing, and categorization.
    """

    condition_id: str
    question: str
    market_id: Optional[str] = None
    event_id: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    auto_category: Optional[str] = None
    end_time: Optional[datetime] = None
    resolution_time: Optional[datetime] = None
    resolved: bool = False
    outcome: Optional[str] = None
    status: MarketStatus = MarketStatus.ACTIVE
    price: Optional[PriceData] = None
    liquidity: Optional[LiquidityData] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate market constraints."""
        if not self.condition_id or not self.condition_id.strip():
            raise ValueError("condition_id cannot be empty")
        if not self.question or not self.question.strip():
            raise ValueError("question cannot be empty")

    @property
    def time_to_expiry(self) -> Optional[timedelta]:
        """Calculate time remaining until market expiry.

        Returns:
            timedelta if end_time is set and in the future
            None if end_time is not set
            timedelta (may be negative) if end_time is in the past
        """
        if self.end_time is None:
            return None

        now = datetime.now(timezone.utc)
        # Ensure end_time is timezone-aware for comparison
        end = self.end_time
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        return end - now


@dataclass
class OrderbookLevel:
    """A single price level in an orderbook."""

    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        """Validate level constraints."""
        _validate_price_range(self.price, "price")
        _validate_positive(self.size, "size")


@dataclass
class Orderbook:
    """Orderbook for a market side (YES or NO).

    Contains sorted lists of bids and asks with their sizes.
    """

    condition_id: str
    side: str  # "YES" or "NO"
    bids: list[OrderbookLevel] = field(default_factory=list)
    asks: list[OrderbookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate orderbook constraints."""
        _validate_side(self.side)

    @property
    def best_bid(self) -> Optional[Decimal]:
        """Get the highest bid price."""
        if not self.bids:
            return None
        return max(level.price for level in self.bids)

    @property
    def best_ask(self) -> Optional[Decimal]:
        """Get the lowest ask price."""
        if not self.asks:
            return None
        return min(level.price for level in self.asks)

    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        bid = self.best_bid
        ask = self.best_ask
        if bid is None or ask is None:
            return None
        return ask - bid

    def depth_at_percentage(
        self, mid_price: Decimal, percentage: Decimal
    ) -> Decimal:
        """Calculate total depth within a percentage band of mid price.

        Args:
            mid_price: The reference price (typically the mid)
            percentage: The percentage band (e.g., 0.05 for 5%)

        Returns:
            Sum of sizes for all levels within |price - mid| <= mid * percentage

        Raises:
            ValueError: If percentage is negative or > 1
        """
        if percentage < Decimal("0"):
            raise ValueError(f"percentage must be non-negative, got {percentage}")
        if percentage > Decimal("1"):
            raise ValueError(f"percentage must be <= 1, got {percentage}")

        threshold = mid_price * percentage
        total = Decimal("0")

        for level in self.bids:
            if abs(level.price - mid_price) <= threshold:
                total += level.size

        for level in self.asks:
            if abs(level.price - mid_price) <= threshold:
                total += level.size

        return total


@dataclass
class Trade:
    """An executed trade on a market."""

    condition_id: str
    trade_id: str
    timestamp: datetime
    side: str  # "YES" or "NO"
    price: Decimal
    size: Decimal
    maker_address: Optional[str] = None
    taker_address: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate trade constraints."""
        _validate_side(self.side)
        _validate_price_range(self.price, "price")
        _validate_positive(self.size, "size")
        _validate_timezone_aware(self.timestamp, "timestamp")

    @property
    def notional(self) -> Decimal:
        """Calculate notional value (price * size)."""
        return self.price * self.size


@dataclass
class OHLCV:
    """OHLCV candlestick data for a market.

    Stores open, high, low, close prices and volume for a time bucket.
    """

    condition_id: str
    bucket: datetime  # Start of the time bucket
    timeframe: str  # "1m", "5m", "15m", "1h", "4h", "1d", "1w"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int

    def __post_init__(self) -> None:
        """Validate OHLCV constraints."""
        # Validate timezone
        _validate_timezone_aware(self.bucket, "bucket")

        # Validate timeframe
        if self.timeframe not in VALID_TIMEFRAMES:
            raise ValueError(
                f"timeframe must be one of {VALID_TIMEFRAMES}, got {self.timeframe}"
            )

        # Validate price ranges
        _validate_price_range(self.open, "open")
        _validate_price_range(self.high, "high")
        _validate_price_range(self.low, "low")
        _validate_price_range(self.close, "close")

        # Validate high >= low
        if self.high < self.low:
            raise ValueError(
                f"high ({self.high}) must be >= low ({self.low})"
            )

        # Validate open/close within range
        if self.open < self.low or self.open > self.high:
            raise ValueError(
                f"open ({self.open}) must be within [low, high] = [{self.low}, {self.high}]"
            )
        if self.close < self.low or self.close > self.high:
            raise ValueError(
                f"close ({self.close}) must be within [low, high] = [{self.low}, {self.high}]"
            )

        # Validate volume and trade_count
        _validate_non_negative(self.volume, "volume")
        if self.trade_count < 0:
            raise ValueError(f"trade_count must be non-negative, got {self.trade_count}")

    @property
    def price_change(self) -> Decimal:
        """Calculate absolute price change (close - open)."""
        return self.close - self.open

    @property
    def price_change_pct(self) -> Optional[Decimal]:
        """Calculate percentage price change.

        Returns:
            Percentage change as Decimal (e.g., 10.00 for 10%)
            None if open is zero (undefined)
        """
        if self.open == Decimal("0"):
            return None
        return ((self.close - self.open) / self.open) * Decimal("100")

    @property
    def range(self) -> Decimal:
        """Calculate price range (high - low)."""
        return self.high - self.low
