"""
Tests for order submission and tracking.

Orders interact with the Polymarket CLOB API.
All API calls must be mocked.
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from polymarket_bot.execution import (
    OrderManager,
    OrderConfig,
    OrderStatus,
    PriceTooHighError,
    InsufficientBalanceError,
)


class TestOrderSubmission:
    """Tests for submitting orders."""

    @pytest.mark.asyncio
    async def test_submits_buy_order(self, order_manager, mock_clob_client):
        """Should submit BUY order to CLOB."""
        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        assert order_id == "order_123"
        mock_clob_client.create_and_post_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_respects_max_price(self, order_manager):
        """Should reject orders above max price."""
        with pytest.raises(PriceTooHighError) as exc_info:
            await order_manager.submit_order(
                token_id="tok_yes_abc",
                side="BUY",
                price=Decimal("0.97"),  # Above max (0.95)
                size=Decimal("20"),
            )

        assert exc_info.value.price == Decimal("0.97")
        assert exc_info.value.max_price == Decimal("0.95")

    @pytest.mark.asyncio
    async def test_stores_order_in_cache(self, order_manager, mock_db):
        """Should store order in local cache."""
        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        order = order_manager.get_order(order_id)

        assert order is not None
        assert order.token_id == "tok_yes_abc"
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_persists_order_to_db(self, order_manager, mock_db):
        """Should persist order to database."""
        await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Verify DB was called
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_sell_orders_bypass_max_price(self, order_manager, mock_clob_client):
        """SELL orders should not be limited by max price."""
        mock_clob_client.create_and_post_order.return_value = {"orderID": "sell_order"}

        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="SELL",
            price=Decimal("0.99"),  # Above max, but OK for SELL
            size=Decimal("20"),
        )

        assert order_id == "sell_order"


class TestOrderTracking:
    """Tests for order status tracking."""

    @pytest.mark.asyncio
    async def test_syncs_order_status(self, order_manager, mock_clob_client, mock_db):
        """Should sync order status from CLOB."""
        # Submit order
        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Sync status
        order = await order_manager.sync_order_status(order_id)

        assert order.status == OrderStatus.FILLED
        assert order.filled_size == Decimal("20")

    @pytest.mark.asyncio
    async def test_detects_partial_fill(self, mock_db, mock_clob_partial_fill):
        """Should detect partially filled orders."""
        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_partial_fill,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        order = await manager.sync_order_status(order_id)

        assert order.status == OrderStatus.PARTIAL
        assert order.filled_size == Decimal("10")

    @pytest.mark.asyncio
    async def test_gets_open_orders(self, order_manager, mock_clob_client):
        """Should return list of open orders."""
        mock_clob_client.create_and_post_order.side_effect = [
            {"orderID": "order_1", "status": "LIVE"},
            {"orderID": "order_2", "status": "LIVE"},
        ]

        await order_manager.submit_order("tok_1", "BUY", Decimal("0.95"), Decimal("10"))
        await order_manager.submit_order("tok_2", "BUY", Decimal("0.94"), Decimal("10"))

        open_orders = order_manager.get_open_orders()

        assert len(open_orders) == 2


class TestOrderCancellation:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancels_order(self, order_manager, mock_clob_client, mock_db):
        """Should cancel order successfully."""
        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        result = await order_manager.cancel_order(order_id)

        assert result is True
        mock_clob_client.cancel.assert_called_with(order_id)

    @pytest.mark.asyncio
    async def test_updates_status_on_cancel(self, order_manager, mock_clob_client, mock_db):
        """Should update order status to cancelled."""
        order_id = await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        await order_manager.cancel_order(order_id)

        order = order_manager.get_order(order_id)
        assert order.status == OrderStatus.CANCELLED


class TestBalanceIntegration:
    """Tests for balance management integration."""

    @pytest.mark.asyncio
    async def test_reserves_balance_on_order(self, order_manager, mock_clob_client):
        """Should reserve balance when submitting order."""
        initial_balance = order_manager.get_available_balance()

        await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),  # Costs $19
        )

        new_balance = order_manager.get_available_balance()

        # Should have reserved $19
        assert new_balance == initial_balance - Decimal("19.00")

    @pytest.mark.asyncio
    async def test_releases_reservation_on_fill(self, order_manager, mock_clob_client, mock_db):
        """Should release reservation when order fills."""
        await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Before sync - balance is reserved
        balance_before = order_manager.get_available_balance()

        # Sync triggers fill and releases reservation
        await order_manager.sync_order_status("order_123")

        # After fill - reservation released (though balance actually decreases in real life)
        balance_after = order_manager.get_available_balance()

        # Reservation released, but balance refreshed
        assert balance_after > balance_before

    @pytest.mark.asyncio
    async def test_releases_reservation_on_cancel(self, order_manager, mock_clob_client):
        """Should release reservation when order cancelled."""
        await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        balance_with_reservation = order_manager.get_available_balance()

        await order_manager.cancel_order("order_123")

        balance_after_cancel = order_manager.get_available_balance()

        # Should have released the $19 reservation
        assert balance_after_cancel == balance_with_reservation + Decimal("19.00")


class TestBalanceRefresh:
    """Tests for G4 protection - balance cache staleness."""

    @pytest.mark.asyncio
    async def test_refreshes_balance_after_fill(self, order_manager, mock_clob_client, mock_db):
        """
        G4 PROTECTION: Should refresh balance after order fills.

        This prevents showing stale balance after trades.
        """
        # Initial balance
        order_manager.get_available_balance()

        # Submit and sync order
        await order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Update mock to return lower balance (simulating fill)
        mock_clob_client.get_balance_allowance.return_value = {"balance": "981000000"}

        # Sync triggers refresh
        await order_manager.sync_order_status("order_123")

        # Should have called get_balance after sync
        # (once on init, once on sync)
        assert mock_clob_client.get_balance_allowance.call_count >= 2


class TestLoadOrders:
    """Tests for loading orders from database on startup."""

    @pytest.mark.asyncio
    async def test_loads_open_orders_from_db(self, mock_db, mock_clob_client):
        """Should load pending/live/partial orders from database."""
        # Mock database to return open orders
        mock_db.fetch.return_value = [
            {
                "order_id": "order_db_1",
                "token_id": "tok_yes_abc",
                "condition_id": "0xtest123",
                "side": "BUY",
                "price": 0.95,
                "size": 20,
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "pending",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            }
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        count = await manager.load_orders()

        assert count == 1
        assert "order_db_1" in manager._orders

    @pytest.mark.asyncio
    async def test_restores_balance_reservations(self, mock_db, mock_clob_client):
        """Should restore balance reservations for loaded orders."""
        mock_db.fetch.return_value = [
            {
                "order_id": "order_restore",
                "token_id": "tok_yes_abc",
                "condition_id": "0xtest123",
                "side": "BUY",
                "price": 0.95,
                "size": 20,
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "live",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            }
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        await manager.load_orders()

        new_balance = manager.get_available_balance()

        # Should have reserved 20 * 0.95 = $19
        assert new_balance == initial_balance - Decimal("19.00")

    @pytest.mark.asyncio
    async def test_restores_partial_fill_reservations(self, mock_db, mock_clob_client):
        """Should restore reservations for unfilled portion only."""
        mock_db.fetch.return_value = [
            {
                "order_id": "order_partial",
                "token_id": "tok_yes_abc",
                "condition_id": "0xtest123",
                "side": "BUY",
                "price": 0.95,
                "size": 20,
                "filled_size": 10,  # 50% filled
                "avg_fill_price": 0.95,
                "status": "partial",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            }
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        await manager.load_orders()

        new_balance = manager.get_available_balance()

        # Should only reserve unfilled portion: 10 * 0.95 = $9.50
        assert new_balance == initial_balance - Decimal("9.50")

    @pytest.mark.asyncio
    async def test_handles_insufficient_balance_gracefully(self, mock_db, mock_clob_client):
        """Should track orders even when reservation fails due to low balance."""
        # Return multiple orders that together exceed balance
        mock_db.fetch.return_value = [
            {
                "order_id": "order_1",
                "token_id": "tok_1",
                "condition_id": "0x1",
                "side": "BUY",
                "price": 0.95,
                "size": 500,  # $475 - this will work
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "live",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            },
            {
                "order_id": "order_2",
                "token_id": "tok_2",
                "condition_id": "0x2",
                "side": "BUY",
                "price": 0.95,
                "size": 1000,  # $950 - this will exceed balance
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "live",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            },
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        # Should not raise - handles gracefully
        count = await manager.load_orders()

        # Should still track both orders
        assert count == 2
        assert "order_1" in manager._orders
        assert "order_2" in manager._orders

    @pytest.mark.asyncio
    async def test_loads_multiple_orders(self, mock_db, mock_clob_client):
        """Should load multiple orders correctly."""
        mock_db.fetch.return_value = [
            {
                "order_id": f"order_{i}",
                "token_id": f"tok_{i}",
                "condition_id": f"0x{i}",
                "side": "BUY",
                "price": 0.95,
                "size": 10,
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "live",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            }
            for i in range(5)
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        count = await manager.load_orders()

        assert count == 5
        assert len(manager._orders) == 5

    @pytest.mark.asyncio
    async def test_loads_zero_orders_when_db_empty(self, mock_db, mock_clob_client):
        """Should handle empty database gracefully."""
        mock_db.fetch.return_value = []

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        count = await manager.load_orders()

        assert count == 0
        assert len(manager._orders) == 0

    @pytest.mark.asyncio
    async def test_sell_orders_skip_reservation(self, mock_db, mock_clob_client):
        """SELL orders should not create reservations (they don't consume balance)."""
        mock_db.fetch.return_value = [
            {
                "order_id": "sell_order",
                "token_id": "tok_yes_abc",
                "condition_id": "0xtest123",
                "side": "SELL",
                "price": 0.99,
                "size": 20,
                "filled_size": 0,
                "avg_fill_price": None,
                "status": "live",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            }
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        await manager.load_orders()

        new_balance = manager.get_available_balance()

        # SELL orders don't reserve balance
        assert new_balance == initial_balance
