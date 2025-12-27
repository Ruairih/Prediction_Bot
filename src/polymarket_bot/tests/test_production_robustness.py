"""
Production Robustness Tests.

These tests verify the bot handles production edge cases correctly:
- Network failures and retries
- Concurrent operations and race conditions
- State corruption and recovery
- Unexpected API responses
- Resource cleanup on failures

All tests use mocks - no real database or API required.
"""
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from polymarket_bot.execution import (
    OrderManager,
    OrderConfig,
    OrderStatus,
    PositionTracker,
    ExitManager,
    ExitConfig,
    ExecutionService,
    ExecutionConfig,
    InsufficientBalanceError,
)
from polymarket_bot.execution.order_manager import Order, OrderSubmissionError
from polymarket_bot.execution.position_tracker import Position


# =============================================================================
# Network Failure and Recovery Tests
# =============================================================================


class TestNetworkFailureRecovery:
    """Tests for handling network failures gracefully."""

    @pytest.fixture
    def mock_db(self):
        """Mock database."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value="INSERT 0")
        db.fetch = AsyncMock(return_value=[])
        db.fetchrow = AsyncMock(return_value=None)
        db.fetchval = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_clob_client(self):
        """Mock CLOB client."""
        client = MagicMock()
        client.create_and_post_order = MagicMock(return_value={"orderID": "order_123", "status": "LIVE"})
        client.get_order = MagicMock(return_value={
            "orderID": "order_123",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        })
        client.get_balance_allowance = MagicMock(return_value={"balance": "1000000000"})
        client.cancel = MagicMock(return_value=True)
        return client

    @pytest.mark.asyncio
    async def test_network_error_during_order_releases_reservation(self, mock_db, mock_clob_client):
        """Network error during order should release balance reservation."""
        mock_clob_client.create_and_post_order.side_effect = ConnectionError("Network error")

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        with pytest.raises(ConnectionError):
            await manager.submit_order(
                token_id="tok_test",
                side="BUY",
                price=Decimal("0.95"),
                size=Decimal("20"),
            )

        # Balance should be fully restored
        assert manager.get_available_balance() == initial_balance
        assert len(manager._balance_manager.get_active_reservations()) == 0

    @pytest.mark.asyncio
    async def test_timeout_during_order_releases_reservation(self, mock_db, mock_clob_client):
        """Timeout during order should release balance reservation."""
        mock_clob_client.create_and_post_order.side_effect = asyncio.TimeoutError()

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        with pytest.raises(asyncio.TimeoutError):
            await manager.submit_order(
                token_id="tok_test",
                side="BUY",
                price=Decimal("0.95"),
                size=Decimal("20"),
            )

        assert manager.get_available_balance() == initial_balance

    @pytest.mark.asyncio
    async def test_empty_order_id_releases_reservation(self, mock_db, mock_clob_client):
        """Empty order ID from CLOB should release reservation and not save order."""
        mock_clob_client.create_and_post_order.return_value = {"orderID": "", "status": "LIVE"}

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        with pytest.raises(OrderSubmissionError):
            await manager.submit_order(
                token_id="tok_test",
                side="BUY",
                price=Decimal("0.95"),
                size=Decimal("20"),
            )

        assert manager.get_available_balance() == initial_balance
        assert len(manager._orders) == 0

    @pytest.mark.asyncio
    async def test_none_order_id_releases_reservation(self, mock_db, mock_clob_client):
        """None order ID from CLOB should release reservation."""
        mock_clob_client.create_and_post_order.return_value = {"orderID": None, "status": "LIVE"}

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        with pytest.raises(OrderSubmissionError):
            await manager.submit_order(
                token_id="tok_test",
                side="BUY",
                price=Decimal("0.95"),
                size=Decimal("20"),
            )

        assert manager.get_available_balance() == initial_balance


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestConcurrentOperations:
    """Tests for handling concurrent operations safely."""

    @pytest.fixture
    def mock_db(self):
        """Mock database with transaction support."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value="INSERT 0")
        db.fetch = AsyncMock(return_value=[])
        db.fetchrow = AsyncMock(return_value=None)
        db.fetchval = AsyncMock(return_value=None)

        # Transaction context manager
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0")
        mock_conn.fetchval = AsyncMock(side_effect=[None, "tok_test"])

        class MockTransaction:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, *args):
                pass

        db.transaction = MagicMock(return_value=MockTransaction())
        db._mock_conn = mock_conn
        return db

    @pytest.fixture
    def mock_clob_client(self):
        """Mock CLOB client."""
        call_count = [0]

        def create_order(*args, **kwargs):
            call_count[0] += 1
            return {"orderID": f"order_{call_count[0]}", "status": "LIVE"}

        client = MagicMock()
        client.create_and_post_order = MagicMock(side_effect=create_order)
        client.get_order = MagicMock(return_value={
            "orderID": "order_1",
            "status": "LIVE",
            "filledSize": "0",
            "size": "20",
        })
        client.get_balance_allowance = MagicMock(return_value={"balance": "1000000000"})
        return client

    @pytest.mark.asyncio
    async def test_concurrent_orders_respect_balance(self, mock_db, mock_clob_client):
        """Concurrent order submissions should not over-allocate balance."""
        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        # Get initial balance
        initial_balance = manager.get_available_balance()

        # Submit orders concurrently
        async def submit_order(i):
            try:
                return await manager.submit_order(
                    token_id=f"tok_{i}",
                    side="BUY",
                    price=Decimal("0.95"),
                    size=Decimal("200"),  # $190 each
                )
            except InsufficientBalanceError:
                return None

        results = await asyncio.gather(*[submit_order(i) for i in range(10)])

        # Count successful orders
        successful = [r for r in results if r is not None]

        # With $1000 balance, should allow max 5 orders of $190 each
        assert len(successful) <= 5

        # Final balance should be non-negative
        final_balance = manager.get_available_balance()
        assert final_balance >= Decimal("0")

    @pytest.mark.asyncio
    async def test_concurrent_sync_operations_are_safe(self, mock_db, mock_clob_client):
        """Concurrent sync operations should not corrupt state."""
        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        # Submit an order first
        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Run multiple syncs concurrently
        await asyncio.gather(*[
            manager.sync_order_status(order_id)
            for _ in range(10)
        ])

        # Order should still be in valid state
        order = manager.get_order(order_id)
        assert order is not None
        assert order.status in [OrderStatus.PENDING, OrderStatus.LIVE, OrderStatus.FILLED]


