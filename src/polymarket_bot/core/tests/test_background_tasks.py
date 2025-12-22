"""
Tests for BackgroundTasksManager.

The BackgroundTasksManager runs periodic async tasks for:
- Watchlist rescoring and promotion
- Order status sync with CLOB
- Exit condition evaluation
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from decimal import Decimal

from polymarket_bot.core.background_tasks import (
    BackgroundTasksManager,
    BackgroundTaskConfig,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_engine():
    """Mock TradingEngine."""
    engine = MagicMock()
    engine.rescore_watchlist = AsyncMock(return_value=[])
    engine.config = MagicMock(
        dry_run=False,
        position_size=20,
    )
    return engine


@pytest.fixture
def mock_engine_dry_run():
    """Mock TradingEngine in dry run mode."""
    engine = MagicMock()
    engine.rescore_watchlist = AsyncMock(return_value=[])
    engine.config = MagicMock(
        dry_run=True,
        position_size=20,
    )
    return engine


@pytest.fixture
def mock_execution_service():
    """Mock ExecutionService."""
    service = AsyncMock()
    service.sync_open_orders = AsyncMock(return_value=0)
    service.evaluate_exits = AsyncMock(return_value=[])
    service.execute_exit = AsyncMock()
    service.execute_entry = AsyncMock()
    service.get_open_positions = MagicMock(return_value=[])
    return service


@pytest.fixture
def mock_price_fetcher():
    """Mock price fetcher callback."""
    async def fetcher(token_ids):
        return {tid: Decimal("0.95") for tid in token_ids}
    return fetcher


@pytest.fixture
def default_config():
    """Default task configuration with short intervals for testing."""
    return BackgroundTaskConfig(
        watchlist_rescore_interval_seconds=0.1,  # Short for fast tests
        watchlist_enabled=True,
        order_sync_interval_seconds=0.1,
        order_sync_enabled=True,
        exit_eval_interval_seconds=0.1,
        exit_eval_enabled=True,
    )


@pytest.fixture
def disabled_config():
    """Configuration with all tasks disabled."""
    return BackgroundTaskConfig(
        watchlist_enabled=False,
        order_sync_enabled=False,
        exit_eval_enabled=False,
    )


@pytest.fixture
def mock_promotion():
    """Mock watchlist promotion entry."""
    promotion = MagicMock()
    promotion.token_id = "tok_promoted"
    promotion.new_score = 0.98
    promotion.condition_id = "0xtest123"
    promotion.trigger_price = Decimal("0.95")
    promotion.time_to_end_hours = 720.0
    promotion.question = "Test market?"
    promotion.outcome = None
    promotion.outcome_index = None
    return promotion


@pytest.fixture
def mock_position():
    """Mock position for exit evaluation."""
    position = MagicMock()
    position.position_id = "pos_test123"
    position.token_id = "tok_position"
    position.size = Decimal("20")
    position.entry_price = Decimal("0.95")
    return position


# =============================================================================
# Idempotent Start/Stop Tests
# =============================================================================


class TestIdempotentStartStop:
    """Tests for idempotent start and stop behavior."""

    @pytest.mark.asyncio
    async def test_start_twice_warns_and_returns(
        self, mock_engine, mock_execution_service, default_config
    ):
        """Starting twice should log warning and return early."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        # First start
        await manager.start()
        assert manager.is_running

        # Second start should be idempotent
        with patch("polymarket_bot.core.background_tasks.logger") as mock_logger:
            await manager.start()
            mock_logger.warning.assert_called_once()

        # Still running, same number of tasks
        assert manager.is_running

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_twice_is_safe(
        self, mock_engine, mock_execution_service, default_config
    ):
        """Stopping twice should be safe and idempotent."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        await manager.start()
        assert manager.is_running

        # First stop
        await manager.stop()
        assert not manager.is_running

        # Second stop should be safe
        await manager.stop()
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(
        self, mock_engine, mock_execution_service, default_config
    ):
        """Stopping without starting should be safe."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        # Should not raise
        await manager.stop()
        assert not manager.is_running


