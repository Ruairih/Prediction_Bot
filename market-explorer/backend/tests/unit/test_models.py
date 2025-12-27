"""
TDD: Tests for core data models.
Write tests FIRST, then implement models to make them pass.

Codex Review Incorporated:
- Added invariant tests (bid <= ask, yes+no ~= 1)
- Added edge cases for division by zero, empty orderbooks
- Added validation for negative sizes, invalid ranges
- Added timezone safety tests
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from explorer.models.market import (
    Market,
    MarketStatus,
    PriceData,
    LiquidityData,
    OrderbookLevel,
    Orderbook,
    Trade,
    OHLCV,
)


class TestMarketModel:
    """Test the core Market model."""

    def test_market_creation_with_required_fields(self):
        """Market should be creatable with minimal required fields."""
        market = Market(
            condition_id="0x1234567890abcdef",
            question="Will Bitcoin hit $150k by end of 2025?",
        )

        assert market.condition_id == "0x1234567890abcdef"
        assert market.question == "Will Bitcoin hit $150k by end of 2025?"
        assert market.status == MarketStatus.ACTIVE  # default
        assert market.resolved is False  # default

    def test_market_with_full_data(self):
        """Market should accept all optional fields."""
        now = datetime.now(timezone.utc)
        market = Market(
            condition_id="0x1234",
            market_id="market_123",
            event_id="event_456",
            question="Will ETH hit $10k?",
            description="Resolves YES if ETH >= $10,000",
            category="crypto",
            auto_category="cryptocurrency",
            end_time=now,
            resolved=False,
            outcome=None,
            price=PriceData(
                yes_price=Decimal("0.42"),
                no_price=Decimal("0.58"),
                best_bid=Decimal("0.41"),
                best_ask=Decimal("0.43"),
            ),
            liquidity=LiquidityData(
                volume_24h=Decimal("125000.00"),
                volume_7d=Decimal("890000.00"),
                open_interest=Decimal("1200000.00"),
                liquidity_score=Decimal("85.5"),
            ),
        )

        assert market.market_id == "market_123"
        assert market.event_id == "event_456"
        assert market.category == "crypto"
        assert market.price.yes_price == Decimal("0.42")
        assert market.liquidity.volume_24h == Decimal("125000.00")

    def test_market_empty_question_rejected(self):
        """Market must have a non-empty question."""
        with pytest.raises(ValueError, match="question"):
            Market(
                condition_id="0x1234",
                question="",
            )

    def test_market_empty_condition_id_rejected(self):
        """Market must have a non-empty condition_id."""
        with pytest.raises(ValueError, match="condition_id"):
            Market(
                condition_id="",
                question="Test question?",
            )

    def test_market_status_resolved_consistency(self):
        """If resolved=True, status should be RESOLVED."""
        # Valid: resolved=True with status=RESOLVED
        market = Market(
            condition_id="0x1234",
            question="Test?",
            resolved=True,
            status=MarketStatus.RESOLVED,
            outcome="YES",
        )
        assert market.resolved is True
        assert market.status == MarketStatus.RESOLVED

    def test_market_time_to_expiry(self):
        """Market should calculate time to expiry."""
        future_time = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        market = Market(
            condition_id="0x1234",
            question="Test market",
            end_time=future_time,
        )

        # Should return positive timedelta for future markets
        assert market.time_to_expiry is not None
        assert market.time_to_expiry.total_seconds() > 0

    def test_market_expired_time_to_expiry(self):
        """Expired market should have None or negative time_to_expiry."""
        past_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        market = Market(
            condition_id="0x1234",
            question="Test market",
            end_time=past_time,
        )

        # Should return None or negative for expired markets
        ttl = market.time_to_expiry
        assert ttl is None or ttl.total_seconds() <= 0

    def test_market_no_end_time(self):
        """Market without end_time should return None for time_to_expiry."""
        market = Market(
            condition_id="0x1234",
            question="Test market",
            end_time=None,
        )
        assert market.time_to_expiry is None


class TestPriceDataModel:
    """Test the PriceData model with Codex-suggested edge cases."""

    def test_price_data_computed_fields(self):
        """PriceData should compute spread and mid_price."""
        price = PriceData(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50"),
            best_bid=Decimal("0.48"),
            best_ask=Decimal("0.52"),
        )

        assert price.spread == Decimal("0.04")  # 0.52 - 0.48
        assert price.mid_price == Decimal("0.50")  # (0.48 + 0.52) / 2

    def test_price_validation_range(self):
        """Prices must be between 0 and 1."""
        with pytest.raises(ValueError):
            PriceData(
                yes_price=Decimal("1.50"),  # Invalid: > 1
                no_price=Decimal("0.50"),
                best_bid=Decimal("0.48"),
                best_ask=Decimal("0.52"),
            )

        with pytest.raises(ValueError):
            PriceData(
                yes_price=Decimal("0.50"),
                no_price=Decimal("-0.50"),  # Invalid: < 0
                best_bid=Decimal("0.48"),
                best_ask=Decimal("0.52"),
            )

    def test_price_bid_must_be_less_than_or_equal_ask(self):
        """best_bid must be <= best_ask (invariant)."""
        with pytest.raises(ValueError, match="bid.*ask"):
            PriceData(
                yes_price=Decimal("0.50"),
                no_price=Decimal("0.50"),
                best_bid=Decimal("0.55"),  # Invalid: bid > ask
                best_ask=Decimal("0.45"),
            )

    def test_price_bid_equals_ask_valid(self):
        """best_bid == best_ask is valid (zero spread)."""
        price = PriceData(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50"),
            best_bid=Decimal("0.50"),
            best_ask=Decimal("0.50"),
        )
        assert price.spread == Decimal("0.00")
        assert price.mid_price == Decimal("0.50")

    def test_price_yes_plus_no_approximately_one(self):
        """yes_price + no_price should be close to 1.00 (warning if not)."""
        # Valid: sum is exactly 1
        price = PriceData(
            yes_price=Decimal("0.42"),
            no_price=Decimal("0.58"),
            best_bid=Decimal("0.41"),
            best_ask=Decimal("0.43"),
        )
        assert price.yes_price + price.no_price == Decimal("1.00")

        # Also valid: allow slight deviation due to market dynamics
        price2 = PriceData(
            yes_price=Decimal("0.42"),
            no_price=Decimal("0.57"),  # Sum = 0.99
            best_bid=Decimal("0.41"),
            best_ask=Decimal("0.43"),
        )
        # Should still work, just flag if sum deviates too much
        assert price2.prices_sum_valid(tolerance=Decimal("0.05"))

    def test_price_none_bid_ask_handling(self):
        """PriceData with None bid/ask should handle gracefully."""
        price = PriceData(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.50"),
            best_bid=None,
            best_ask=None,
        )
        assert price.spread is None
        assert price.mid_price is None

    def test_price_spread_quantization(self):
        """Spread should be properly quantized to avoid floating point issues."""
        price = PriceData(
            yes_price=Decimal("0.333"),
            no_price=Decimal("0.667"),
            best_bid=Decimal("0.332"),
            best_ask=Decimal("0.334"),
        )
        # Should be exactly 0.002, not 0.0020000000001
        assert price.spread == Decimal("0.002")


class TestMarketStatusEnum:
    """Test MarketStatus enum."""

    def test_market_status_values(self):
        """MarketStatus should have correct values."""
        assert MarketStatus.ACTIVE.value == "active"
        assert MarketStatus.RESOLVING.value == "resolving"
        assert MarketStatus.RESOLVED.value == "resolved"
        assert MarketStatus.CANCELLED.value == "cancelled"

    def test_market_status_from_string(self):
        """MarketStatus should be creatable from string."""
        assert MarketStatus("active") == MarketStatus.ACTIVE
        assert MarketStatus("resolved") == MarketStatus.RESOLVED


class TestLiquidityDataModel:
    """Test the LiquidityData model."""

    def test_liquidity_data_creation(self):
        """LiquidityData should store all metrics."""
        liquidity = LiquidityData(
            volume_24h=Decimal("125000.00"),
            volume_7d=Decimal("890000.00"),
            open_interest=Decimal("1200000.00"),
            liquidity_score=Decimal("85.5"),
        )

        assert liquidity.volume_24h == Decimal("125000.00")
        assert liquidity.liquidity_score == Decimal("85.5")

    def test_liquidity_negative_values_rejected(self):
        """Liquidity values must be non-negative."""
        with pytest.raises(ValueError):
            LiquidityData(
                volume_24h=Decimal("-100.00"),  # Invalid
                volume_7d=Decimal("890000.00"),
                open_interest=Decimal("1200000.00"),
                liquidity_score=Decimal("85.5"),
            )

    def test_liquidity_score_range(self):
        """Liquidity score should be 0-100."""
        with pytest.raises(ValueError):
            LiquidityData(
                volume_24h=Decimal("100.00"),
                volume_7d=Decimal("890000.00"),
                open_interest=Decimal("1200000.00"),
                liquidity_score=Decimal("150.0"),  # Invalid: > 100
            )


class TestOrderbookLevelModel:
    """Test the OrderbookLevel model."""

    def test_orderbook_level_creation(self):
        """OrderbookLevel should store price and size."""
        level = OrderbookLevel(
            price=Decimal("0.45"),
            size=Decimal("1500.00"),
        )

        assert level.price == Decimal("0.45")
        assert level.size == Decimal("1500.00")

    def test_orderbook_level_negative_size_rejected(self):
        """OrderbookLevel size must be positive."""
        with pytest.raises(ValueError):
            OrderbookLevel(
                price=Decimal("0.45"),
                size=Decimal("-100.00"),  # Invalid
            )

    def test_orderbook_level_zero_size_rejected(self):
        """OrderbookLevel size must be > 0."""
        with pytest.raises(ValueError):
            OrderbookLevel(
                price=Decimal("0.45"),
                size=Decimal("0.00"),  # Invalid
            )

    def test_orderbook_level_price_range(self):
        """OrderbookLevel price must be 0-1."""
        with pytest.raises(ValueError):
            OrderbookLevel(
                price=Decimal("1.50"),  # Invalid
                size=Decimal("100.00"),
            )


class TestOrderbookModel:
    """Test the Orderbook model with Codex-suggested edge cases."""

    def test_orderbook_creation(self):
        """Orderbook should contain bids and asks."""
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[
                OrderbookLevel(price=Decimal("0.44"), size=Decimal("1000")),
                OrderbookLevel(price=Decimal("0.43"), size=Decimal("2000")),
            ],
            asks=[
                OrderbookLevel(price=Decimal("0.46"), size=Decimal("1500")),
                OrderbookLevel(price=Decimal("0.47"), size=Decimal("3000")),
            ],
        )

        assert orderbook.condition_id == "0x1234"
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == Decimal("0.44")

    def test_orderbook_best_bid_ask(self):
        """Orderbook should compute best bid and ask."""
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[
                OrderbookLevel(price=Decimal("0.44"), size=Decimal("1000")),
                OrderbookLevel(price=Decimal("0.43"), size=Decimal("2000")),
            ],
            asks=[
                OrderbookLevel(price=Decimal("0.46"), size=Decimal("1500")),
                OrderbookLevel(price=Decimal("0.47"), size=Decimal("3000")),
            ],
        )

        assert orderbook.best_bid == Decimal("0.44")
        assert orderbook.best_ask == Decimal("0.46")
        assert orderbook.spread == Decimal("0.02")

    def test_orderbook_depth_at_percentage(self):
        """Orderbook should compute depth within price bands.

        Definition: depth_at_percentage(mid, pct) returns sum of sizes
        for all levels where |price - mid| <= mid * pct
        """
        mid_price = Decimal("0.45")
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[
                OrderbookLevel(price=Decimal("0.44"), size=Decimal("1000")),  # |0.44-0.45|=0.01 <= 0.0225 (5% of 0.45)
                OrderbookLevel(price=Decimal("0.40"), size=Decimal("2000")),  # |0.40-0.45|=0.05 > 0.0225
            ],
            asks=[
                OrderbookLevel(price=Decimal("0.46"), size=Decimal("1500")),  # |0.46-0.45|=0.01 <= 0.0225
                OrderbookLevel(price=Decimal("0.50"), size=Decimal("3000")),  # |0.50-0.45|=0.05 > 0.0225
            ],
        )

        # Depth within 5% of mid should be bids + asks within that range
        depth_5pct = orderbook.depth_at_percentage(mid_price, Decimal("0.05"))
        assert depth_5pct == Decimal("2500")  # 1000 + 1500

    def test_orderbook_depth_empty_result(self):
        """depth_at_percentage should return 0 if no levels in range."""
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[OrderbookLevel(price=Decimal("0.30"), size=Decimal("1000"))],
            asks=[OrderbookLevel(price=Decimal("0.70"), size=Decimal("1500"))],
        )

        # 1% of 0.50 = 0.005, neither level is within range
        depth = orderbook.depth_at_percentage(Decimal("0.50"), Decimal("0.01"))
        assert depth == Decimal("0")

    def test_orderbook_depth_percentage_clamping(self):
        """depth_at_percentage should clamp to valid range."""
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[OrderbookLevel(price=Decimal("0.44"), size=Decimal("1000"))],
            asks=[OrderbookLevel(price=Decimal("0.46"), size=Decimal("1500"))],
        )

        # Percentage > 1 should be clamped or raise
        with pytest.raises(ValueError):
            orderbook.depth_at_percentage(Decimal("0.50"), Decimal("1.50"))

        # Negative percentage should raise
        with pytest.raises(ValueError):
            orderbook.depth_at_percentage(Decimal("0.50"), Decimal("-0.05"))

    def test_empty_orderbook(self):
        """Empty orderbook should handle gracefully."""
        orderbook = Orderbook(
            condition_id="0x1234",
            side="YES",
            bids=[],
            asks=[],
        )

        assert orderbook.best_bid is None
        assert orderbook.best_ask is None
        assert orderbook.spread is None
        assert orderbook.depth_at_percentage(Decimal("0.50"), Decimal("0.05")) == Decimal("0")

    def test_orderbook_side_validation(self):
        """Orderbook side must be YES or NO."""
        with pytest.raises(ValueError):
            Orderbook(
                condition_id="0x1234",
                side="MAYBE",  # Invalid
                bids=[],
                asks=[],
            )


class TestTradeModel:
    """Test the Trade model."""

    def test_trade_creation(self):
        """Trade should store all trade data."""
        now = datetime.now(timezone.utc)
        trade = Trade(
            condition_id="0x1234",
            trade_id="trade_001",
            timestamp=now,
            side="YES",
            price=Decimal("0.45"),
            size=Decimal("100.00"),
            maker_address="0xmaker",
            taker_address="0xtaker",
        )

        assert trade.condition_id == "0x1234"
        assert trade.side == "YES"
        assert trade.price == Decimal("0.45")
        assert trade.size == Decimal("100.00")
        assert trade.notional == Decimal("45.00")  # price * size

    def test_trade_side_validation(self):
        """Trade side must be YES or NO."""
        with pytest.raises(ValueError):
            Trade(
                condition_id="0x1234",
                trade_id="trade_001",
                timestamp=datetime.now(timezone.utc),
                side="MAYBE",  # Invalid
                price=Decimal("0.45"),
                size=Decimal("100.00"),
            )

    def test_trade_negative_size_rejected(self):
        """Trade size must be positive."""
        with pytest.raises(ValueError):
            Trade(
                condition_id="0x1234",
                trade_id="trade_001",
                timestamp=datetime.now(timezone.utc),
                side="YES",
                price=Decimal("0.45"),
                size=Decimal("-100.00"),  # Invalid
            )

    def test_trade_naive_datetime_rejected(self):
        """Trade timestamp must be timezone-aware."""
        with pytest.raises(ValueError, match="timezone"):
            Trade(
                condition_id="0x1234",
                trade_id="trade_001",
                timestamp=datetime.now(),  # Naive - no timezone
                side="YES",
                price=Decimal("0.45"),
                size=Decimal("100.00"),
            )


class TestOHLCVModel:
    """Test the OHLCV candlestick model with Codex-suggested edge cases."""

    def test_ohlcv_creation(self):
        """OHLCV should store candlestick data."""
        now = datetime.now(timezone.utc)
        candle = OHLCV(
            condition_id="0x1234",
            bucket=now,
            timeframe="1h",
            open=Decimal("0.40"),
            high=Decimal("0.48"),
            low=Decimal("0.38"),
            close=Decimal("0.45"),
            volume=Decimal("50000.00"),
            trade_count=125,
        )

        assert candle.timeframe == "1h"
        assert candle.open == Decimal("0.40")
        assert candle.close == Decimal("0.45")
        assert candle.volume == Decimal("50000.00")

    def test_ohlcv_price_change(self):
        """OHLCV should compute price change percentage."""
        candle = OHLCV(
            condition_id="0x1234",
            bucket=datetime.now(timezone.utc),
            timeframe="1h",
            open=Decimal("0.40"),
            high=Decimal("0.48"),
            low=Decimal("0.38"),
            close=Decimal("0.44"),  # 10% increase
            volume=Decimal("50000.00"),
            trade_count=125,
        )

        assert candle.price_change == Decimal("0.04")  # 0.44 - 0.40
        assert candle.price_change_pct == Decimal("10.00")  # 10%

    def test_ohlcv_price_change_zero_open(self):
        """OHLCV with open=0 should handle price_change_pct gracefully."""
        candle = OHLCV(
            condition_id="0x1234",
            bucket=datetime.now(timezone.utc),
            timeframe="1h",
            open=Decimal("0.00"),
            high=Decimal("0.10"),
            low=Decimal("0.00"),
            close=Decimal("0.05"),
            volume=Decimal("1000.00"),
            trade_count=10,
        )

        assert candle.price_change == Decimal("0.05")
        # When open=0, price_change_pct should be None or infinity indicator
        assert candle.price_change_pct is None

    def test_ohlcv_range(self):
        """OHLCV should compute price range."""
        candle = OHLCV(
            condition_id="0x1234",
            bucket=datetime.now(timezone.utc),
            timeframe="1h",
            open=Decimal("0.40"),
            high=Decimal("0.48"),
            low=Decimal("0.38"),
            close=Decimal("0.45"),
            volume=Decimal("50000.00"),
            trade_count=125,
        )

        assert candle.range == Decimal("0.10")  # 0.48 - 0.38

    def test_ohlcv_high_low_invariant(self):
        """OHLCV high must be >= low."""
        with pytest.raises(ValueError, match="high.*low"):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe="1h",
                open=Decimal("0.40"),
                high=Decimal("0.35"),  # Invalid: high < low
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=125,
            )

    def test_ohlcv_open_close_within_range(self):
        """OHLCV open and close must be within [low, high]."""
        with pytest.raises(ValueError):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe="1h",
                open=Decimal("0.30"),  # Invalid: open < low
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=125,
            )

    def test_ohlcv_negative_volume_rejected(self):
        """OHLCV volume must be non-negative."""
        with pytest.raises(ValueError):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe="1h",
                open=Decimal("0.40"),
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("-1000.00"),  # Invalid
                trade_count=125,
            )

    def test_ohlcv_negative_trade_count_rejected(self):
        """OHLCV trade_count must be non-negative."""
        with pytest.raises(ValueError):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe="1h",
                open=Decimal("0.40"),
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=-5,  # Invalid
            )

    def test_ohlcv_timeframe_validation(self):
        """OHLCV timeframe must be valid."""
        valid_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        for tf in valid_timeframes:
            candle = OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe=tf,
                open=Decimal("0.40"),
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=125,
            )
            assert candle.timeframe == tf

        with pytest.raises(ValueError):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(timezone.utc),
                timeframe="2h",  # Invalid
                open=Decimal("0.40"),
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=125,
            )

    def test_ohlcv_naive_datetime_rejected(self):
        """OHLCV bucket must be timezone-aware."""
        with pytest.raises(ValueError, match="timezone"):
            OHLCV(
                condition_id="0x1234",
                bucket=datetime.now(),  # Naive - no timezone
                timeframe="1h",
                open=Decimal("0.40"),
                high=Decimal("0.48"),
                low=Decimal("0.38"),
                close=Decimal("0.45"),
                volume=Decimal("50000.00"),
                trade_count=125,
            )
