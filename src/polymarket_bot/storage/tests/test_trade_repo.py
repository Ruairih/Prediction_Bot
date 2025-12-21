"""
Trade repository tests.

Tests for trade storage and watermark pattern (G1 gotcha prevention).
"""
from datetime import datetime

import pytest

from polymarket_bot.storage.models import PolymarketTrade
from polymarket_bot.storage.repositories import TradeRepository, TradeWatermarkRepository


@pytest.mark.asyncio
class TestTradeRepository:
    """Tests for TradeRepository."""

    async def test_create_trade(
        self, trade_repo: TradeRepository, sample_trade: PolymarketTrade
    ):
        """Test creating a trade."""
        result = await trade_repo.create(sample_trade)

        assert result.condition_id == sample_trade.condition_id
        assert result.trade_id == sample_trade.trade_id
        assert result.price == sample_trade.price

    async def test_duplicate_trade_is_noop(
        self, trade_repo: TradeRepository, sample_trade: PolymarketTrade
    ):
        """Test duplicate trade insert is ignored (ON CONFLICT DO NOTHING)."""
        await trade_repo.create(sample_trade)
        await trade_repo.create(sample_trade)

        count = await trade_repo.count()
        assert count == 1

    async def test_get_by_condition(
        self, trade_repo: TradeRepository, sample_trade: PolymarketTrade
    ):
        """Test getting trades by condition_id."""
        await trade_repo.create(sample_trade)

        # Create another trade for same condition
        trade2 = sample_trade.model_copy()
        trade2.trade_id = "trade_002"
        await trade_repo.create(trade2)

        results = await trade_repo.get_by_condition(sample_trade.condition_id)

        assert len(results) == 2

    async def test_get_recent_filters_old_trades(
        self, trade_repo: TradeRepository, sample_trade: PolymarketTrade
    ):
        """
        CRITICAL TEST: G1 gotcha - filters old trades.

        The "Belichick Bug" happened when old trades were mistaken
        for recent activity. This test ensures get_recent filters by age.
        """
        # Create an old trade (10 minutes ago)
        old_trade = sample_trade.model_copy()
        old_trade.timestamp = int(datetime.utcnow().timestamp()) - 600
        old_trade.trade_id = "old_trade"
        await trade_repo.create(old_trade)

        # Create a recent trade (1 minute ago)
        recent_trade = sample_trade.model_copy()
        recent_trade.timestamp = int(datetime.utcnow().timestamp()) - 60
        recent_trade.trade_id = "recent_trade"
        await trade_repo.create(recent_trade)

        # Get recent trades (max 5 minutes)
        results = await trade_repo.get_recent(
            sample_trade.condition_id, max_age_seconds=300
        )

        assert len(results) == 1
        assert results[0].trade_id == "recent_trade"

    async def test_create_many(self, trade_repo: TradeRepository):
        """Test bulk insert of trades."""
        trades = [
            PolymarketTrade(
                condition_id="0xbulk",
                trade_id=f"trade_{i}",
                token_id="0xtoken",
                price=0.5 + i * 0.01,
                size=100.0,
                timestamp=int(datetime.utcnow().timestamp()),
            )
            for i in range(5)
        ]

        count = await trade_repo.create_many(trades)

        assert count == 5

        # Verify all inserted
        results = await trade_repo.get_by_condition("0xbulk")
        assert len(results) == 5

    async def test_get_latest_timestamp(
        self, trade_repo: TradeRepository, sample_trade: PolymarketTrade
    ):
        """Test getting latest trade timestamp."""
        await trade_repo.create(sample_trade)

        result = await trade_repo.get_latest_timestamp(sample_trade.condition_id)

        assert result == sample_trade.timestamp


@pytest.mark.asyncio
class TestTradeWatermarkRepository:
    """Tests for TradeWatermarkRepository (idempotent processing)."""

    async def test_get_timestamp_returns_zero_if_none(
        self, trade_watermark_repo: TradeWatermarkRepository
    ):
        """Test returns 0 for non-existent watermark."""
        result = await trade_watermark_repo.get_timestamp("0xnonexistent")

        assert result == 0

    async def test_update_creates_watermark(
        self, trade_watermark_repo: TradeWatermarkRepository
    ):
        """Test update creates new watermark."""
        timestamp = int(datetime.utcnow().timestamp())

        result = await trade_watermark_repo.update("0xcondition", timestamp)

        assert result.condition_id == "0xcondition"
        assert result.last_timestamp == timestamp

    async def test_watermark_enables_idempotent_processing(
        self, trade_repo: TradeRepository,
        trade_watermark_repo: TradeWatermarkRepository,
    ):
        """
        Test watermark pattern for idempotent processing.

        Pattern:
        1. Get watermark (last processed timestamp)
        2. Fetch trades newer than watermark
        3. Process trades
        4. Update watermark
        """
        # Initial state: no watermark
        watermark = await trade_watermark_repo.get_timestamp("0xtest")
        assert watermark == 0

        # "Process" some trades
        now = int(datetime.utcnow().timestamp())
        trades = [
            PolymarketTrade(
                condition_id="0xtest",
                trade_id=f"trade_{i}",
                token_id="0xtoken",
                price=0.5,
                size=100.0,
                timestamp=now + i,
            )
            for i in range(3)
        ]
        await trade_repo.create_many(trades)

        # Update watermark to latest processed
        latest_timestamp = now + 2
        await trade_watermark_repo.update("0xtest", latest_timestamp)

        # Next run: only process trades newer than watermark
        new_watermark = await trade_watermark_repo.get_timestamp("0xtest")
        assert new_watermark == latest_timestamp

        # Add new trade
        new_trade = PolymarketTrade(
            condition_id="0xtest",
            trade_id="trade_new",
            token_id="0xtoken",
            price=0.6,
            size=100.0,
            timestamp=now + 100,  # Newer than watermark
        )
        await trade_repo.create(new_trade)

        # Get trades since watermark (simulating next processing run)
        # This would typically be a custom query, but we can verify the pattern
        latest = await trade_repo.get_latest_timestamp("0xtest")
        assert latest > new_watermark, "New trade should be after watermark"