# =============================================================================
# Task Creation Gating Tests
# =============================================================================


class TestTaskCreationGating:
    """Tests for task creation based on config and dependencies."""

    @pytest.mark.asyncio
    async def test_watchlist_task_requires_engine(
        self, mock_execution_service, default_config
    ):
        """Watchlist task should not start without engine."""
        manager = BackgroundTasksManager(
            engine=None,  # No engine
            execution_service=mock_execution_service,
            config=default_config,
        )

        await manager.start()

        # Should start only non-watchlist tasks
        task_names = [t.get_name() for t in manager._tasks]
        assert "watchlist_rescore" not in task_names
        assert "order_sync" in task_names
        assert "exit_eval" in task_names

        await manager.stop()

    @pytest.mark.asyncio
    async def test_order_sync_requires_execution_service(
        self, mock_engine, default_config
    ):
        """Order sync task should not start without execution service."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=None,  # No execution service
            config=default_config,
        )

        await manager.start()

        # Only watchlist task should start
        task_names = [t.get_name() for t in manager._tasks]
        assert "watchlist_rescore" in task_names
        assert "order_sync" not in task_names
        assert "exit_eval" not in task_names

        await manager.stop()

    @pytest.mark.asyncio
    async def test_exit_eval_requires_execution_service(
        self, mock_engine
    ):
        """Exit eval task should not start without execution service."""
        config = BackgroundTaskConfig(
            watchlist_enabled=False,  # Disable to isolate
            order_sync_enabled=False,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=None,  # No execution service
            config=config,
        )

        await manager.start()

        # No tasks should start
        assert len(manager._tasks) == 0

        await manager.stop()

    @pytest.mark.asyncio
    async def test_disabled_tasks_dont_start(
        self, mock_engine, mock_execution_service, disabled_config
    ):
        """Disabled tasks should not start even with dependencies."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=disabled_config,
        )

        await manager.start()

        assert len(manager._tasks) == 0

        await manager.stop()

    @pytest.mark.asyncio
    async def test_all_tasks_start_with_all_dependencies(
        self, mock_engine, mock_execution_service, default_config
    ):
        """All enabled tasks should start when dependencies are available."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        await manager.start()

        task_names = [t.get_name() for t in manager._tasks]
        assert "watchlist_rescore" in task_names
        assert "order_sync" in task_names
        assert "exit_eval" in task_names

        await manager.stop()


# =============================================================================
# Dry Run vs Live Mode Tests
# =============================================================================


class TestDryRunVsLiveMode:
    """Tests for dry run vs live mode behavior in watchlist promotions."""

    @pytest.mark.asyncio
    async def test_dry_run_logs_but_does_not_execute(
        self, mock_engine_dry_run, mock_execution_service, mock_promotion
    ):
        """In dry run mode, promotions should be logged but not executed."""
        mock_engine_dry_run.rescore_watchlist = AsyncMock(return_value=[mock_promotion])

        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=0.05,
            watchlist_enabled=True,
            order_sync_enabled=False,
            exit_eval_enabled=False,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine_dry_run,
            execution_service=mock_execution_service,
            config=config,
        )

        with patch("polymarket_bot.core.background_tasks.logger") as mock_logger:
            await manager.start()
            await asyncio.sleep(0.15)  # Let one rescore cycle run
            await manager.stop()

            # Should log dry run message
            assert any(
                "DRY RUN" in str(call)
                for call in mock_logger.info.call_args_list
            )

        # Should NOT have called execute_entry
        mock_execution_service.execute_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_mode_executes_promotions(
        self, mock_engine, mock_execution_service, mock_promotion
    ):
        """In live mode, promotions should be executed via ExecutionService."""
        mock_engine.rescore_watchlist = AsyncMock(return_value=[mock_promotion])
        mock_execution_service.execute_entry = AsyncMock(
            return_value=MagicMock(success=True, order_id="order_123")
        )

        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=0.05,
            watchlist_enabled=True,
            order_sync_enabled=False,
            exit_eval_enabled=False,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
        )

        await manager.start()
        await asyncio.sleep(0.15)  # Let one rescore cycle run
        await manager.stop()

        # Should have called execute_entry
        mock_execution_service.execute_entry.assert_called()


# =============================================================================
# Stop Event Cancellation Tests
# =============================================================================


class TestStopEventCancellation:
    """Tests for graceful task cancellation via stop event."""

    @pytest.mark.asyncio
    async def test_stop_event_cancels_waiting_tasks(
        self, mock_engine, mock_execution_service
    ):
        """Tasks waiting on interval should exit when stop event is set."""
        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=60,  # Long interval
            watchlist_enabled=True,
            order_sync_interval_seconds=60,
            order_sync_enabled=True,
            exit_eval_interval_seconds=60,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
        )

        await manager.start()
        assert manager.is_running
        assert len(manager._tasks) == 3

        # Stop should complete quickly despite long intervals
        import time
        start = time.time()
        await manager.stop()
        elapsed = time.time() - start

        # Should stop in under 1 second (not wait for 60s interval)
        assert elapsed < 1.0
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_tasks_clear_after_stop(
        self, mock_engine, mock_execution_service, default_config
    ):
        """Task list should be cleared after stop."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        await manager.start()
        assert len(manager._tasks) > 0

        await manager.stop()
        assert len(manager._tasks) == 0