# =============================================================================
# State Consistency Tests
# =============================================================================


class TestStateConsistency:
    """Tests for maintaining consistent state under various conditions."""

    @pytest.fixture
    def mock_db(self):
        """Mock database."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value="INSERT 0")
        db.fetch = AsyncMock(return_value=[])
        db.fetchrow = AsyncMock(return_value=None)
        db.fetchval = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_clob_client(self):
        """Mock CLOB client."""
        client = MagicMock()
        client.create_and_post_order = MagicMock(return_value={"orderID": "order_123", "status": "LIVE"})
        client.get_order = MagicMock(return_value={
            "orderID": "order_123",
            "status": "MATCHED",
            "filledSize": "20",
            "size": "20",
        })
        client.get_balance_allowance = MagicMock(return_value={"balance": "1000000000"})
        return client

    @pytest.mark.asyncio
    async def test_order_status_sync_updates_correctly(self, mock_db, mock_clob_client):
        """Order status should update correctly when synced from CLOB."""
        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Initial status should be PENDING or LIVE
        order = manager.get_order(order_id)
        assert order.status in [OrderStatus.PENDING, OrderStatus.LIVE]

        # Sync should update to FILLED
        await manager.sync_order_status(order_id)

        order = manager.get_order(order_id)
        assert order.status == OrderStatus.FILLED
        assert order.filled_size == Decimal("20")

    @pytest.mark.asyncio
    async def test_order_maintains_metadata_through_sync(self, mock_db, mock_clob_client):
        """Order metadata should be preserved through sync operations."""
        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        original_order = manager.get_order(order_id)
        original_token_id = original_order.token_id
        original_price = original_order.price

        # Sync
        await manager.sync_order_status(order_id)

        synced_order = manager.get_order(order_id)

        # Core metadata should be preserved
        assert synced_order.token_id == original_token_id
        assert synced_order.price == original_price


# =============================================================================
# Decimal Precision Tests
# =============================================================================


class TestDecimalPrecision:
    """Tests for handling decimal precision correctly."""

    def test_balance_calculation_precision(self):
        """Balance calculations should maintain precision."""
        balance = Decimal("1000.00")
        reservations = [
            Decimal("19.95"),
            Decimal("19.95"),
            Decimal("19.95"),
            Decimal("19.95"),
            Decimal("19.95"),
        ]

        total_reserved = sum(reservations)
        available = balance - total_reserved

        # Should be exactly 900.25, not floating point approximation
        assert available == Decimal("900.25")

    def test_pnl_calculation_precision(self):
        """PnL calculations should maintain precision."""
        entry_price = Decimal("0.95")
        exit_price = Decimal("0.99")
        size = Decimal("20")

        pnl = (exit_price - entry_price) * size

        # Should be exactly 0.80
        assert pnl == Decimal("0.80")

    def test_position_cost_precision(self):
        """Position cost calculations should maintain precision."""
        price = Decimal("0.9523")
        size = Decimal("21")

        cost = price * size

        # Should preserve precision
        assert cost == Decimal("19.9983")


# =============================================================================
# API Response Handling Tests
# =============================================================================


class TestAPIResponseHandling:
    """Tests for handling various API response formats."""

    @pytest.fixture
    def mock_db(self):
        """Mock database."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value="INSERT 0")
        db.fetch = AsyncMock(return_value=[])
        db.fetchrow = AsyncMock(return_value=None)
        db.fetchval = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_clob_client(self):
        """Mock CLOB client."""
        client = MagicMock()
        client.create_and_post_order = MagicMock(return_value={"orderID": "order_123", "status": "LIVE"})
        client.get_balance_allowance = MagicMock(return_value={"balance": "1000000000"})
        return client

    @pytest.mark.asyncio
    async def test_handles_string_numeric_values(self, mock_db, mock_clob_client):
        """Should handle API returning numbers as strings."""
        mock_clob_client.get_order.return_value = {
            "orderID": "order_123",
            "status": "LIVE",
            "filledSize": "10.5",  # String
            "size": "20",  # String
            "avgPrice": "0.945",  # String
        }

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        order = await manager.sync_order_status(order_id)

        assert order.filled_size == Decimal("10.5")
        assert order.avg_fill_price == Decimal("0.945")

    @pytest.mark.asyncio
    async def test_handles_missing_optional_fields(self, mock_db, mock_clob_client):
        """Should handle API responses with missing optional fields."""
        mock_clob_client.get_order.return_value = {
            "orderID": "order_123",
            "status": "LIVE",
            "filledSize": "0",
            "size": "20",
            # avgPrice missing
        }

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        order = await manager.sync_order_status(order_id)

        # Should not crash, avgPrice should be None
        assert order.avg_fill_price is None

    @pytest.mark.asyncio
    async def test_handles_unexpected_status_values(self, mock_db, mock_clob_client):
        """Should handle unexpected status values from API."""
        mock_clob_client.get_order.return_value = {
            "orderID": "order_123",
            "status": "UNKNOWN_STATUS",
            "filledSize": "0",
            "size": "20",
        }

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        order_id = await manager.submit_order(
            token_id="tok_test",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Should not crash
        order = await manager.sync_order_status(order_id)

        # Unknown status should default to PENDING (safe fallback)
        assert order.status == OrderStatus.PENDING


# =============================================================================
# Resource Cleanup Tests
# =============================================================================


class TestResourceCleanup:
    """Tests for proper resource cleanup."""

    @pytest.fixture
    def mock_db(self):
        """Mock database."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value="INSERT 0")
        db.fetch = AsyncMock(return_value=[])
        db.fetchrow = AsyncMock(return_value=None)
        db.fetchval = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_clob_client(self):
        """Mock CLOB client."""
        client = MagicMock()
        client.create_and_post_order = MagicMock(return_value={"orderID": "order_123", "status": "LIVE"})
        client.get_balance_allowance = MagicMock(return_value={"balance": "1000000000"})
        client.cancel = MagicMock(return_value=True)
        return client

    @pytest.mark.asyncio
    async def test_cancel_all_orders_releases_all_reservations(self, mock_db, mock_clob_client):
        """Cancelling all orders should release all reservations."""
        mock_clob_client.create_and_post_order.side_effect = [
            {"orderID": "order_1", "status": "LIVE"},
            {"orderID": "order_2", "status": "LIVE"},
            {"orderID": "order_3", "status": "LIVE"},
        ]

        manager = OrderManager(
            db=mock_db,
            clob_client=mock_clob_client,
            config=OrderConfig(max_price=Decimal("0.95")),
        )

        initial_balance = manager.get_available_balance()

        # Submit 3 orders
        await manager.submit_order("tok_1", "BUY", Decimal("0.95"), Decimal("10"))
        await manager.submit_order("tok_2", "BUY", Decimal("0.95"), Decimal("10"))
        await manager.submit_order("tok_3", "BUY", Decimal("0.95"), Decimal("10"))

        # Should have reservations
        assert manager.get_available_balance() < initial_balance

        # Cancel all
        for order_id in list(manager._orders.keys()):
            await manager.cancel_order(order_id)

        # All reservations should be released
        assert manager.get_available_balance() == initial_balance
        assert len(manager._balance_manager.get_active_reservations()) == 0
