"""
Execution layer test fixtures.

The execution layer interacts with the Polymarket CLOB API.
All API calls MUST be mocked in tests - never hit real APIs.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from polymarket_bot.execution import (
    BalanceManager,
    BalanceConfig,
    OrderManager,
    OrderConfig,
    Order,
    OrderStatus,
    PositionTracker,
    Position,
    ExitManager,
    ExitConfig,
)


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value="UPDATE 1")
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)
    return db


# =============================================================================
# Mock CLOB Client Fixtures
# =============================================================================


@pytest.fixture
def mock_clob_client():
    """Mock py-clob-client for order submission."""
    # Use spec to limit attributes and avoid hasattr issues
    # Only define the methods we actually use
    class CLOBClientSpec:
        def create_and_post_order(self, order_args):
            pass

        def get_balance_allowance(self, params):
            pass

        def get_order(self, order_id):
            pass

        def cancel(self, order_id):
            pass

        def cancel_order(self, order_id):
            pass

    client = MagicMock(spec=CLOBClientSpec)

    # Mock successful order creation
    client.create_and_post_order.return_value = {
        "orderID": "order_123",
        "status": "LIVE",
    }

    # Mock balance check - returns balance in micro-units (6 decimals)
    # 1000 USDC = 1000000000 micro-units
    client.get_balance_allowance.return_value = {
        "balance": "1000000000",  # 1000 USDC in micro-units
    }

    # Mock order status
    client.get_order.return_value = {
        "orderID": "order_123",
        "status": "MATCHED",
        "filledSize": "20",
        "size": "20",
        "avgPrice": "0.95",
    }

    # Mock cancel
    client.cancel.return_value = {"success": True}
    client.cancel_order.return_value = {"success": True}

    return client


@pytest.fixture
def mock_clob_insufficient_balance():
    """Mock CLOB client with insufficient balance."""
    client = MagicMock()
    client.get_balance_allowance.return_value = {"balance": "5000000"}  # 5 USDC
    client.create_and_post_order.side_effect = Exception("Insufficient balance")
    return client


@pytest.fixture
def mock_clob_partial_fill():
    """Mock CLOB client with partial fill."""
    client = MagicMock()
    client.get_balance_allowance.return_value = {"balance": "1000000000"}  # 1000 USDC
    client.create_and_post_order.return_value = {"orderID": "order_partial", "status": "LIVE"}
    client.get_order.return_value = {
        "orderID": "order_partial",
        "status": "LIVE",
        "filledSize": "10",
        "size": "20",
    }
    return client


# =============================================================================
# Order Fixtures
# =============================================================================


@pytest.fixture
def sample_order():
    """Standard buy order."""
    return Order(
        order_id="order_123",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        side="BUY",
        price=Decimal("0.95"),
        size=Decimal("20"),
        status=OrderStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def filled_order():
    """Fully filled order."""
    return Order(
        order_id="order_456",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        side="BUY",
        price=Decimal("0.95"),
        size=Decimal("20"),
        filled_size=Decimal("20"),
        avg_fill_price=Decimal("0.95"),
        status=OrderStatus.FILLED,
        created_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Position Fixtures
# =============================================================================


@pytest.fixture
def sample_position():
    """Standard position with known age."""
    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(days=3)
    return Position(
        position_id="pos_123",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_cost=Decimal("19.00"),
        entry_time=entry_time,
        hold_start_at=entry_time,
        age_source="bot_created",  # Known age for exit logic
    )


@pytest.fixture
def long_held_position():
    """Position held > 7 days (exit strategy applies)."""
    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(days=10)
    return Position(
        position_id="pos_old",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_cost=Decimal("19.00"),
        entry_time=entry_time,
        hold_start_at=entry_time,
        age_source="bot_created",  # Known age for exit logic
    )


@pytest.fixture
def short_held_position():
    """Position held < 7 days (hold to resolution)."""
    now = datetime.now(timezone.utc)
    entry_time = now - timedelta(days=2)
    return Position(
        position_id="pos_new",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_cost=Decimal("19.00"),
        entry_time=entry_time,
        hold_start_at=entry_time,
        age_source="bot_created",  # Known age for exit logic
    )


# =============================================================================
# Manager Fixtures
# =============================================================================


@pytest.fixture
def balance_manager(mock_db, mock_clob_client):
    """BalanceManager for tests."""
    return BalanceManager(
        db=mock_db,
        clob_client=mock_clob_client,
        config=BalanceConfig(min_reserve=Decimal("100")),
    )


@pytest.fixture
def order_manager(mock_db, mock_clob_client):
    """OrderManager with mocked CLOB client."""
    config = OrderConfig(
        max_price=Decimal("0.95"),
        position_size=Decimal("20"),
    )
    return OrderManager(db=mock_db, clob_client=mock_clob_client, config=config)


@pytest.fixture
def position_tracker(mock_db):
    """PositionTracker for tests."""
    return PositionTracker(db=mock_db)


@pytest.fixture
def exit_manager(mock_db, mock_clob_client, position_tracker, balance_manager):
    """ExitManager with mocked CLOB client."""
    manager = ExitManager(
        db=mock_db,
        clob_client=mock_clob_client,
        position_tracker=position_tracker,
        balance_manager=balance_manager,
        profit_target=Decimal("0.99"),
        stop_loss=Decimal("0.90"),
        min_hold_days=7,
    )
    # Mock refresh_balance for test assertions
    manager._balance_manager.refresh_balance = MagicMock()
    return manager