# =============================================================================
# Error Recovery Tests
# =============================================================================


class TestErrorRecovery:
    """Tests for error recovery in background loops."""

    @pytest.mark.asyncio
    async def test_watchlist_loop_logs_error_and_continues(
        self, mock_engine, mock_execution_service
    ):
        """Watchlist loop should log error and remain running."""
        mock_engine.rescore_watchlist = AsyncMock(
            side_effect=Exception("Temporary error")
        )

        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=0.05,
            watchlist_enabled=True,
            order_sync_enabled=False,
            exit_eval_enabled=False,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
        )

        with patch("polymarket_bot.core.background_tasks.logger") as mock_logger:
            await manager.start()
            await asyncio.sleep(0.1)  # Let one cycle fail

            # Error should be logged
            assert any(
                "Error in watchlist rescore" in str(call)
                for call in mock_logger.error.call_args_list
            )

            # But task should still be running (manager is still running)
            assert manager.is_running
            assert len([t for t in manager._tasks if not t.done()]) > 0

            await manager.stop()

    @pytest.mark.asyncio
    async def test_order_sync_loop_logs_error_and_continues(
        self, mock_engine, mock_execution_service
    ):
        """Order sync loop should log error and remain running."""
        mock_execution_service.sync_open_orders = AsyncMock(
            side_effect=Exception("CLOB connection error")
        )

        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_interval_seconds=0.05,
            order_sync_enabled=True,
            exit_eval_enabled=False,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
        )

        with patch("polymarket_bot.core.background_tasks.logger") as mock_logger:
            await manager.start()
            await asyncio.sleep(0.1)  # Let one cycle fail

            # Error should be logged
            assert any(
                "Error in order sync" in str(call)
                for call in mock_logger.error.call_args_list
            )

            # But task should still be running
            assert manager.is_running

            await manager.stop()

    @pytest.mark.asyncio
    async def test_exit_eval_loop_continues_after_price_fetch_error(
        self, mock_engine, mock_execution_service, mock_position
    ):
        """Exit eval loop should continue after price fetcher error."""
        mock_execution_service.get_open_positions = MagicMock(
            return_value=[mock_position]
        )

        call_count = 0

        async def price_fetcher_with_error(token_ids):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Price API error")
            return {tid: Decimal("0.95") for tid in token_ids}

        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_enabled=False,
            exit_eval_interval_seconds=0.05,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
            price_fetcher=price_fetcher_with_error,
        )

        await manager.start()
        await asyncio.sleep(0.25)  # Let multiple cycles run
        await manager.stop()

        # Should have tried at least twice
        assert call_count >= 2


# =============================================================================
# Exit Evaluation Tests
# =============================================================================


