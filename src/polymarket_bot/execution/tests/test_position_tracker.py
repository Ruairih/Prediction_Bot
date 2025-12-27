"""
Tests for position tracking.

Positions are created when orders fill and closed when markets resolve.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from polymarket_bot.execution import (
    PositionTracker,
    Position,
    Order,
    OrderStatus,
)


class TestPositionCreation:
    """Tests for creating positions from fills."""

    @pytest.mark.asyncio
    async def test_creates_position_from_fill(self, position_tracker, mock_db, filled_order):
        """Should create position when order fills."""
        await position_tracker.record_fill(filled_order)

        positions = position_tracker.get_open_positions()

        assert len(positions) == 1
        assert positions[0].token_id == "tok_yes_abc"
        assert positions[0].size == Decimal("20")

    @pytest.mark.asyncio
    async def test_ignores_unfilled_orders(self, position_tracker, sample_order):
        """Should not create position from pending order."""
        await position_tracker.record_fill(sample_order)

        positions = position_tracker.get_open_positions()

        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_ignores_zero_size_fill(self, position_tracker, mock_db):
        """Zero-size fills should not create positions."""
        zero_fill = Order(
            order_id="order_zero",
            token_id="tok_yes_abc",
            condition_id="0x123",
            side="BUY",
            size=Decimal("20"),
            filled_size=Decimal("0"),
            price=Decimal("0.95"),
            avg_fill_price=Decimal("0.95"),
            status=OrderStatus.FILLED,
        )

        position = await position_tracker.record_fill(zero_fill)

        assert position is None
        assert position_tracker.get_open_positions() == []

    @pytest.mark.asyncio
    async def test_aggregates_multiple_fills(self, position_tracker, mock_db):
        """Should aggregate fills for same token."""
        # First fill
        order1 = Order(
            order_id="order_1",
            token_id="tok_yes_abc",
            condition_id="0x123",
            side="BUY",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.94"),
            avg_fill_price=Decimal("0.94"),
            status=OrderStatus.FILLED,
        )
        await position_tracker.record_fill(order1)

        # Second fill for same token
        order2 = Order(
            order_id="order_2",
            token_id="tok_yes_abc",
            condition_id="0x123",
            side="BUY",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.96"),
            avg_fill_price=Decimal("0.96"),
            status=OrderStatus.FILLED,
        )
        await position_tracker.record_fill(order2)

        positions = position_tracker.get_open_positions()

        assert len(positions) == 1
        assert positions[0].size == Decimal("20")
        # Average entry price: (10*0.94 + 10*0.96) / 20 = 0.95
        assert positions[0].entry_price == Decimal("0.95")

    @pytest.mark.asyncio
    async def test_calculates_entry_cost(self, position_tracker, filled_order):
        """Should calculate entry cost correctly."""
        await position_tracker.record_fill(filled_order)

        position = position_tracker.get_open_positions()[0]

        # 20 shares * $0.95 = $19.00
        assert position.entry_cost == Decimal("19.00")


class TestPositionValuation:
    """Tests for position P&L calculation."""

    def test_calculates_unrealized_pnl(self, position_tracker, sample_position):
        """Should calculate unrealized P&L."""
        position_tracker.positions[sample_position.position_id] = sample_position

        # Current price is 99c
        pnl = position_tracker.calculate_pnl(
            sample_position.position_id,
            current_price=Decimal("0.99")
        )

        # Bought at 95c, now 99c, size 20
        # PnL = 20 * (0.99 - 0.95) = $0.80
        assert pnl == Decimal("0.80")

    def test_calculates_negative_pnl(self, position_tracker, sample_position):
        """Should calculate negative P&L correctly."""
        position_tracker.positions[sample_position.position_id] = sample_position

        # Current price dropped to 90c
        pnl = position_tracker.calculate_pnl(
            sample_position.position_id,
            current_price=Decimal("0.90")
        )

        # Bought at 95c, now 90c, size 20
        # PnL = 20 * (0.90 - 0.95) = -$1.00
        assert pnl == Decimal("-1.00")

    def test_returns_zero_for_unknown_position(self, position_tracker):
        """Should return zero for non-existent position."""
        pnl = position_tracker.calculate_pnl(
            "nonexistent_position",
            current_price=Decimal("0.99")
        )

        assert pnl == Decimal("0")

    def test_calculates_total_pnl(self, position_tracker, sample_position):
        """Should calculate total P&L across positions."""
        position_tracker.positions[sample_position.position_id] = sample_position

        # Create second position
        position2 = Position(
            position_id="pos_456",
            token_id="tok_yes_xyz",
            condition_id="0xtest456",
            size=Decimal("10"),
            entry_price=Decimal("0.90"),
            entry_cost=Decimal("9.00"),
            entry_time=datetime.now(timezone.utc),
        )
        position_tracker.positions[position2.position_id] = position2

        prices = {
            "tok_yes_abc": Decimal("0.99"),  # +$0.80
            "tok_yes_xyz": Decimal("0.95"),  # +$0.50
        }

        total_pnl = position_tracker.calculate_total_pnl(prices)

        assert total_pnl == Decimal("1.30")


class TestPositionClosure:
    """Tests for closing positions."""

    @pytest.mark.asyncio
    async def test_closes_position(self, position_tracker, mock_db, sample_position):
        """Should close position."""
        position_tracker.positions[sample_position.position_id] = sample_position

        await position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("1.00"),
            reason="resolution_yes"
        )

        open_positions = position_tracker.get_open_positions()
        assert len(open_positions) == 0

    @pytest.mark.asyncio
    async def test_records_exit_event(self, position_tracker, mock_db, sample_position):
        """Should record exit event for audit trail."""
        position_tracker.positions[sample_position.position_id] = sample_position

        await position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("0.99"),
            reason="profit_target"
        )

        exit_events = position_tracker.get_exit_events(sample_position.position_id)

        assert len(exit_events) == 1
        assert exit_events[0].exit_price == Decimal("0.99")
        assert exit_events[0].reason == "profit_target"

    @pytest.mark.asyncio
    async def test_calculates_realized_pnl(self, position_tracker, mock_db, sample_position):
        """Should calculate realized P&L on close."""
        position_tracker.positions[sample_position.position_id] = sample_position

        exit_event = await position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("0.99"),
            reason="profit_target"
        )

        # Entry: 0.95, Exit: 0.99, Size: 20
        # PnL = 20 * (0.99 - 0.95) = $0.80
        assert exit_event.net_pnl == Decimal("0.80")

    @pytest.mark.asyncio
    async def test_records_negative_realized_pnl(self, position_tracker, mock_db, sample_position):
        """Should record negative realized P&L on loss."""
        position_tracker.positions[sample_position.position_id] = sample_position

        exit_event = await position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("0.90"),
            reason="stop_loss",
        )

        assert exit_event is not None
        assert exit_event.net_pnl == Decimal("-1.00")
        assert position_tracker.positions[sample_position.position_id].realized_pnl == Decimal("-1.00")

    @pytest.mark.asyncio
    async def test_persists_exit_metadata(self, position_tracker, mock_db, sample_position):
        """Should persist exit_order_id and exit_timestamp when closing."""
        position_tracker.positions[sample_position.position_id] = sample_position

        exit_order_id = "exit_order_123"
        await position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("0.99"),
            reason="profit_target",
            exit_order_id=exit_order_id,
        )

        position_call = None
        for call in mock_db.execute.call_args_list:
            if "INSERT INTO positions" in call.args[0]:
                position_call = call
                break

        assert position_call is not None
        assert position_call.args[9] == exit_order_id
        assert position_call.args[10] is False
        assert position_call.args[11] == "filled"
        assert isinstance(position_call.args[12], str)
        assert position_call.args[12].endswith("Z")


class TestPositionLoading:
    """Tests for loading positions from storage."""

    @pytest.mark.asyncio
    async def test_normalizes_naive_timestamps(self, position_tracker, mock_db):
        """Should normalize naive timestamps to UTC."""
        mock_db.fetch.return_value = [
            {
                "position_id": "1",
                "token_id": "tok_yes_abc",
                "condition_id": "0x123",
                "size": 10,
                "entry_price": 0.95,
                "entry_cost": 9.5,
                "entry_time": "2025-01-01T00:00:00",
                "realized_pnl": 0,
                "status": "open",
                "hold_start_at": "2025-01-02T00:00:00",
                "import_source": None,
            }
        ]

        await position_tracker.load_positions()

        position = position_tracker.get_position("1")
        assert position is not None
        assert position.entry_time.tzinfo == timezone.utc
        assert position.hold_start_at is not None
        assert position.hold_start_at.tzinfo == timezone.utc


class TestPositionRetrieval:
    """Tests for retrieving positions."""

    def test_get_position_by_id(self, position_tracker, sample_position):
        """Should retrieve position by ID."""
        position_tracker.positions[sample_position.position_id] = sample_position

        position = position_tracker.get_position(sample_position.position_id)

        assert position is not None
        assert position.position_id == sample_position.position_id

    def test_get_position_by_token(self, position_tracker, sample_position):
        """Should retrieve position by token ID."""
        position_tracker.positions[sample_position.position_id] = sample_position
        position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        position = position_tracker.get_position_by_token(sample_position.token_id)

        assert position is not None
        assert position.token_id == sample_position.token_id

    def test_returns_none_for_unknown(self, position_tracker):
        """Should return None for unknown position."""
        position = position_tracker.get_position("unknown_id")

        assert position is None


class TestSellOrders:
    """Tests for SELL order handling."""

    @pytest.mark.asyncio
    async def test_sell_reduces_position(self, position_tracker, sample_position, mock_db):
        """SELL order should reduce position size."""
        position_tracker.positions[sample_position.position_id] = sample_position
        position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        sell_order = Order(
            order_id="sell_1",
            token_id="tok_yes_abc",
            condition_id="0xtest123",
            side="SELL",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.99"),
            avg_fill_price=Decimal("0.99"),
            status=OrderStatus.FILLED,
        )

        await position_tracker.record_fill(sell_order)

        position = position_tracker.get_position(sample_position.position_id)

        assert position.size == Decimal("10")  # 20 - 10

    @pytest.mark.asyncio
    async def test_sell_records_realized_pnl(self, position_tracker, sample_position, mock_db):
        """SELL should record realized P&L."""
        position_tracker.positions[sample_position.position_id] = sample_position
        position_tracker._token_positions[sample_position.token_id] = sample_position.position_id

        sell_order = Order(
            order_id="sell_1",
            token_id="tok_yes_abc",
            condition_id="0xtest123",
            side="SELL",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.99"),
            avg_fill_price=Decimal("0.99"),
            status=OrderStatus.FILLED,
        )

        await position_tracker.record_fill(sell_order)

        position = position_tracker.get_position(sample_position.position_id)

        # PnL = 10 * (0.99 - 0.95) = $0.40
        assert position.realized_pnl == Decimal("0.40")
