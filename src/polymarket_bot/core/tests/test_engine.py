"""
Tests for the main TradingEngine.

The engine orchestrates: events -> strategy -> execution.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from polymarket_bot.core import TradingEngine, EngineConfig, EngineStats
from polymarket_bot.strategies import (
    EntrySignal,
    ExitSignal,
    HoldSignal,
    WatchlistSignal,
    IgnoreSignal,
    SignalType,
)


class TestEngineInitialization:
    """Tests for engine setup."""

    def test_engine_initializes_with_config(self, mock_db, mock_strategy):
        """Engine should initialize with configuration."""
        config = EngineConfig(
            price_threshold=Decimal("0.95"),
            position_size=Decimal("20"),
        )

        engine = TradingEngine(
            config=config,
            db=mock_db,
            strategy=mock_strategy,
        )

        assert engine.config == config
        assert engine.strategy == mock_strategy

    def test_engine_starts_in_stopped_state(self, stopped_engine):
        """Engine should not be running until started."""
        assert stopped_engine.is_running is False

    def test_engine_has_stats(self, trading_engine):
        """Engine should track statistics."""
        stats = trading_engine.stats

        assert isinstance(stats, EngineStats)
        assert stats.events_processed == 0
        assert stats.entries_executed == 0

    def test_engine_exposes_trigger_repo(self, trading_engine):
        """Engine should expose trigger repository."""
        assert trading_engine.trigger_repo is not None

    def test_engine_exposes_position_repo(self, trading_engine):
        """Engine should expose position repository."""
        assert trading_engine.position_repo is not None


class TestEngineLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, stopped_engine):
        """Starting engine should set is_running to True."""
        assert stopped_engine.is_running is False  # Verify initially stopped
        await stopped_engine.start()

        assert stopped_engine.is_running is True

        await stopped_engine.stop()  # Cleanup

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self, stopped_engine):
        """Stopping engine should set is_running to False."""
        await stopped_engine.start()
        await stopped_engine.stop()

        assert stopped_engine.is_running is False

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, stopped_engine):
        """Starting when already running should be idempotent."""
        await stopped_engine.start()
        await stopped_engine.start()  # Second call

        assert stopped_engine.is_running is True

        await stopped_engine.stop()  # Cleanup

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, stopped_engine):
        """Stopping when not running should be safe."""
        assert stopped_engine.is_running is False  # Verify initially stopped
        await stopped_engine.stop()  # Should not raise

        assert stopped_engine.is_running is False


class TestEventProcessing:
    """Tests for event handling pipeline."""

    @pytest.mark.asyncio
    async def test_processes_valid_event(self, trading_engine, price_trigger_event, mock_db):
        """Should process valid price trigger event."""
        # Mock token metadata lookup
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None  # No existing trigger

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.events_processed == 1

    @pytest.mark.asyncio
    async def test_ignores_below_threshold(self, trading_engine, below_threshold_event, mock_strategy):
        """Should ignore events below price threshold."""
        await trading_engine.process_event(below_threshold_event)

        # Strategy should NOT have been called
        mock_strategy.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluates_strategy(self, trading_engine, price_trigger_event, mock_db, mock_strategy):
        """Should evaluate strategy for valid events."""
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None

        await trading_engine.process_event(price_trigger_event)

        mock_strategy.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_signal(self, trading_engine, price_trigger_event, mock_db, mock_strategy):
        """Should return the signal from strategy."""
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_strategy.evaluate.return_value = HoldSignal(reason="Test hold")

        signal = await trading_engine.process_event(price_trigger_event)

        assert signal is not None
        assert signal.type == SignalType.HOLD


class TestTriggerDeduplication:
    """Tests for trigger deduplication (G2)."""

    @pytest.mark.asyncio
    async def test_rejects_duplicate_trigger(self, trading_engine, price_trigger_event, mock_db, mock_strategy):
        """Should reject duplicate triggers for same token."""
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        # Simulate existing trigger
        mock_db.fetchval.return_value = 1

        await trading_engine.process_event(price_trigger_event)

        # Strategy should NOT have been called
        mock_strategy.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_tracks_triggers_evaluated(self, trading_engine, price_trigger_event, mock_db):
        """Should track number of triggers evaluated."""
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.triggers_evaluated == 1

    @pytest.mark.asyncio
    async def test_duplicate_events_are_ignored(
        self, trading_engine, price_trigger_event, mock_db, mock_strategy
    ):
        """Duplicate WebSocket events should not re-trigger strategy evaluation."""
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        # First event: no existing triggers (token + condition checks)
        # Second event: existing trigger found
        mock_db.fetchval.side_effect = [None, None, 1]

        await trading_engine.process_event(price_trigger_event)
        await trading_engine.process_event(price_trigger_event)

        assert mock_strategy.evaluate.call_count == 1


class TestSignalRouting:
    """Tests for routing signals to handlers."""

    @pytest.mark.asyncio
    async def test_handles_entry_signal(self, trading_engine, price_trigger_event, mock_db, always_enter_strategy):
        """Should handle ENTRY signal."""
        trading_engine.strategy = always_enter_strategy
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        # Should have recorded dry run
        assert trading_engine.stats.dry_run_signals == 1

    @pytest.mark.asyncio
    async def test_handles_watchlist_signal(self, trading_engine, price_trigger_event, mock_db, watchlist_strategy):
        """Should handle WATCHLIST signal."""
        trading_engine.strategy = watchlist_strategy
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.watchlist_additions == 1

    @pytest.mark.asyncio
    async def test_handles_ignore_signal(self, trading_engine, price_trigger_event, mock_db, mock_strategy):
        """Should handle IGNORE signal."""
        mock_strategy.evaluate.return_value = IgnoreSignal(
            reason="Filtered",
            filter_name="test_filter",
        )
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.filters_rejected >= 1


class TestDryRunMode:
    """Tests for dry-run (paper trading) mode."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_submit_orders(
        self, trading_engine, price_trigger_event, mock_db, always_enter_strategy
    ):
        """Dry run should NOT submit real orders."""
        trading_engine.strategy = always_enter_strategy
        trading_engine.config.dry_run = True
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.orders_submitted == 0
        assert trading_engine.dry_run_signals >= 1

    @pytest.mark.asyncio
    async def test_live_mode_increments_executed(
        self, trading_engine, price_trigger_event, mock_db, always_enter_strategy
    ):
        """Live mode should increment entries_executed."""
        trading_engine.strategy = always_enter_strategy
        trading_engine.config.dry_run = False
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.entries_executed >= 1


