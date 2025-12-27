"""
Tests for exit strategy management.

Exit strategies:
- Short positions (<7 days): Hold to resolution (high win rate)
- Long positions (>7 days): Apply profit target (99c) and stop-loss (90c)
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from polymarket_bot.execution import (
    ExitManager,
    ExitConfig,
    Position,
)


class TestExitStrategySelection:
    """Tests for selecting appropriate exit strategy."""

    def test_short_position_holds_to_resolution(
        self, exit_manager, short_held_position
    ):
        """Positions < 7 days should hold to resolution."""
        should_exit, reason = exit_manager.evaluate_exit(
            short_held_position,
            current_price=Decimal("0.99")  # At profit target
        )

        # Should NOT exit - short hold
        assert should_exit is False

    def test_long_position_exits_at_profit_target(
        self, exit_manager, long_held_position
    ):
        """Positions > 7 days should exit at profit target."""
        should_exit, reason = exit_manager.evaluate_exit(
            long_held_position,
            current_price=Decimal("0.99")  # At profit target
        )

        assert should_exit is True
        assert reason == "profit_target"

    def test_long_position_exits_at_stop_loss(
        self, exit_manager, long_held_position
    ):
        """Positions > 7 days should exit at stop loss."""
        should_exit, reason = exit_manager.evaluate_exit(
            long_held_position,
            current_price=Decimal("0.90")  # At stop loss
        )

        assert should_exit is True
        assert reason == "stop_loss"

    def test_long_position_holds_in_between(
        self, exit_manager, long_held_position
    ):
        """Long positions should hold between target and stop."""
        should_exit, reason = exit_manager.evaluate_exit(
            long_held_position,
            current_price=Decimal("0.94")  # Between 0.90 and 0.99
        )

        assert should_exit is False

    def test_get_strategy_for_short_position(self, exit_manager, short_held_position):
        """Should return hold_to_resolution for short positions."""
        strategy = exit_manager.get_strategy_for_position(short_held_position)

        assert strategy == "hold_to_resolution"

    def test_get_strategy_for_long_position(self, exit_manager, long_held_position):
        """Should return conditional_exit for long positions."""
        strategy = exit_manager.get_strategy_for_position(long_held_position)

        assert strategy == "conditional_exit"


class TestExitExecution:
    """Tests for executing exits."""

    @pytest.mark.asyncio
    async def test_submits_sell_order_on_exit(
        self, exit_manager, long_held_position, mock_clob_client
    ):
        """Should submit SELL order when exit triggered."""
        # Add position to tracker
        exit_manager._position_tracker.positions[long_held_position.position_id] = long_held_position

        await exit_manager.execute_exit(
            long_held_position,
            current_price=Decimal("0.99"),
            reason="profit_target"
        )

        # Should have submitted sell order
        mock_clob_client.create_and_post_order.assert_called()
        order_args = mock_clob_client.create_and_post_order.call_args[0][0]
        assert order_args.side == "SELL"  # OrderArgs is a dataclass, use attribute access

    @pytest.mark.asyncio
    async def test_closes_position_on_exit(
        self, exit_manager, long_held_position, mock_db
    ):
        """Should close position when exit executed."""
        exit_manager._position_tracker.positions[long_held_position.position_id] = long_held_position

        await exit_manager.execute_exit(
            long_held_position,
            current_price=Decimal("0.99"),
            reason="profit_target"
        )

        # Position should be closed
        position = exit_manager._position_tracker.get_position(long_held_position.position_id)
        assert position.status == "closed"

    @pytest.mark.asyncio
    async def test_returns_true_on_success(
        self, exit_manager, long_held_position, mock_db, mock_clob_client
    ):
        """Should return (True, order_id) when exit succeeds."""
        exit_manager._position_tracker.positions[long_held_position.position_id] = long_held_position

        success, order_id = await exit_manager.execute_exit(
            long_held_position,
            current_price=Decimal("0.99"),
            reason="profit_target"
        )

        assert success is True
        assert order_id is not None


class TestExitBoundaries:
    """Tests for exit strategy boundary conditions."""

    @pytest.mark.parametrize("days_held,expected_strategy", [
        (6, "hold_to_resolution"),
        (7, "conditional_exit"),  # Exactly at threshold
        (8, "conditional_exit"),
        (30, "conditional_exit"),
    ])
    def test_hold_days_boundary(self, exit_manager, sample_position, days_held, expected_strategy):
        """Should apply correct strategy based on hold duration."""
        hold_time = datetime.now(timezone.utc) - timedelta(days=days_held)
        sample_position.entry_time = hold_time
        sample_position.hold_start_at = hold_time  # Must update both for consistent hold duration

        strategy = exit_manager.get_strategy_for_position(sample_position)

        assert strategy == expected_strategy

    @pytest.mark.parametrize("price,expected_exit", [
        (Decimal("0.89"), True),   # Below stop loss
        (Decimal("0.90"), True),   # At stop loss
        (Decimal("0.91"), False),  # Above stop loss
        (Decimal("0.98"), False),  # Below profit target
        (Decimal("0.99"), True),   # At profit target
        (Decimal("1.00"), True),   # Above profit target
    ])
    def test_price_boundaries(
        self, exit_manager, long_held_position, price, expected_exit
    ):
        """Should exit at correct price boundaries."""
        should_exit, _ = exit_manager.evaluate_exit(
            long_held_position,
            current_price=price
        )

        assert should_exit == expected_exit


class TestBatchEvaluation:
    """Tests for evaluating multiple positions."""

    @pytest.mark.asyncio
    async def test_evaluate_all_positions(self, exit_manager, long_held_position):
        """Should evaluate all open positions."""
        exit_manager._position_tracker.positions[long_held_position.position_id] = long_held_position

        current_prices = {
            "tok_yes_abc": Decimal("0.99"),  # At profit target
        }

        exits = await exit_manager.evaluate_all_positions(current_prices)

        assert len(exits) == 1
        assert exits[0][0].position_id == long_held_position.position_id
        assert exits[0][1] == "profit_target"

    @pytest.mark.asyncio
    async def test_process_exits(self, exit_manager, long_held_position, mock_db, mock_clob_client):
        """Should process all pending exits."""
        exit_manager._position_tracker.positions[long_held_position.position_id] = long_held_position

        current_prices = {
            "tok_yes_abc": Decimal("0.99"),
        }

        count = await exit_manager.process_exits(current_prices)

        assert count == 1


class TestMarketResolution:
    """Tests for handling market resolution."""

    @pytest.mark.asyncio
    async def test_handles_yes_resolution(self, exit_manager, sample_position, mock_db):
        """Should handle market resolving to Yes."""
        exit_manager._position_tracker.positions[sample_position.position_id] = sample_position
        exit_manager._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        result = await exit_manager.handle_resolution(
            token_id="tok_yes_abc",
            resolved_price=Decimal("1.00"),
        )

        assert result is True

        # Position should be closed
        position = exit_manager._position_tracker.get_position(sample_position.position_id)
        assert position.status == "closed"

    @pytest.mark.asyncio
    async def test_handles_no_resolution(self, exit_manager, sample_position, mock_db):
        """Should handle market resolving to No."""
        exit_manager._position_tracker.positions[sample_position.position_id] = sample_position
        exit_manager._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        result = await exit_manager.handle_resolution(
            token_id="tok_yes_abc",
            resolved_price=Decimal("0.00"),
        )

        assert result is True

        # Check exit event reason
        events = exit_manager._position_tracker.get_exit_events(sample_position.position_id)
        assert events[0].reason == "resolution_no"

    @pytest.mark.asyncio
    async def test_ignores_unknown_token(self, exit_manager):
        """Should return False for unknown token."""
        result = await exit_manager.handle_resolution(
            token_id="tok_unknown",
            resolved_price=Decimal("1.00"),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_resolution_clears_pending_exit_state(
        self, exit_manager, sample_position, mock_db
    ):
        """Resolution should clear pending exit flags to avoid stuck positions."""
        sample_position.exit_pending = True
        sample_position.exit_order_id = "order_pending"
        sample_position.exit_status = "pending"
        exit_manager._position_tracker.positions[sample_position.position_id] = sample_position
        exit_manager._position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        result = await exit_manager.handle_resolution(
            token_id=sample_position.token_id,
            resolved_price=Decimal("1.00"),
        )

        assert result is True
        position = exit_manager._position_tracker.get_position(sample_position.position_id)
        assert position.exit_pending is False
        assert position.exit_order_id is None
        assert position.exit_status is None


class TestConfigOverrides:
    """Tests for configuration overrides."""

    def test_custom_profit_target(self, mock_db, mock_clob_client, position_tracker):
        """Should use custom profit target."""
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            profit_target=Decimal("0.98"),  # Custom target
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_test",
            token_id="tok_test",
            condition_id="0xtest",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        should_exit, reason = manager.evaluate_exit(position, Decimal("0.98"))

        assert should_exit is True
        assert reason == "profit_target"

    def test_custom_stop_loss(self, mock_db, mock_clob_client, position_tracker):
        """Should use custom stop loss."""
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            stop_loss=Decimal("0.85"),  # Custom stop
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_test",
            token_id="tok_test",
            condition_id="0xtest",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        # 0.86 is above 0.85, should not exit
        should_exit, _ = manager.evaluate_exit(position, Decimal("0.86"))
        assert should_exit is False

        # 0.85 is at stop loss, should exit
        should_exit, reason = manager.evaluate_exit(position, Decimal("0.85"))
        assert should_exit is True
        assert reason == "stop_loss"


class TestOrderFillConfirmation:
    """
    Tests for waiting for order fill before closing position.

    FIX: Prevents desync between order state and position state.
    Without confirmation, position could be closed while order is rejected.
    """

    @pytest.mark.asyncio
    async def test_waits_for_order_fill_not_just_live(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Should wait for order to be FILLED, not just LIVE.

        FIX: LIVE means order is on book but NOT filled.
        We must wait for actual fill before closing position.
        """
        # Mock order status: LIVE (order is on book but NOT filled)
        mock_clob_client.get_order.return_value = {
            "orderID": "order_exit",
            "status": "LIVE",
            "filledSize": "0",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_wait",
            token_id="tok_wait",
            condition_id="0xwait",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
            wait_for_fill=True,
            fill_timeout_seconds=0.5,  # Short timeout for test
        )

        # FIX: Should FAIL - LIVE means not filled yet, times out
        success, order_id = result
        assert success is False

    @pytest.mark.asyncio
    async def test_live_to_matched_sequence(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Should succeed when order goes LIVE -> MATCHED.

        This tests the polling behavior where order is initially LIVE
        but eventually fills.
        """
        # Mock order status sequence: LIVE, then MATCHED
        call_count = [0]

        def get_order_side_effect(order_id):
            call_count[0] += 1
            if call_count[0] < 3:
                return {
                    "orderID": order_id,
                    "status": "LIVE",
                    "filledSize": "0",
                    "size": "20",
                }
            return {
                "orderID": order_id,
                "status": "MATCHED",
                "filledSize": "20",
                "size": "20",
            }

        mock_clob_client.get_order.side_effect = get_order_side_effect

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_sequence",
            token_id="tok_sequence",
            condition_id="0xsequence",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
            wait_for_fill=True,
            fill_timeout_seconds=5.0,
        )

        # Should succeed - order eventually filled
        success, order_id = result
        assert success is True

    @pytest.mark.asyncio
    async def test_does_not_close_on_rejection(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Should NOT close position if order is rejected.

        Desync prevention: position should remain open.
        """
        # Mock order status: REJECTED
        mock_clob_client.get_order.return_value = {
            "orderID": "order_rejected",
            "status": "REJECTED",
            "filledSize": "0",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_reject",
            token_id="tok_reject",
            condition_id="0xreject",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
            wait_for_fill=True,
            fill_timeout_seconds=1.0,
        )

        # Should fail - order was rejected
        success, order_id = result
        assert success is False

        # Position should NOT be closed
        pos = position_tracker.get_position(position.position_id)
        assert pos.status != "closed"

    @pytest.mark.asyncio
    async def test_does_not_close_on_expiration(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """Expired exit orders should not close positions."""
        mock_clob_client.get_order.return_value = {
            "orderID": "order_expired",
            "status": "EXPIRED",
            "filledSize": "0",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_expired",
            token_id="tok_expired",
            condition_id="0xexpired",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        success, order_id = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
            wait_for_fill=True,
            fill_timeout_seconds=1.0,
        )

        assert success is False
        pos = position_tracker.get_position(position.position_id)
        assert pos.status != "closed"

    @pytest.mark.asyncio
    async def test_accepts_matched_status(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Should accept MATCHED status as filled.
        """
        mock_clob_client.get_order.return_value = {
            "orderID": "order_matched",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_matched",
            token_id="tok_matched",
            condition_id="0xmatched",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        success, order_id = result
        assert success is True

    @pytest.mark.asyncio
    async def test_handles_timeout(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Should return False on timeout.

        Long polling with no terminal status should eventually timeout.
        """
        # Mock order stuck in PENDING state
        mock_clob_client.get_order.return_value = {
            "orderID": "order_stuck",
            "status": "PENDING",
            "filledSize": "0",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_timeout",
            token_id="tok_timeout",
            condition_id="0xtimeout",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
            wait_for_fill=True,
            fill_timeout_seconds=0.5,  # Very short timeout
        )

        # Should fail due to timeout
        success, order_id = result
        assert success is False

    @pytest.mark.asyncio
    async def test_refreshes_balance_after_resolution(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G4 FIX: Should refresh balance after resolution.

        Resolution settles positions and changes balance.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )
        # Mock refresh_balance for assertion
        manager._balance_manager.refresh_balance = MagicMock()

        position = Position(
            position_id="pos_resolve",
            token_id="tok_resolve",
            condition_id="0xresolve",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=1),
        )
        position_tracker.positions[position.position_id] = position
        position_tracker._token_positions[position.token_id] = position.position_id

        await manager.handle_resolution(
            token_id="tok_resolve",
            resolved_price=Decimal("1.00"),
        )

        # Balance should have been refreshed (G4 protection)
        manager._balance_manager.refresh_balance.assert_called()


class TestAtomicExitClaiming:
    """
    Tests for atomic exit order claiming to prevent duplicates.

    CRITICAL FIX: Without atomic claiming, two concurrent execute_exit
    calls could both pass _has_pending_exit and submit duplicate orders.
    """

    @pytest.mark.asyncio
    async def test_atomic_claim_succeeds_for_first_caller(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """First caller should successfully claim exit slot."""
        # Mock DB to return row ID on successful claim
        mock_db.fetchval.return_value = 1  # Simulates successful UPDATE RETURNING

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_atomic",
            token_id="tok_atomic",
            condition_id="0xatomic",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # First claim should succeed
        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        success, order_id = result
        assert success is True
        # Verify atomic claim was attempted
        mock_db.fetchval.assert_called()

    @pytest.mark.asyncio
    async def test_pending_exit_blocks_new_exit(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        If position has pending exit, new exit should be blocked.

        This tests the existing _has_pending_exit check.
        """
        # Mock order status to return LIVE (still pending, not filled)
        mock_clob_client.get_order.return_value = {
            "orderID": "order_existing",
            "status": "LIVE",
            "filledSize": "0",
            "size": "20",
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_pending",
            token_id="tok_pending",
            condition_id="0xpending",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
            # Already has pending exit
            exit_pending=True,
            exit_order_id="order_existing",
            exit_status="pending",
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        # Should return False - pending exit blocks new order
        success, order_id = result
        assert success is False

        # Should NOT have submitted a new order
        mock_clob_client.create_and_post_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleared_pending_allows_retry(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        After pending is cleared, new exit attempt should succeed.
        """
        # Mock DB to return row ID on successful claim
        mock_db.fetchval.return_value = 1

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_retry",
            token_id="tok_retry",
            condition_id="0xretry",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
            # Previously had pending that was cleared
            exit_pending=False,
            exit_status="cancelled",
            exit_order_id=None,
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        # Should succeed - pending was cleared
        success, order_id = result
        assert success is True
        mock_clob_client.create_and_post_order.assert_called()

    @pytest.mark.asyncio
    async def test_failed_order_clears_pending_state(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        If order submission fails, pending state should be cleared.

        This allows retry on next evaluation cycle.
        """
        # Mock DB to allow claim to succeed
        mock_db.fetchval.return_value = 1

        # Mock order submission returning no order_id
        mock_clob_client.create_and_post_order.return_value = {}

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_fail",
            token_id="tok_fail",
            condition_id="0xfail",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        # Should fail due to no order_id
        success, order_id = result
        assert success is False

        # Pending should be cleared to allow retry
        pos = position_tracker.get_position(position.position_id)
        assert pos.exit_pending is False
        assert pos.exit_status == "failed"

    @pytest.mark.asyncio
    async def test_exception_clears_pending_state(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        If execution raises exception, pending state should be cleared.
        """
        # Mock DB to allow claim to succeed
        mock_db.fetchval.return_value = 1

        # Mock order submission raising exception
        mock_clob_client.create_and_post_order.side_effect = Exception("API error")

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_exc",
            token_id="tok_exc",
            condition_id="0xexc",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        result = await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),
            reason="profit_target",
        )

        # Should fail due to exception
        success, order_id = result
        assert success is False

        # Pending should be cleared to allow retry
        pos = position_tracker.get_position(position.position_id)
        assert pos.exit_pending is False

    @pytest.mark.asyncio
    async def test_has_pending_exit_checks_status(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        _has_pending_exit should check both exit_pending and exit_status.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        # Position with exit_status=timeout should be considered pending
        position = Position(
            position_id="pos_timeout_status",
            token_id="tok_timeout_status",
            condition_id="0xtimeout_status",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
            exit_pending=False,  # Not marked pending
            exit_status="timeout",  # But has timeout status
            exit_order_id="order_old",
        )

        assert manager._has_pending_exit(position) is True

    @pytest.mark.asyncio
    async def test_atomic_claim_fails_for_second_caller(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Second caller should fail to claim if first already claimed.

        This tests the database-level exclusivity of the atomic claim.
        """
        # First call returns ID (success), second returns None (already claimed)
        call_count = [0]

        async def fetchval_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return 1  # First caller succeeds
            return None  # Second caller fails

        mock_db.fetchval.side_effect = fetchval_side_effect

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_race",
            token_id="tok_race",
            condition_id="0xrace",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # First claim succeeds
        claimed1 = await position_tracker.try_claim_exit_atomic(position.position_id)
        assert claimed1 is True

        # Reset position state for second claim test (simulate another process)
        position.exit_pending = False
        position.exit_status = None

        # Second claim fails (DB returns None)
        claimed2 = await position_tracker.try_claim_exit_atomic(position.position_id)
        assert claimed2 is False

    @pytest.mark.asyncio
    async def test_claiming_status_protected_from_reconcile(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        Position with exit_status='claiming' should NOT be cleared by reconcile.

        This protects against race where reconcile runs while order is being submitted.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        # Position in claiming state (order submission in progress)
        position = Position(
            position_id="pos_claiming",
            token_id="tok_claiming",
            condition_id="0xclaiming",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
            exit_pending=True,
            exit_status="claiming",
            exit_order_id=None,  # Order not submitted yet
        )
        position_tracker.positions[position.position_id] = position

        # Reconcile should return "pending", NOT "cleared"
        result = await manager.reconcile_pending_exit(position)

        assert result == "pending"
        # Position should still be pending
        assert position.exit_pending is True
        assert position.exit_status == "claiming"
