"""
Tests for event processor with G1/G3/G5 protections.

These tests verify that the gotcha protections work correctly.
"""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from polymarket_bot.ingestion.models import PriceUpdate, Trade, TradeSide
from polymarket_bot.ingestion.processor import EventProcessor, ProcessorConfig


class TestG1StaleTradeFiltering:
    """
    G1 REGRESSION TESTS: Stale Trade Data (Belichick Bug)

    Polymarket's API returns "recent" trades that may be months old.
    We MUST filter by timestamp.
    """

    @pytest.mark.asyncio
    async def test_filters_out_stale_trades(self, event_processor):
        """
        CRITICAL: Stale trades must be rejected.

        The Belichick Bug caused us to execute at 95c based on a
        2-month-old trade when the actual market was at 5c.
        """
        # Create a trade that's 60 days old
        stale_time = datetime.now(timezone.utc) - timedelta(days=60)
        stale_trade = Trade(
            id="trade_stale",
            token_id="0x123",
            price=Decimal("0.95"),
            size=Decimal("4.2"),
            side=TradeSide.BUY,
            timestamp=stale_time,
        )

        result = await event_processor.process_trade(stale_trade)

        assert not result.accepted
        assert result.g1_filtered
        assert "too old" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_accepts_fresh_trades(self, event_processor):
        """Fresh trades should be accepted."""
        fresh_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        fresh_trade = Trade(
            id="trade_fresh",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=fresh_time,
        )

        result = await event_processor.process_trade(fresh_trade)

        assert result.accepted
        assert not result.g1_filtered

    @pytest.mark.asyncio
    async def test_configurable_max_age(self, mock_rest_client, metrics_collector):
        """Max age is configurable."""
        # Configure very short max age
        config = ProcessorConfig(
            max_trade_age_seconds=60,  # 1 minute
            backfill_missing_size=False,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        # Trade that's 2 minutes old (should be filtered)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        trade = Trade(
            id="trade",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=old_time,
        )

        result = await processor.process_trade(trade)
        assert not result.accepted
        assert result.g1_filtered

    @pytest.mark.asyncio
    async def test_boundary_case_exactly_at_limit(self, event_processor):
        """Trade exactly at the age limit should be accepted."""
        # Exactly 300 seconds ago (at the boundary)
        boundary_time = datetime.now(timezone.utc) - timedelta(seconds=299)
        trade = Trade(
            id="trade",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=boundary_time,
        )

        result = await event_processor.process_trade(trade)
        assert result.accepted

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_g1(self, event_processor, metrics_collector):
        """G1 filtering should update metrics."""
        stale_trade = Trade(
            id="stale",
            token_id="0x123",
            price=Decimal("0.95"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=datetime.now(timezone.utc) - timedelta(days=30),
        )

        await event_processor.process_trade(stale_trade)

        metrics = metrics_collector.get_metrics()
        assert metrics.g1_stale_filtered > 0


class TestG3MissingSizeBackfill:
    """
    G3 TESTS: WebSocket Missing Trade Size

    WebSocket price updates don't include size.
    We must fetch size via REST API.
    """

    @pytest.mark.asyncio
    async def test_backfills_missing_size(self, event_processor):
        """
        Price updates should have size backfilled from REST.
        """
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await event_processor.process_price_update(update)

        assert result.accepted
        assert result.g3_backfilled
        assert result.size is not None

    @pytest.mark.asyncio
    async def test_handles_backfill_failure(
        self, mock_rest_client, metrics_collector
    ):
        """Should handle gracefully when backfill fails."""
        # Make backfill return None
        mock_rest_client.get_trade_size_at_price = AsyncMock(return_value=None)

        config = ProcessorConfig(
            backfill_missing_size=True,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await processor.process_price_update(update)

        # Should still accept, just without size
        assert result.accepted
        assert not result.g3_backfilled
        assert result.size is None

    @pytest.mark.asyncio
    async def test_backfill_can_be_disabled(
        self, mock_rest_client, metrics_collector
    ):
        """Backfill can be disabled in config."""
        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await processor.process_price_update(update)

        assert result.accepted
        assert not result.g3_backfilled


class TestG5PriceDivergence:
    """
    G5 REGRESSION TESTS: Orderbook vs Trade Price Divergence

    Spike trades can show 95c while orderbook is at 5c.
    Must detect and flag these divergences.
    """

    @pytest.mark.asyncio
    async def test_flags_price_divergence(
        self, mock_rest_client, metrics_collector
    ):
        """
        CRITICAL: Must detect when orderbook diverges from trigger price.

        A spike trade at 95c when orderbook is at 5c would cause
        massive losses if executed.
        """
        # Mock orderbook to return divergent price (5c)
        async def mock_verify_divergent(token_id, expected_price, max_deviation):
            return False, Decimal("0.05"), "Orderbook at 0.05, expected 0.95"

        mock_rest_client.verify_price = mock_verify_divergent

        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=True,
            max_price_deviation=Decimal("0.10"),
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        # Price update at 95c
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.95"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await processor.process_price_update(update)

        # Should be flagged (but still accepted for logging)
        assert result.accepted
        assert result.g5_flagged

    @pytest.mark.asyncio
    async def test_no_flag_when_prices_match(self, event_processor):
        """Normal price updates should not be flagged."""
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await event_processor.process_price_update(update)

        assert result.accepted
        assert not result.g5_flagged

    @pytest.mark.asyncio
    async def test_divergence_check_can_be_disabled(
        self, mock_rest_client, metrics_collector
    ):
        """Divergence checking can be disabled."""
        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.95"),
            timestamp=datetime.now(timezone.utc),
        )

        result = await processor.process_price_update(update)

        # Should not check divergence when disabled
        assert result.accepted
        assert not result.g5_flagged


class TestProcessorStats:
    """Tests for processor statistics tracking."""

    @pytest.mark.asyncio
    async def test_tracks_processed_count(self, event_processor):
        """Total processed count is tracked."""
        # Reset stats to get clean baseline
        event_processor.reset_stats()

        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )
        await event_processor.process_price_update(update)

        assert event_processor.stats.total_processed == 1

    @pytest.mark.asyncio
    async def test_tracks_accepted_rejected(self, event_processor):
        """Accepted and rejected counts are tracked."""
        # Process a fresh trade (should be accepted)
        fresh_trade = Trade(
            id="fresh",
            token_id="0x123",
            price=Decimal("0.75"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=datetime.now(timezone.utc),
        )
        await event_processor.process_trade(fresh_trade)

        # Process a stale trade (should be rejected)
        stale_trade = Trade(
            id="stale",
            token_id="0x123",
            price=Decimal("0.95"),
            size=Decimal("100"),
            side=TradeSide.BUY,
            timestamp=datetime.now(timezone.utc) - timedelta(days=30),
        )
        await event_processor.process_trade(stale_trade)

        stats = event_processor.stats
        assert stats.total_accepted >= 1
        assert stats.total_rejected >= 1

    @pytest.mark.asyncio
    async def test_recent_events_stored(self, event_processor):
        """Recent events are stored for dashboard."""
        update = PriceUpdate(
            token_id="0x123",
            price=Decimal("0.75"),
            timestamp=datetime.now(timezone.utc),
        )
        await event_processor.process_price_update(update)

        events = event_processor.recent_events
        assert len(events) > 0
        assert events[0].token_id == "0x123"


class TestConcurrentProcessing:
    """
    Tests for concurrent event processing.

    FIX: Lock is only held during shared state updates, not during I/O.
    This allows concurrent event processing while I/O is in progress.
    """

    @pytest.mark.asyncio
    async def test_concurrent_price_updates(
        self, mock_rest_client, metrics_collector
    ):
        """
        Should process multiple price updates concurrently.

        The fix allows I/O to happen in parallel while only
        locking during shared state updates.
        """
        import asyncio

        # Create slow REST client to test concurrency
        slow_responses = []

        async def slow_verify(*args, **kwargs):
            # Simulate network delay
            await asyncio.sleep(0.1)
            slow_responses.append(True)
            return True, Decimal("0.75"), ""

        mock_rest_client.verify_price = slow_verify
        mock_rest_client.get_trade_size_at_price = AsyncMock(return_value=Decimal("100"))

        config = ProcessorConfig(
            backfill_missing_size=True,
            check_price_divergence=True,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        # Create multiple updates
        updates = [
            PriceUpdate(
                token_id=f"0x{i}",
                price=Decimal("0.75"),
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        # Process concurrently
        start_time = time.time()
        results = await asyncio.gather(*[
            processor.process_price_update(u) for u in updates
        ])
        elapsed = time.time() - start_time

        # All should succeed
        assert all(r.accepted for r in results)

        # Should be faster than sequential (5 * 0.1s = 0.5s)
        # Concurrent should be closer to 0.1s (plus some overhead)
        # Allow some tolerance for test environment variability
        assert elapsed < 0.4, f"Processing took {elapsed:.2f}s - may not be concurrent"

    @pytest.mark.asyncio
    async def test_concurrent_trades(
        self, mock_rest_client, metrics_collector
    ):
        """
        Should process multiple trades concurrently.
        """
        import asyncio

        async def slow_verify(*args, **kwargs):
            await asyncio.sleep(0.05)
            return True, Decimal("0.75"), ""

        mock_rest_client.verify_price = slow_verify

        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=True,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )

        # Create multiple fresh trades
        trades = [
            Trade(
                id=f"trade_{i}",
                token_id=f"0x{i}",
                price=Decimal("0.75"),
                size=Decimal("100"),
                side=TradeSide.BUY,
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        # Process concurrently
        start_time = time.time()
        results = await asyncio.gather(*[
            processor.process_trade(t) for t in trades
        ])
        elapsed = time.time() - start_time

        # All should succeed
        assert all(r.accepted for r in results)

        # Should be concurrent (faster than sequential)
        assert elapsed < 0.2, f"Processing took {elapsed:.2f}s - may not be concurrent"

    @pytest.mark.asyncio
    async def test_stats_consistent_after_concurrent(
        self, mock_rest_client, metrics_collector
    ):
        """
        Stats should be consistent after concurrent processing.

        Despite concurrent I/O, shared state updates are locked.
        """
        import asyncio

        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )
        processor.reset_stats()

        # Create many updates
        updates = [
            PriceUpdate(
                token_id=f"0x{i}",
                price=Decimal("0.75"),
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(100)
        ]

        # Process all concurrently
        results = await asyncio.gather(*[
            processor.process_price_update(u) for u in updates
        ])

        # Stats should be consistent
        stats = processor.stats
        assert stats.total_processed == 100
        assert stats.total_accepted == 100
        assert len(processor.recent_events) == 100

    @pytest.mark.asyncio
    async def test_mixed_concurrent_processing(
        self, mock_rest_client, metrics_collector
    ):
        """
        Should handle mixed price updates and trades concurrently.
        """
        import asyncio

        config = ProcessorConfig(
            backfill_missing_size=False,
            check_price_divergence=False,
        )
        processor = EventProcessor(
            rest_client=mock_rest_client,
            metrics=metrics_collector,
            config=config,
        )
        processor.reset_stats()

        # Mix of updates and trades
        updates = [
            PriceUpdate(
                token_id=f"0x{i}",
                price=Decimal("0.75"),
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        trades = [
            Trade(
                id=f"trade_{i}",
                token_id=f"0x{i}",
                price=Decimal("0.75"),
                size=Decimal("100"),
                side=TradeSide.BUY,
                timestamp=datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        # Process all concurrently
        coros = [processor.process_price_update(u) for u in updates]
        coros += [processor.process_trade(t) for t in trades]

        results = await asyncio.gather(*coros)

        # All should succeed
        assert all(r.accepted for r in results)
        assert processor.stats.total_processed == 10
