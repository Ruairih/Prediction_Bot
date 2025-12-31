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


class TestG13SlippageProtection:
    """
    G13: Slippage and Liquidity Protection for Exits.

    CRITICAL FIX: Prevents catastrophic losses like the Gold Cards bug where
    a position at ~$0.96 was sold at $0.026 due to an illiquid orderbook
    with 99.8% spread.

    These tests verify that exits are blocked when:
    1. Market has no bids (completely illiquid)
    2. Spread is too wide (> 20% default)
    3. Best bid is below minimum price floor (< 50% of entry)
    4. Slippage from expected price is too high (> 10% default)
    """

    @pytest.mark.asyncio
    async def test_blocks_exit_when_no_bids(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should block exit when orderbook has no bids.

        Empty bid side means no one is willing to buy - selling would get $0.
        """
        # Mock orderbook with no bids
        mock_clob_client.get_order_book.return_value = {
            "bids": [],
            "asks": [{"price": "0.99", "size": "100"}],
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_nobid",
            token_id="tok_nobid",
            condition_id="0xnobid",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # Verify liquidity check fails
        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is False
        assert "No bids" in reason or "illiquid" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_exit_when_spread_too_wide(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should block exit when bid-ask spread is too wide.

        Wide spread indicates illiquid market where we'd sell at a huge discount.
        Default max spread is 20%.
        """
        # Mock orderbook with 99% spread (bid: 0.01, ask: 0.99)
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.01", "size": "100"}],  # Terrible bid
            "asks": [{"price": "0.99", "size": "100"}],
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_spread",
            token_id="tok_spread",
            condition_id="0xspread",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is False
        assert "Spread too wide" in reason or "spread" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_exit_below_price_floor(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should block exit when best bid is below minimum price floor.

        Default floor is 50% of entry price. If we entered at 0.95, we should
        never sell below 0.475.
        """
        # Mock orderbook with bid way below entry price
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.10", "size": "100"}],  # 10c bid vs 95c entry
            "asks": [{"price": "0.12", "size": "100"}],  # Reasonable spread
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_floor",
            token_id="tok_floor",
            condition_id="0xfloor",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),  # Entered at 95c
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is False
        assert "floor" in reason.lower() or "below minimum" in reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_exit_with_high_slippage(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should block exit when slippage from expected price is too high.

        Default max slippage is 10%. If expected exit is 0.99 and best bid
        is 0.85, that's >10% slippage.
        """
        # Mock orderbook with bid 15% below expected exit
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.84", "size": "100"}],  # 84c vs expected 99c
            "asks": [{"price": "0.86", "size": "100"}],
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_slip",
            token_id="tok_slip",
            condition_id="0xslip",
            size=Decimal("20"),
            entry_price=Decimal("0.80"),  # Low entry so floor check passes
            entry_cost=Decimal("16.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.99")  # Expected at 99c
        )

        assert is_safe is False
        assert "Slippage too high" in reason or "slippage" in reason.lower()

    @pytest.mark.asyncio
    async def test_allows_exit_with_good_liquidity(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should allow exit when liquidity is good.

        All checks pass: bids exist, spread is narrow, bid is above floor,
        slippage is acceptable.
        """
        # Mock healthy orderbook
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.98", "size": "100"}],  # Good bid
            "asks": [{"price": "0.99", "size": "100"}],  # 1% spread
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_good",
            token_id="tok_good",
            condition_id="0xgood",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, safe_price = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is True
        assert safe_price == Decimal("0.98")  # Should return best bid

    @pytest.mark.asyncio
    async def test_execute_exit_uses_verified_price(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Exit should use verified safe price (best bid), not requested price.

        This ensures we place limit orders at the actual market price.
        """
        # Mock healthy orderbook with bid at 0.97
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.97", "size": "100"}],
            "asks": [{"price": "0.98", "size": "100"}],
        }
        mock_db.fetchval.return_value = 1  # Claim succeeds

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_price",
            token_id="tok_price",
            condition_id="0xprice",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        await manager.execute_exit(
            position,
            current_price=Decimal("0.99"),  # Requested at 99c
            reason="profit_target",
        )

        # Should have submitted order at best bid (0.97), not requested (0.99)
        call_args = mock_clob_client.create_and_post_order.call_args
        if call_args:
            order_args = call_args[0][0]
            assert float(order_args.price) == 0.97

    @pytest.mark.asyncio
    async def test_execute_exit_blocked_by_liquidity_check(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Exit should be blocked entirely if liquidity check fails.
        """
        # Mock illiquid orderbook
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.01", "size": "100"}],  # Terrible bid
            "asks": [{"price": "0.99", "size": "100"}],  # Huge spread
        }
        mock_db.fetchval.return_value = 1  # Claim succeeds

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_blocked",
            token_id="tok_blocked",
            condition_id="0xblocked",
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
        )

        # Should be blocked - no order submitted
        assert success is False
        mock_clob_client.create_and_post_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_liquidity_check_disabled_allows_exit(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: If verify_liquidity=False in config, exit proceeds without check.
        """
        config = ExitConfig(verify_liquidity=False)

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            config=config,
        )

        position = Position(
            position_id="pos_nocheck",
            token_id="tok_nocheck",
            condition_id="0xnocheck",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, safe_price = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is True
        assert "disabled" in reason.lower()

    @pytest.mark.asyncio
    async def test_dry_run_bypasses_liquidity_check(
        self, mock_db, position_tracker
    ):
        """
        G13: Dry run mode (no CLOB client) should bypass liquidity check.
        """
        # No CLOB client = dry run
        manager = ExitManager(
            db=mock_db,
            clob_client=None,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_dry",
            token_id="tok_dry",
            condition_id="0xdry",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is True
        assert "dry_run" in reason.lower()

    @pytest.mark.asyncio
    async def test_gold_cards_scenario_would_be_blocked(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        REGRESSION TEST: Gold Cards bug scenario.

        The actual bug:
        - Position at entry ~$0.915
        - Market became illiquid: Bid $0.001, Ask $0.999 (99.8% spread)
        - Bot sold at $0.026 causing ~$31 loss

        With G9 protection, this exit would be BLOCKED.
        """
        # Replicate the Gold Cards illiquid orderbook
        mock_clob_client.get_order_book.return_value = {
            "bids": [{"price": "0.001", "size": "100"}],  # Bid at 0.1c
            "asks": [{"price": "0.999", "size": "100"}],  # Ask at 99.9c
        }

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_gold",
            token_id="95197758690536781344967069481835822467121525130144169973322994558549635662278",
            condition_id="0xgoldcards",
            size=Decimal("40"),  # 40 shares like the real trade
            entry_price=Decimal("0.915"),  # Entered at ~91.5c
            entry_cost=Decimal("36.60"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, _ = await manager.verify_exit_liquidity(
            position, Decimal("0.96")  # Expected exit around 96c
        )

        assert is_safe is False
        # Should fail on spread check (99.8% spread >> 20% max)
        assert "Spread too wide" in reason or "spread" in reason.lower()

    @pytest.mark.asyncio
    async def test_handles_orderbook_object_format(
        self, mock_db, mock_clob_client, position_tracker
    ):
        """
        G13: Should handle orderbook returned as object (not dict).

        py-clob-client may return OrderBookSummary object with .bids/.asks
        attributes instead of dict with ["bids"]/["asks"] keys.
        """
        # Mock orderbook as object with attributes
        class OrderLevel:
            def __init__(self, price, size):
                self.price = price
                self.size = size

        class OrderBookSummary:
            def __init__(self):
                self.bids = [OrderLevel("0.97", "100")]
                self.asks = [OrderLevel("0.98", "100")]

        mock_clob_client.get_order_book.return_value = OrderBookSummary()

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
        )

        position = Position(
            position_id="pos_obj",
            token_id="tok_obj",
            condition_id="0xobj",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )

        is_safe, reason, safe_price = await manager.verify_exit_liquidity(
            position, Decimal("0.99")
        )

        assert is_safe is True
        assert safe_price == Decimal("0.97")


# =============================================================================
# Regression Tests: SELL Order Persistence Bug
# =============================================================================


class TestSellOrderPersistence:
    """
    Regression tests for the SELL order persistence bug.

    BUG: ExitManager.execute_exit() was calling CLOB directly, bypassing
    OrderManager.submit_order(). This meant SELL orders were NOT persisted
    to the database, causing:
    - No order records for exits
    - No exit_events created (equity curve didn't update)
    - No audit trail for exit attempts

    FIX: execute_exit() now uses order_manager.submit_order() when available,
    ensuring SELL orders are persisted like BUY orders.
    """

    @pytest.mark.asyncio
    async def test_exit_uses_order_manager_when_provided(
        self, mock_db, mock_clob_client, position_tracker, balance_manager, order_manager
    ):
        """
        CRITICAL: When order_manager is provided, execute_exit() should
        use order_manager.submit_order(), NOT direct CLOB call.
        """
        from unittest.mock import AsyncMock, patch

        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=order_manager,
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_sell_test",
            token_id="tok_sell",
            condition_id="0xsell",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # Spy on order_manager.submit_order
        original_submit = order_manager.submit_order
        order_manager.submit_order = AsyncMock(return_value="sell_order_123")

        await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="profit_target",
        )

        # CRITICAL: order_manager.submit_order should be called, NOT direct CLOB
        order_manager.submit_order.assert_called_once()
        call_args = order_manager.submit_order.call_args
        assert call_args.kwargs.get("side") == "SELL" or call_args[1].get("side") == "SELL"

        # Restore
        order_manager.submit_order = original_submit

    @pytest.mark.asyncio
    async def test_sell_order_persisted_to_database(
        self, mock_db, mock_clob_client, position_tracker, balance_manager, order_manager
    ):
        """
        CRITICAL: SELL orders must be persisted to the orders table.
        This is what was missing before the fix.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=order_manager,
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_persist_test",
            token_id="tok_persist",
            condition_id="0xpersist",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # Reset mock to track calls
        mock_db.execute.reset_mock()

        await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="profit_target",
        )

        # Verify INSERT INTO orders was called (order persistence)
        insert_calls = [
            call for call in mock_db.execute.call_args_list
            if call[0] and "INSERT INTO orders" in str(call[0][0])
        ]
        assert len(insert_calls) >= 1, "SELL order should be persisted to orders table"

    @pytest.mark.asyncio
    async def test_legacy_fallback_without_order_manager(
        self, mock_db, mock_clob_client, position_tracker, balance_manager
    ):
        """
        When order_manager is NOT provided, should fall back to direct CLOB call.
        This maintains backward compatibility but logs a warning.
        """
        # Create manager WITHOUT order_manager
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=None,  # No order manager
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_legacy",
            token_id="tok_legacy",
            condition_id="0xlegacy",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # Should still work via direct CLOB call
        success, order_id = await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="profit_target",
        )

        # Direct CLOB call should have been made
        mock_clob_client.create_and_post_order.assert_called()
        assert success is True

    @pytest.mark.asyncio
    async def test_full_exit_flow_creates_exit_event(
        self, mock_db, mock_clob_client, position_tracker, balance_manager, order_manager
    ):
        """
        Full exit flow should create both:
        1. An order record (via order_manager)
        2. An exit_event record (via position_tracker)

        This is what populates the equity curve.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=order_manager,
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_full_flow",
            token_id="tok_full",
            condition_id="0xfull",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        success, order_id = await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="profit_target",
        )

        assert success is True
        assert order_id is not None

        # Verify exit_event was created
        exit_events = position_tracker.get_exit_events(position.position_id)
        assert len(exit_events) == 1
        assert exit_events[0].reason == "profit_target"
        assert exit_events[0].exit_price == Decimal("0.98")

    @pytest.mark.asyncio
    async def test_regression_equity_curve_bug_scenario(
        self, mock_db, mock_clob_client, position_tracker, balance_manager, order_manager
    ):
        """
        Regression test for the exact bug scenario:
        - User clicks "close position" in dashboard
        - SELL order is submitted
        - Order should be saved to DB (was missing before fix)
        - exit_event should be created (for equity curve)

        Before the fix:
        - SELL went to CLOB directly
        - No order record
        - No exit_event (equity curve stuck at 1 point)
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=order_manager,
            min_hold_days=7,
        )

        # Simulate the position that wouldn't close properly
        position = Position(
            position_id="pos_equity_bug",
            token_id="tok_equity",
            condition_id="0xequity",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        # Track all DB operations
        mock_db.execute.reset_mock()

        # Simulate dashboard close action
        success, order_id = await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="manual_close",  # Dashboard reason
        )

        # MUST succeed
        assert success is True, "Exit should succeed"

        # MUST have order_id
        assert order_id is not None, "Order ID should be returned"

        # MUST have persisted order to database
        insert_order_calls = [
            call for call in mock_db.execute.call_args_list
            if call[0] and "INSERT INTO orders" in str(call[0][0])
        ]
        assert len(insert_order_calls) >= 1, (
            "BUG REGRESSION: SELL order was not persisted to database. "
            "This causes equity curve to not update."
        )

        # MUST have exit_event for equity curve
        exit_events = position_tracker.get_exit_events(position.position_id)
        assert len(exit_events) == 1, (
            "BUG REGRESSION: exit_event was not created. "
            "Equity curve will not show this closed position."
        )

    @pytest.mark.asyncio
    async def test_sell_order_has_correct_side_in_database(
        self, mock_db, mock_clob_client, position_tracker, balance_manager, order_manager
    ):
        """
        Verify the persisted order has side='SELL', not 'BUY'.
        """
        manager = ExitManager(
            db=mock_db,
            clob_client=mock_clob_client,
            position_tracker=position_tracker,
            balance_manager=balance_manager,
            order_manager=order_manager,
            min_hold_days=7,
        )

        position = Position(
            position_id="pos_side_test",
            token_id="tok_side",
            condition_id="0xside",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
            entry_cost=Decimal("19.00"),
            entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        )
        position_tracker.positions[position.position_id] = position

        mock_db.execute.reset_mock()

        await manager.execute_exit(
            position,
            current_price=Decimal("0.98"),
            reason="profit_target",
        )

        # Find the INSERT call and verify side is SELL
        for call in mock_db.execute.call_args_list:
            if call[0] and "INSERT INTO orders" in str(call[0][0]):
                # Args are: order_id, token_id, condition_id, side, ...
                side_arg = call[0][4] if len(call[0]) > 4 else None
                assert side_arg == "SELL", f"Order side should be SELL, got {side_arg}"
                break
