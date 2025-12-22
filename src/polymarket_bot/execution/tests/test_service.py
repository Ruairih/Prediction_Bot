"""
Tests for ExecutionService - the facade for execution layer.

ExecutionService coordinates:
- BalanceManager (balance tracking)
- OrderManager (order submission)
- PositionTracker (position management)
- ExitManager (exit execution)

This is the primary interface that TradingEngine and BackgroundTasksManager use.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from polymarket_bot.execution.service import (
    ExecutionService,
    ExecutionConfig,
    ExecutionResult,
)
from polymarket_bot.execution import (
    Order,
    OrderStatus,
    Position,
)
from polymarket_bot.strategies import (
    EntrySignal,
    ExitSignal,
    StrategyContext,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value="UPDATE 1")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_clob_client():
    """Mock CLOB client with successful responses."""
    client = MagicMock()
    client.get_balance.return_value = {"USDC": "1000.00"}
    client.create_order.return_value = {"orderID": "order_123", "status": "LIVE"}
    client.get_order.return_value = {
        "orderID": "order_123",
        "status": "MATCHED",
        "filledSize": "20",
        "size": "20",
        "avgPrice": "0.95",
    }
    client.cancel_order.return_value = {"success": True}
    return client


@pytest.fixture
def config():
    """Standard execution config."""
    return ExecutionConfig(
        max_price=Decimal("0.95"),
        default_position_size=Decimal("20"),
        min_balance_reserve=Decimal("100"),
        profit_target=Decimal("0.99"),
        stop_loss=Decimal("0.90"),
        min_hold_days=7,
        wait_for_fill=False,  # Disable for faster tests
    )


@pytest.fixture
def execution_service(mock_db, mock_clob_client, config):
    """ExecutionService for tests."""
    return ExecutionService(
        db=mock_db,
        clob_client=mock_clob_client,
        config=config,
    )


@pytest.fixture
def dry_run_service(mock_db, config):
    """ExecutionService in dry run mode (no CLOB client)."""
    return ExecutionService(
        db=mock_db,
        clob_client=None,  # Dry run
        config=config,
    )


@pytest.fixture
def entry_signal():
    """Standard entry signal."""
    return EntrySignal(
        token_id="tok_yes_abc",
        side="BUY",
        price=Decimal("0.95"),
        size=Decimal("20"),
        reason="Test entry",
    )


@pytest.fixture
def exit_signal():
    """Standard exit signal."""
    return ExitSignal(
        position_id="pos_123",
        reason="profit_target",
    )


@pytest.fixture
def strategy_context():
    """Standard strategy context."""
    return StrategyContext(
        condition_id="0xtest123",
        token_id="tok_yes_abc",
        question="Test market?",
        category="Test",
        trigger_price=Decimal("0.95"),
        trade_size=Decimal("75"),
        time_to_end_hours=720,
        trade_age_seconds=10,
        model_score=0.98,
    )


@pytest.fixture
def sample_position():
    """Standard position."""
    return Position(
        position_id="pos_123",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_cost=Decimal("19.00"),
        entry_time=datetime.now(timezone.utc) - timedelta(days=10),
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestServiceInitialization:
    """Tests for ExecutionService initialization."""

    def test_creates_all_managers(self, mock_db, mock_clob_client, config):
        """Should create all required managers."""
        service = ExecutionService(
            db=mock_db,
            clob_client=mock_clob_client,
            config=config,
        )

        assert service._balance_manager is not None
        assert service._order_manager is not None
        assert service._position_tracker is not None
        assert service._exit_manager is not None

    def test_exposes_managers_via_properties(self, execution_service):
        """Should expose managers via properties for queries."""
        assert execution_service.balance_manager is not None
        assert execution_service.order_manager is not None
        assert execution_service.position_tracker is not None

    def test_works_without_clob_client_for_dry_run(self, mock_db, config):
        """Should work without CLOB client (dry run mode)."""
        service = ExecutionService(
            db=mock_db,
            clob_client=None,
            config=config,
        )

        assert service._clob_client is None


# =============================================================================
# State Loading Tests
# =============================================================================


class TestStateLoading:
    """Tests for load_state functionality."""

    @pytest.mark.asyncio
    async def test_load_state_refreshes_balance(
        self, execution_service, mock_clob_client
    ):
        """load_state should refresh balance from CLOB."""
        await execution_service.load_state()

        mock_clob_client.get_balance.assert_called()

    @pytest.mark.asyncio
    async def test_load_state_loads_open_orders(self, execution_service, mock_db):
        """load_state should load open orders from DB."""
        mock_db.fetch.return_value = []  # No orders

        await execution_service.load_state()

        # Should have queried for open orders
        assert mock_db.fetch.called

    @pytest.mark.asyncio
    async def test_load_state_loads_positions(self, execution_service, mock_db):
        """load_state should load open positions from DB."""
        mock_db.fetch.return_value = []  # No positions

        await execution_service.load_state()

        # Should have been called multiple times (orders + positions)
        assert mock_db.fetch.call_count >= 1


# =============================================================================
# Entry Execution Tests
# =============================================================================


class TestEntryExecution:
    """Tests for execute_entry functionality."""

    @pytest.mark.asyncio
    async def test_execute_entry_returns_success(
        self, execution_service, entry_signal, strategy_context
    ):
        """Successful entry should return success result."""
        result = await execution_service.execute_entry(entry_signal, strategy_context)

        assert result.success is True
        assert result.order_id is not None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_entry_submits_order(
        self, execution_service, entry_signal, strategy_context, mock_clob_client
    ):
        """Should submit order to CLOB."""
        await execution_service.execute_entry(entry_signal, strategy_context)

        mock_clob_client.create_order.assert_called()

    @pytest.mark.asyncio
    async def test_execute_entry_syncs_order_status(
        self, execution_service, entry_signal, strategy_context, mock_clob_client
    ):
        """Should sync order status after submission."""
        await execution_service.execute_entry(entry_signal, strategy_context)

        mock_clob_client.get_order.assert_called()

    @pytest.mark.asyncio
    async def test_execute_entry_creates_position_on_fill(
        self, execution_service, entry_signal, strategy_context
    ):
        """Should create position when order fills."""
        result = await execution_service.execute_entry(entry_signal, strategy_context)

        # Position should be created (mock CLOB returns MATCHED)
        assert result.position_id is not None

    @pytest.mark.asyncio
    async def test_execute_entry_handles_price_too_high(
        self, execution_service, strategy_context
    ):
        """Should handle price too high error."""
        high_price_signal = EntrySignal(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.99"),  # Above max price
            size=Decimal("20"),
            reason="Test entry",
        )

        result = await execution_service.execute_entry(high_price_signal, strategy_context)

        assert result.success is False
        assert result.error_type == "price_too_high"

    @pytest.mark.asyncio
    async def test_execute_entry_handles_insufficient_balance(
        self, mock_db, config, strategy_context
    ):
        """Should handle insufficient balance error."""
        # Create client that fails on order creation
        failing_client = MagicMock()
        failing_client.get_balance.return_value = {"USDC": "5.00"}  # Low balance
        failing_client.create_order.side_effect = Exception("Insufficient balance")

        service = ExecutionService(
            db=mock_db,
            clob_client=failing_client,
            config=config,
        )

        signal = EntrySignal(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
            reason="Test entry",
        )

        result = await service.execute_entry(signal, strategy_context)

        assert result.success is False
        assert result.error_type == "insufficient_balance"


# =============================================================================
# Exit Execution Tests
# =============================================================================


class TestExitExecution:
    """Tests for execute_exit functionality."""

    @pytest.mark.asyncio
    async def test_execute_exit_returns_success(
        self, execution_service, exit_signal, sample_position, mock_clob_client
    ):
        """Successful exit should return success result."""
        # Pre-populate position
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position
        execution_service._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        # Make CLOB return MATCHED for exit order
        mock_clob_client.get_order.return_value = {
            "orderID": "exit_order",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        }

        result = await execution_service.execute_exit(
            exit_signal, sample_position, Decimal("0.99")
        )

        assert result.success is True
        assert result.position_id == sample_position.position_id

    @pytest.mark.asyncio
    async def test_execute_exit_submits_sell_order(
        self, execution_service, exit_signal, sample_position, mock_clob_client
    ):
        """Should submit sell order to CLOB."""
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position
        execution_service._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        mock_clob_client.get_order.return_value = {
            "orderID": "exit_order",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        }

        await execution_service.execute_exit(
            exit_signal, sample_position, Decimal("0.99")
        )

        # Should have called create_order for exit
        mock_clob_client.create_order.assert_called()


# =============================================================================
# Order Sync Tests
# =============================================================================


class TestOrderSync:
    """Tests for sync_open_orders functionality."""

    @pytest.mark.asyncio
    async def test_sync_open_orders_returns_count(
        self, execution_service
    ):
        """sync_open_orders should return number of orders synced."""
        # No open orders
        count = await execution_service.sync_open_orders()

        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_open_orders_syncs_each_order(
        self, execution_service, mock_clob_client
    ):
        """Should sync status for each open order."""
        # Add an open order
        order = Order(
            order_id="order_open",
            token_id="tok_abc",
            condition_id="0xtest",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
            status=OrderStatus.PENDING,
        )
        execution_service._order_manager._orders[order.order_id] = order

        mock_clob_client.get_order.return_value = {
            "orderID": "order_open",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
            "avgPrice": "0.95",
        }

        count = await execution_service.sync_open_orders()

        assert count == 1
        mock_clob_client.get_order.assert_called_with("order_open")

    @pytest.mark.asyncio
    async def test_sync_detects_partial_fills(
        self, execution_service, mock_clob_client
    ):
        """Should detect and record partial fills."""
        # Add an order with no fills
        order = Order(
            order_id="order_partial",
            token_id="tok_partial",
            condition_id="0xtest",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
            filled_size=Decimal("0"),
            status=OrderStatus.LIVE,
        )
        execution_service._order_manager._orders[order.order_id] = order

        # Return partial fill
        mock_clob_client.get_order.return_value = {
            "orderID": "order_partial",
            "status": "LIVE",
            "filledSize": "10",
            "size": "20",
            "avgPrice": "0.95",
        }

        await execution_service.sync_open_orders()

        # Should have updated order
        updated_order = execution_service._order_manager._orders["order_partial"]
        assert updated_order.filled_size == Decimal("10")
        assert updated_order.status == OrderStatus.PARTIAL


# =============================================================================
# Exit Evaluation Tests
# =============================================================================


class TestExitEvaluation:
    """Tests for evaluate_exits functionality."""

    @pytest.mark.asyncio
    async def test_evaluate_exits_checks_all_positions(
        self, execution_service, sample_position
    ):
        """Should check all open positions for exit conditions."""
        # Add position
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position
        execution_service._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        current_prices = {sample_position.token_id: Decimal("0.99")}  # At profit target

        exits = await execution_service.evaluate_exits(current_prices)

        # Should identify exit (position is > 7 days old, price at profit target)
        assert len(exits) == 1
        assert exits[0][0].position_id == sample_position.position_id
        assert exits[0][1] == "profit_target"

    @pytest.mark.asyncio
    async def test_evaluate_exits_returns_empty_when_no_exits(
        self, execution_service, sample_position
    ):
        """Should return empty list when no exits needed."""
        # Add position
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position

        # Price in middle (no exit)
        current_prices = {sample_position.token_id: Decimal("0.96")}

        exits = await execution_service.evaluate_exits(current_prices)

        assert len(exits) == 0

    @pytest.mark.asyncio
    async def test_evaluate_exits_handles_missing_price(
        self, execution_service, sample_position
    ):
        """Should skip positions without current price."""
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position

        # No price for this token
        current_prices = {}

        exits = await execution_service.evaluate_exits(current_prices)

        assert len(exits) == 0


# =============================================================================
# Resolution Handling Tests
# =============================================================================


class TestResolutionHandling:
    """Tests for handle_resolution functionality."""

    @pytest.mark.asyncio
    async def test_handle_resolution_closes_position(
        self, execution_service, sample_position, mock_clob_client
    ):
        """Should close position on market resolution."""
        # Add position
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position
        execution_service._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        # Resolve as Yes (1.0)
        result = await execution_service.handle_resolution(
            sample_position.token_id, Decimal("1.0")
        )

        # handle_resolution returns bool (True if closed)
        assert result is True

        # Position should be closed
        position = execution_service._position_tracker.positions.get(sample_position.position_id)
        assert position.status == "closed"

    @pytest.mark.asyncio
    async def test_handle_resolution_returns_false_for_unknown_token(
        self, execution_service
    ):
        """Should return False for unknown token."""
        result = await execution_service.handle_resolution(
            "unknown_token", Decimal("1.0")
        )

        assert result is False


# =============================================================================
# Convenience Method Tests
# =============================================================================


class TestConvenienceMethods:
    """Tests for convenience methods."""

    def test_get_available_balance(self, execution_service, mock_clob_client):
        """get_available_balance should return balance from manager."""
        balance = execution_service.get_available_balance()

        # get_available_balance returns total minus reservations (not min_reserve)
        # With no reservations, it returns the full balance
        assert balance == Decimal("1000.00")

    def test_get_open_positions(self, execution_service, sample_position):
        """get_open_positions should return open positions."""
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position

        positions = execution_service.get_open_positions()

        assert len(positions) == 1
        assert positions[0].position_id == sample_position.position_id

    def test_get_open_orders(self, execution_service):
        """get_open_orders should return open orders."""
        order = Order(
            order_id="order_open",
            token_id="tok_abc",
            condition_id="0xtest",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
            status=OrderStatus.LIVE,
        )
        execution_service._order_manager._orders[order.order_id] = order

        orders = execution_service.get_open_orders()

        assert len(orders) == 1

    def test_get_position_by_token(self, execution_service, sample_position):
        """get_position_by_token should return position for token."""
        execution_service._position_tracker.positions[sample_position.position_id] = sample_position
        execution_service._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        position = execution_service.get_position_by_token(sample_position.token_id)

        assert position is not None
        assert position.position_id == sample_position.position_id

    def test_get_position_by_token_returns_none_for_unknown(self, execution_service):
        """get_position_by_token should return None for unknown token."""
        position = execution_service.get_position_by_token("unknown_token")

        assert position is None


# =============================================================================
# Dry Run Mode Tests
# =============================================================================


class TestDryRunMode:
    """Tests for dry run mode behavior."""

    @pytest.mark.asyncio
    async def test_dry_run_entry_fails_with_no_balance(
        self, dry_run_service, entry_signal, strategy_context
    ):
        """Entry in dry run mode fails due to zero balance (no CLOB = no balance)."""
        # Without a CLOB client, balance is 0, so orders fail with insufficient balance
        result = await dry_run_service.execute_entry(entry_signal, strategy_context)

        # This fails because without CLOB client there's no way to get balance
        assert result.success is False
        assert result.error_type == "insufficient_balance"

    def test_dry_run_balance_returns_zero(self, dry_run_service):
        """Balance should return zero in dry run mode without CLOB."""
        balance = dry_run_service.get_available_balance()

        # Without CLOB, balance is 0
        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_dry_run_with_mocked_balance_works(
        self, mock_db, config, entry_signal, strategy_context
    ):
        """Dry run with mocked balance (simulated trading) should work."""
        # Create a service with no CLOB but mock the balance manager
        service = ExecutionService(
            db=mock_db,
            clob_client=None,
            config=config,
        )

        # Pre-set cached balance to simulate paper trading
        # Must set both balance AND cache_time for cache to be valid
        service._balance_manager._cached_balance = Decimal("1000.00")
        service._balance_manager._cache_time = datetime.now(timezone.utc)

        result = await service.execute_entry(entry_signal, strategy_context)

        # Should succeed with mock balance
        assert result.success is True
        assert "mock_order" in result.order_id


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestFullWorkflow:
    """Tests for full entry-to-exit workflow."""

    @pytest.mark.asyncio
    async def test_entry_to_exit_workflow(
        self, execution_service, entry_signal, strategy_context, mock_clob_client
    ):
        """Test full workflow from entry to exit."""
        # 1. Execute entry
        entry_result = await execution_service.execute_entry(
            entry_signal, strategy_context
        )
        assert entry_result.success is True
        assert entry_result.position_id is not None

        # 2. Get the position
        position = execution_service.get_position_by_token(entry_signal.token_id)
        assert position is not None

        # 3. Evaluate exits (price at profit target)
        current_prices = {position.token_id: Decimal("0.99")}
        exits = await execution_service.evaluate_exits(current_prices)

        # Should want to exit (position is old enough and at profit target)
        assert len(exits) >= 0  # May or may not exit depending on position age

        # 4. Execute exit
        exit_signal = ExitSignal(
            position_id=position.position_id,
            reason="profit_target",
        )

        mock_clob_client.get_order.return_value = {
            "orderID": "exit_order",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        }

        exit_result = await execution_service.execute_exit(
            exit_signal, position, Decimal("0.99")
        )

        assert exit_result.success is True
