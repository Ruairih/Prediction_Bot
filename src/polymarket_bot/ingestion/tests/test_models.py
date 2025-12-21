"""Tests for ingestion data models."""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from polymarket_bot.ingestion.models import (
    Market,
    OrderbookLevel,
    OrderbookSnapshot,
    OutcomeType,
    PriceUpdate,
    TokenInfo,
    Trade,
    TradeSide,
)


class TestPriceUpdate:
    """Tests for PriceUpdate model."""

    def test_create_valid_price_update(self):
        """Can create a valid price update."""
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )
        assert update.token_id == "0x123"
        assert update.price == Decimal("0.75")

    def test_price_must_be_between_0_and_1(self):
        """Price must be in valid range."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            PriceUpdate(
                token_id="0x123",
                price=Decimal("1.5"),
                timestamp=datetime.now(timezone.utc),
            )

        with pytest.raises(ValueError, match="between 0 and 1"):
            PriceUpdate(
                token_id="0x123",
                price=Decimal("-0.1"),
                timestamp=datetime.now(timezone.utc),
            )

    def test_is_fresh_within_threshold(self):
        """Fresh update returns True."""
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )
        assert update.is_fresh(max_age_seconds=60)

    def test_is_fresh_outside_threshold(self):
        """Old update returns False."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=old_time,
        )
        assert not update.is_fresh(max_age_seconds=60)


class TestTrade:
    """Tests for Trade model."""

    def test_create_valid_trade(self, now):
        """Can create a valid trade."""
        trade = Trade(
            id="trade_001",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=now,
        )
        assert trade.id == "trade_001"
        assert trade.size == Decimal("100")
        assert trade.side == TradeSide.BUY

    def test_is_fresh_g1_protection(self, now):
        """
        G1 REGRESSION TEST: Fresh trade detection.

        Trades must be filtered by age to prevent the Belichick Bug.
        """
        # Fresh trade (10 seconds ago)
        fresh_trade = Trade(
            id="fresh",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=now - timedelta(seconds=10),
        )
        assert fresh_trade.is_fresh(max_age_seconds=300)

        # Stale trade (60 days ago)
        stale_trade = Trade(
            id="stale",
            token_id="0x123",
            price=Decimal("0.95"),
            size=Decimal("4.2"),
            side=TradeSide.BUY,
            timestamp=now - timedelta(days=60),
        )
        assert not stale_trade.is_fresh(max_age_seconds=300)


class TestOrderbookSnapshot:
    """Tests for OrderbookSnapshot model."""

    def test_best_bid_ask(self, sample_orderbook):
        """Best bid and ask are correctly identified."""
        assert sample_orderbook.best_bid == Decimal("0.74")
        assert sample_orderbook.best_ask == Decimal("0.76")

    def test_mid_price(self, sample_orderbook):
        """Mid price is calculated correctly."""
        # (0.74 + 0.76) / 2 = 0.75
        assert sample_orderbook.mid_price == Decimal("0.75")

    def test_spread(self, sample_orderbook):
        """Spread is calculated correctly."""
        # 0.76 - 0.74 = 0.02
        assert sample_orderbook.spread == Decimal("0.02")

    def test_empty_orderbook(self, now):
        """Empty orderbook handles gracefully."""
        empty = OrderbookSnapshot(
            token_id="0x123",
            bids=[],
            asks=[],
            timestamp=now,
        )
        assert empty.best_bid is None
        assert empty.best_ask is None
        assert empty.mid_price is None
        assert empty.spread is None

    def test_price_within_tolerance_valid(self, sample_orderbook):
        """
        G5 TEST: Price within tolerance passes.
        """
        is_valid, reason = sample_orderbook.price_within_tolerance(
            expected_price=Decimal("0.75"),
            max_deviation=Decimal("0.10"),
        )
        assert is_valid
        assert "within" in reason

    def test_price_within_tolerance_divergent(self, divergent_orderbook):
        """
        G5 REGRESSION TEST: Price divergence detection.

        Orderbook at 5c when trigger is 95c should be rejected.
        """
        is_valid, reason = divergent_orderbook.price_within_tolerance(
            expected_price=Decimal("0.95"),
            max_deviation=Decimal("0.10"),
        )
        assert not is_valid
        assert "divergence" in reason.lower()
        assert "0.05" in reason  # Actual orderbook price
        assert "0.95" in reason  # Expected price


class TestMarket:
    """Tests for Market model."""

    def test_yes_no_tokens(self, sample_market):
        """Can access YES and NO tokens."""
        assert sample_market.yes_token is not None
        assert sample_market.yes_token.outcome == OutcomeType.YES

        assert sample_market.no_token is not None
        assert sample_market.no_token.outcome == OutcomeType.NO

    def test_time_to_end(self):
        """Time to end is calculated correctly."""
        future_market = Market(
            condition_id="test",
            question="Test?",
            slug="test",
            end_date=datetime.now(timezone.utc) + timedelta(hours=24),
            tokens=[],
        )
        # Should be approximately 24 hours
        assert 23 < future_market.time_to_end < 25

    def test_is_expired(self):
        """Expired market detection works."""
        expired = Market(
            condition_id="test",
            question="Test?",
            slug="test",
            end_date=datetime.now(timezone.utc) - timedelta(hours=1),
            tokens=[],
        )
        assert expired.is_expired

        active = Market(
            condition_id="test",
            question="Test?",
            slug="test",
            end_date=datetime.now(timezone.utc) + timedelta(hours=1),
            tokens=[],
        )
        assert not active.is_expired