class TestOrderbookVerification:
    """Tests for orderbook verification (G5)."""

    @pytest.mark.asyncio
    async def test_verifies_orderbook_before_executing(
        self, trading_engine, price_trigger_event, mock_db, always_enter_strategy, mock_api_client
    ):
        """Should verify orderbook matches trigger before executing."""
        trading_engine.strategy = always_enter_strategy
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        # Should have called orderbook verification
        mock_api_client.verify_orderbook_price.assert_called()

    @pytest.mark.asyncio
    async def test_rejects_when_orderbook_mismatches(
        self, trading_engine, price_trigger_event, mock_db, always_enter_strategy, divergent_orderbook_client
    ):
        """
        G5: Should reject execution when orderbook doesn't match trigger.

        This prevents executing on anomalous spike trades.
        """
        trading_engine.strategy = always_enter_strategy
        trading_engine._api_client = divergent_orderbook_client
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        assert trading_engine.stats.orderbook_rejections == 1
        assert trading_engine.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_skips_verification_when_disabled(
        self, trading_engine, price_trigger_event, mock_db, always_enter_strategy, mock_api_client
    ):
        """Should skip orderbook verification when disabled."""
        trading_engine.strategy = always_enter_strategy
        trading_engine.config.verify_orderbook = False
        mock_db.fetchrow.return_value = {
            "question": "Test?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None
        mock_db.execute.return_value = None

        await trading_engine.process_event(price_trigger_event)

        # Should NOT have called verification
        mock_api_client.verify_orderbook_price.assert_not_called()


class TestHardFilters:
    """Tests for hard filter application."""

    @pytest.mark.asyncio
    async def test_rejects_weather_markets(self, trading_engine, weather_market_event, mock_db, mock_strategy):
        """Should reject weather markets (G6)."""
        mock_db.fetchrow.return_value = {
            "question": "Will it rain in NYC tomorrow?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None

        signal = await trading_engine.process_event(weather_market_event)

        # Should be filtered, strategy not called
        if signal is not None:
            assert signal.type == SignalType.IGNORE
        assert trading_engine.stats.filters_rejected >= 1

    @pytest.mark.asyncio
    async def test_allows_rainbow_six(self, trading_engine, rainbow_event, mock_db, mock_strategy):
        """
        REGRESSION TEST: Rainbow Six should NOT be blocked.

        G6 fix: Use word boundaries, not substring match.
        """
        mock_db.fetchrow.return_value = {
            "question": "Will Team A win Rainbow Six Siege tournament?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }
        mock_db.fetchval.return_value = None

        await trading_engine.process_event(rainbow_event)

        # Strategy should have been called (not filtered)
        mock_strategy.evaluate.assert_called_once()


class TestWatchlistRescoring:
    """Tests for watchlist re-scoring."""

    @pytest.mark.asyncio
    async def test_rescores_watchlist(self, trading_engine, mock_db):
        """Should re-score all watchlist entries."""
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_abc",
                "condition_id": "0x123",
                "question": "Test?",
                "trigger_price": 0.95,
                "initial_score": 0.92,
                "current_score": 0.94,
                "time_to_end_hours": 48,
                "created_at": 1702900000,
                "status": "watching",
            }
        ]
        mock_db.execute.return_value = None

        promotions = await trading_engine.rescore_watchlist()

        assert isinstance(promotions, list)


class TestExecutionCount:
    """Tests for execution count tracking."""

    def test_execution_count_combines_live_and_dry(self, trading_engine):
        """execution_count should combine live and dry run signals."""
        trading_engine._stats.entries_executed = 5
        trading_engine._stats.dry_run_signals = 10

        assert trading_engine.execution_count == 15

    def test_orders_submitted_only_live(self, trading_engine):
        """orders_submitted should only count live orders."""
        trading_engine._stats.entries_executed = 5
        trading_engine._stats.dry_run_signals = 10

        assert trading_engine.orders_submitted == 5

    def test_dry_run_signals_property(self, trading_engine):
        """dry_run_signals property should return stats value."""
        trading_engine._stats.dry_run_signals = 7

        assert trading_engine.dry_run_signals == 7