class TestExitEvaluation:
    """Tests for exit evaluation functionality."""

    @pytest.mark.asyncio
    async def test_skips_exit_eval_without_price_fetcher(
        self, mock_engine, mock_execution_service, mock_position
    ):
        """Exit eval should skip when no price fetcher is provided."""
        mock_execution_service.get_open_positions = MagicMock(
            return_value=[mock_position]
        )

        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_enabled=False,
            exit_eval_interval_seconds=0.05,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
            price_fetcher=None,  # No price fetcher
        )

        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()

        # evaluate_exits should not be called without prices
        mock_execution_service.evaluate_exits.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_exit_eval_without_open_positions(
        self, mock_engine, mock_execution_service, mock_price_fetcher
    ):
        """Exit eval should skip when no open positions."""
        mock_execution_service.get_open_positions = MagicMock(return_value=[])

        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_enabled=False,
            exit_eval_interval_seconds=0.05,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
            price_fetcher=mock_price_fetcher,
        )

        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()

        # evaluate_exits should not be called without positions
        mock_execution_service.evaluate_exits.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_exits_when_conditions_met(
        self, mock_engine, mock_execution_service, mock_position, mock_price_fetcher
    ):
        """Should execute exits when evaluate_exits returns positions."""
        mock_execution_service.get_open_positions = MagicMock(
            return_value=[mock_position]
        )
        mock_execution_service.evaluate_exits = AsyncMock(
            return_value=[(mock_position, "profit_target")]
        )
        mock_execution_service.execute_exit = AsyncMock(
            return_value=MagicMock(success=True)
        )

        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_enabled=False,
            exit_eval_interval_seconds=0.05,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
            price_fetcher=mock_price_fetcher,
        )

        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()

        # Should have called execute_exit
        mock_execution_service.execute_exit.assert_called()


# =============================================================================
# Order Sync Tests
# =============================================================================


class TestOrderSync:
    """Tests for order sync functionality."""

    @pytest.mark.asyncio
    async def test_order_sync_calls_execution_service(
        self, mock_engine, mock_execution_service
    ):
        """Order sync should call ExecutionService.sync_open_orders."""
        config = BackgroundTaskConfig(
            watchlist_enabled=False,
            order_sync_interval_seconds=0.05,
            order_sync_enabled=True,
            exit_eval_enabled=False,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
        )

        await manager.start()
        await asyncio.sleep(0.15)
        await manager.stop()

        # Should have called sync_open_orders
        mock_execution_service.sync_open_orders.assert_called()


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestFullLifecycle:
    """Tests for full manager lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_all_tasks(
        self, mock_engine, mock_execution_service, mock_price_fetcher, mock_position
    ):
        """Test full lifecycle with all tasks running."""
        mock_execution_service.get_open_positions = MagicMock(
            return_value=[mock_position]
        )

        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=0.05,
            watchlist_enabled=True,
            order_sync_interval_seconds=0.05,
            order_sync_enabled=True,
            exit_eval_interval_seconds=0.05,
            exit_eval_enabled=True,
        )

        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=config,
            price_fetcher=mock_price_fetcher,
        )

        # Start
        await manager.start()
        assert manager.is_running
        assert len(manager._tasks) == 3

        # Let tasks run
        await asyncio.sleep(0.2)

        # All services should have been called
        mock_engine.rescore_watchlist.assert_called()
        mock_execution_service.sync_open_orders.assert_called()
        mock_execution_service.evaluate_exits.assert_called()

        # Stop
        await manager.stop()
        assert not manager.is_running
        assert len(manager._tasks) == 0

    @pytest.mark.asyncio
    async def test_is_running_property_accuracy(
        self, mock_engine, mock_execution_service, default_config
    ):
        """is_running property should accurately reflect state."""
        manager = BackgroundTasksManager(
            engine=mock_engine,
            execution_service=mock_execution_service,
            config=default_config,
        )

        # Initially not running
        assert not manager.is_running

        # After start
        await manager.start()
        assert manager.is_running

        # After stop
        await manager.stop()
        assert not manager.is_running
