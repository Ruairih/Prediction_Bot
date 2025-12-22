# Execution Layer - CLAUDE.md

> **STATUS: IMPLEMENTED**
> The execution layer is now implemented with critical G4 protections and safety fixes.

## Purpose

The execution layer handles **order management**: submitting orders to Polymarket CLOB, tracking positions, and managing exits. This layer interacts with real money, so correctness is paramount.

## Dependencies

- `storage/` - Writes orders and positions to DB
- `core/` - Receives execution requests from engine
- `py-clob-client` - Polymarket CLOB SDK

### Installing py-clob-client

```bash
pip install py-clob-client
```

Or from source:
```bash
pip install git+https://github.com/Polymarket/py-clob-client.git
```

### CLOB Client Setup

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import json

# Load credentials from file
with open("polymarket_api_creds.json") as f:
    creds_data = json.load(f)

# Create client
creds = ApiCreds(
    api_key=creds_data["api_key"],
    api_secret=creds_data["api_secret"],
    api_passphrase=creds_data["api_passphrase"],
)

client = ClobClient(
    host=creds_data["host"],
    chain_id=creds_data["chain_id"],
    key=creds_data["private_key"],
    creds=creds,
    signature_type=creds_data["signature_type"],
    funder=creds_data["funder"],
)
```

### Credential File Format

See `polymarket_api_creds.json.example` in the project root:
```json
{
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "api_passphrase": "your-passphrase",
  "private_key": "0x...",
  "funder": "0x...",
  "signature_type": 2,
  "host": "https://clob.polymarket.com",
  "chain_id": 137
}
```

## Directory Structure

```
execution/
├── __init__.py
├── service.py              # ExecutionService facade (primary interface)
├── order_manager.py        # Order submission and tracking
├── position_tracker.py     # Position management
├── exit_manager.py         # Exit strategy execution
├── balance_manager.py      # USDC balance tracking
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_order_manager.py
│   ├── test_position_tracker.py
│   ├── test_exit_manager.py
│   └── test_balance_manager.py
└── CLAUDE.md               # This file
```

## ExecutionService Facade

The `ExecutionService` is the **primary interface** for the execution layer. Other components (TradingEngine, BackgroundTasksManager) should use this service instead of calling individual managers directly.

### Why a Facade?

1. **Encapsulation**: Hides complexity of coordinating 4 managers
2. **Consistency**: Ensures proper ordering (balance check → order → position → balance refresh)
3. **State Management**: Handles state rehydration on startup
4. **G4 Protection**: Automatically refreshes balance after fills

### Usage

```python
from polymarket_bot.execution import ExecutionService, ExecutionConfig

config = ExecutionConfig(
    max_price=Decimal("0.95"),
    default_position_size=Decimal("20"),
    min_balance_reserve=Decimal("100"),
    profit_target=Decimal("0.99"),
    stop_loss=Decimal("0.90"),
    min_hold_days=7,
)

service = ExecutionService(
    db=database,
    clob_client=clob_client,  # None for dry run
    config=config,
)

# Load state on startup (REQUIRED)
await service.load_state()

# Execute entry
result = await service.execute_entry(signal, context)
if result.success:
    print(f"Order {result.order_id} submitted")

# Execute exit
result = await service.execute_exit(signal, position, current_price)

# Background sync (called by BackgroundTasksManager)
await service.sync_open_orders()
exits = await service.evaluate_exits(current_prices)
```

### State Rehydration

On startup, `load_state()` restores:

1. **Balance**: Refreshes from CLOB API
2. **Open Orders**: Loads from DB, restores balance reservations
3. **Open Positions**: Loads from DB for exit monitoring

```python
# In OrderManager.load_orders()
query = """
    SELECT order_id, token_id, condition_id, side, price, size,
           filled_size, avg_fill_price, status, created_at, updated_at
    FROM orders WHERE status IN ('pending', 'live', 'partial')
"""
# Restores orders to cache AND recreates balance reservations
```

## Test Fixtures (conftest.py)

```python
"""
Execution layer test fixtures.

The execution layer interacts with the Polymarket CLOB API.
All API calls MUST be mocked in tests - never hit real APIs.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from execution.order_manager import OrderManager, OrderConfig
from execution.position_tracker import PositionTracker
from execution.exit_manager import ExitManager
from storage.database import Database, DatabaseConfig
from storage.models import Order, Position, OrderStatus


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
async def db():
    """Fresh database for each test (uses test PostgreSQL)."""
    config = DatabaseConfig(
        url=os.environ.get("TEST_DATABASE_URL", "postgresql://predict:predict@localhost:5433/predict")
    )
    database = Database(config)
    await database.initialize()
    yield database
    await database.close()


# =============================================================================
# Mock CLOB Client Fixtures
# =============================================================================

@pytest.fixture
def mock_clob_client():
    """Mock py-clob-client for order submission."""
    client = MagicMock()

    # Mock successful order creation
    client.create_order.return_value = {
        "orderID": "order_123",
        "status": "LIVE",
    }

    # Mock balance check
    client.get_balance.return_value = {
        "USDC": "1000.00",
    }

    # Mock order status
    client.get_order.return_value = {
        "orderID": "order_123",
        "status": "MATCHED",
        "filledSize": "20",
        "avgPrice": "0.95",
    }

    return client


@pytest.fixture
def mock_clob_insufficient_balance():
    """Mock CLOB client with insufficient balance."""
    client = MagicMock()
    client.get_balance.return_value = {"USDC": "5.00"}  # Only $5
    client.create_order.side_effect = Exception("Insufficient balance")
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
        status=OrderStatus.FILLED,
        created_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Position Fixtures
# =============================================================================

@pytest.fixture
def sample_position():
    """Standard position."""
    return Position(
        position_id="pos_123",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_time=datetime.now(timezone.utc) - timedelta(days=3),
        cost_basis=Decimal("19.00"),  # 20 * 0.95
    )


@pytest.fixture
def long_held_position():
    """Position held > 7 days (exit strategy applies)."""
    return Position(
        position_id="pos_old",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_time=datetime.now(timezone.utc) - timedelta(days=10),
        cost_basis=Decimal("19.00"),
    )


@pytest.fixture
def short_held_position():
    """Position held < 7 days (hold to resolution)."""
    return Position(
        position_id="pos_new",
        token_id="tok_yes_abc",
        condition_id="0xtest123",
        size=Decimal("20"),
        entry_price=Decimal("0.95"),
        entry_time=datetime.now(timezone.utc) - timedelta(days=2),
        cost_basis=Decimal("19.00"),
    )


# =============================================================================
# Manager Fixtures
# =============================================================================

@pytest.fixture
def order_manager(db, mock_clob_client):
    """OrderManager with mocked CLOB client."""
    config = OrderConfig(
        max_price=Decimal("0.95"),
        position_size=Decimal("20"),
    )
    return OrderManager(db=db, clob_client=mock_clob_client, config=config)


@pytest.fixture
def position_tracker(db):
    """PositionTracker for tests."""
    return PositionTracker(db=db)


@pytest.fixture
def exit_manager(db, mock_clob_client):
    """ExitManager with mocked CLOB client."""
    return ExitManager(
        db=db,
        clob_client=mock_clob_client,
        profit_target=Decimal("0.99"),
        stop_loss=Decimal("0.90"),
        min_hold_days=7,
    )
```

## Test Specifications

### 1. test_order_manager.py

```python
"""
Tests for order submission and tracking.

Orders interact with the Polymarket CLOB API.
All API calls must be mocked.
"""

class TestOrderSubmission:
    """Tests for submitting orders."""

    def test_submits_buy_order(self, order_manager, mock_clob_client):
        """Should submit BUY order to CLOB."""
        order_id = order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        assert order_id == "order_123"
        mock_clob_client.create_order.assert_called_once()

    def test_respects_max_price(self, order_manager):
        """Should reject orders above max price."""
        # Config has max_price=0.95
        with pytest.raises(PriceTooHighError):
            order_manager.submit_order(
                token_id="tok_yes_abc",
                side="BUY",
                price=Decimal("0.97"),  # Above max
                size=Decimal("20"),
            )

    def test_stores_order_in_database(self, order_manager, db):
        """Should persist order to database."""
        order_id = order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Check database
        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)

        assert order is not None
        assert order.token_id == "tok_yes_abc"
        assert order.status == OrderStatus.PENDING

    def test_handles_insufficient_balance(
        self, db, mock_clob_insufficient_balance
    ):
        """Should handle insufficient balance gracefully."""
        manager = OrderManager(
            db=db,
            clob_client=mock_clob_insufficient_balance,
            config=OrderConfig(),
        )

        with pytest.raises(InsufficientBalanceError):
            manager.submit_order(
                token_id="tok_yes_abc",
                side="BUY",
                price=Decimal("0.95"),
                size=Decimal("20"),
            )


class TestOrderTracking:
    """Tests for order status tracking."""

    def test_syncs_order_status(self, order_manager, mock_clob_client, db):
        """Should sync order status from CLOB."""
        # Submit order
        order_id = order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        # Sync status
        order_manager.sync_order_status(order_id)

        # Check updated status
        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)

        assert order.status == OrderStatus.FILLED
        assert order.filled_size == Decimal("20")

    def test_detects_partial_fill(self, order_manager, mock_clob_client, db):
        """Should detect partially filled orders."""
        mock_clob_client.get_order.return_value = {
            "orderID": "order_123",
            "status": "LIVE",
            "filledSize": "10",  # Partial fill
            "size": "20",
        }

        order_id = order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        order_manager.sync_order_status(order_id)

        order_repo = OrderRepository(db)
        order = order_repo.get_by_id(order_id)

        assert order.status == OrderStatus.PARTIAL
        assert order.filled_size == Decimal("10")


class TestBalanceCheck:
    """Tests for balance verification."""

    def test_checks_balance_before_order(self, order_manager, mock_clob_client):
        """Should verify sufficient balance before ordering."""
        # This should succeed - mock has $1000
        order_id = order_manager.submit_order(
            token_id="tok_yes_abc",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),  # Costs $19
        )

        assert order_id is not None

    def test_caches_balance_appropriately(self, order_manager, mock_clob_client):
        """
        GOTCHA: Balance cache can become stale.

        Should refresh balance periodically, not cache forever.
        """
        # First call
        balance1 = order_manager.get_available_balance()

        # Update mock balance
        mock_clob_client.get_balance.return_value = {"USDC": "500.00"}

        # Force refresh
        order_manager.refresh_balance()
        balance2 = order_manager.get_available_balance()

        assert balance2 < balance1
```

### 2. test_position_tracker.py

```python
"""
Tests for position tracking.

Positions are created when orders fill and closed when markets resolve.
"""

class TestPositionCreation:
    """Tests for creating positions from fills."""

    def test_creates_position_from_fill(self, position_tracker, db, filled_order):
        """Should create position when order fills."""
        position_tracker.record_fill(filled_order)

        positions = position_tracker.get_open_positions()

        assert len(positions) == 1
        assert positions[0].token_id == "tok_yes_abc"
        assert positions[0].size == Decimal("20")

    def test_aggregates_multiple_fills(self, position_tracker, db):
        """Should aggregate fills for same token."""
        # First fill
        position_tracker.record_fill(Order(
            order_id="order_1",
            token_id="tok_yes_abc",
            condition_id="0x123",
            side="BUY",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.94"),
            status=OrderStatus.FILLED,
        ))

        # Second fill for same token
        position_tracker.record_fill(Order(
            order_id="order_2",
            token_id="tok_yes_abc",
            condition_id="0x123",
            side="BUY",
            size=Decimal("10"),
            filled_size=Decimal("10"),
            price=Decimal("0.96"),
            status=OrderStatus.FILLED,
        ))

        positions = position_tracker.get_open_positions()

        assert len(positions) == 1
        assert positions[0].size == Decimal("20")
        # Average entry price: (10*0.94 + 10*0.96) / 20 = 0.95
        assert positions[0].entry_price == Decimal("0.95")


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


class TestPositionClosure:
    """Tests for closing positions."""

    def test_closes_position_on_resolution(self, position_tracker, db, sample_position):
        """Should close position when market resolves."""
        position_tracker.positions[sample_position.position_id] = sample_position

        position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("1.00"),
            reason="resolution_yes"
        )

        open_positions = position_tracker.get_open_positions()
        assert sample_position.position_id not in [p.position_id for p in open_positions]

    def test_records_exit_event(self, position_tracker, db, sample_position):
        """Should record exit event for audit trail."""
        position_tracker.positions[sample_position.position_id] = sample_position

        position_tracker.close_position(
            sample_position.position_id,
            exit_price=Decimal("0.99"),
            reason="profit_target"
        )

        exit_events = position_tracker.get_exit_events(sample_position.position_id)

        assert len(exit_events) == 1
        assert exit_events[0].exit_price == Decimal("0.99")
        assert exit_events[0].reason == "profit_target"
```

### 3. test_exit_manager.py

```python
"""
Tests for exit strategy management.

Exit strategies:
- Short positions (<7 days): Hold to resolution (high win rate)
- Long positions (>7 days): Apply profit target (99c) and stop-loss (90c)
"""

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


class TestExitExecution:
    """Tests for executing exits."""

    def test_submits_sell_order_on_exit(
        self, exit_manager, long_held_position, mock_clob_client
    ):
        """Should submit SELL order when exit triggered."""
        exit_manager.execute_exit(
            long_held_position,
            current_price=Decimal("0.99"),
            reason="profit_target"
        )

        # Should have submitted sell order
        mock_clob_client.create_order.assert_called()
        call_args = mock_clob_client.create_order.call_args
        assert call_args[1]["side"] == "SELL"

    def test_records_exit_pnl(self, exit_manager, long_held_position, db):
        """Should record realized P&L on exit."""
        exit_manager.execute_exit(
            long_held_position,
            current_price=Decimal("0.99"),
            reason="profit_target"
        )

        # Check exit event
        exit_repo = ExitEventRepository(db)
        events = exit_repo.get_by_position(long_held_position.position_id)

        assert len(events) == 1
        # Entry: 0.95, Exit: 0.99, Size: 20
        # PnL = 20 * (0.99 - 0.95) = $0.80
        assert events[0].realized_pnl == Decimal("0.80")


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
        sample_position.entry_time = datetime.now(timezone.utc) - timedelta(days=days_held)

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
```

### 4. test_balance_manager.py

```python
"""
Tests for USDC balance management.

Balance tracking is critical for knowing when we can trade.
"""

class TestBalanceTracking:
    """Tests for balance queries."""

    def test_fetches_current_balance(self, db, mock_clob_client):
        """Should fetch current USDC balance."""
        manager = BalanceManager(db=db, clob_client=mock_clob_client)

        balance = manager.get_available_balance()

        assert balance == Decimal("1000.00")

    def test_tracks_reserved_balance(self, db, mock_clob_client):
        """Should track balance reserved for pending orders."""
        manager = BalanceManager(db=db, clob_client=mock_clob_client)

        # Reserve for pending order
        manager.reserve(amount=Decimal("19.00"), order_id="order_pending")

        available = manager.get_available_balance()

        # $1000 - $19 reserved = $981
        assert available == Decimal("981.00")

    def test_releases_reservation_on_fill(self, db, mock_clob_client):
        """Should release reservation when order fills."""
        manager = BalanceManager(db=db, clob_client=mock_clob_client)

        manager.reserve(amount=Decimal("19.00"), order_id="order_123")
        manager.release_reservation(order_id="order_123")

        available = manager.get_available_balance()

        assert available == Decimal("1000.00")


class TestBalanceSafety:
    """Tests for balance safety checks."""

    def test_prevents_over_allocation(self, db, mock_clob_client):
        """Should prevent allocating more than available."""
        manager = BalanceManager(db=db, clob_client=mock_clob_client)

        # Try to reserve more than available
        with pytest.raises(InsufficientBalanceError):
            manager.reserve(amount=Decimal("2000.00"), order_id="big_order")

    def test_respects_minimum_reserve(self, db, mock_clob_client):
        """Should maintain minimum reserve balance."""
        manager = BalanceManager(
            db=db,
            clob_client=mock_clob_client,
            min_reserve=Decimal("100.00")  # Keep $100 minimum
        )

        # Available for trading: $1000 - $100 reserve = $900
        available = manager.get_tradeable_balance()

        assert available == Decimal("900.00")
```

## Critical Gotchas (Must Test)

### 1. CLOB Balance Cache Staleness
```python
def test_balance_cache_staleness():
    """
    GOTCHA: Balance cache becomes stale after trades.

    Must refresh balance after order fills.
    """
    # Order fills, balance decreases
    order_manager.submit_order(...)

    # Sync order status
    order_manager.sync_order_status(order_id)

    # MUST refresh balance
    balance_manager.refresh_balance()

    # Now check available
    available = balance_manager.get_available_balance()
```

### 2. Max Price Enforcement
```python
def test_never_buy_above_max_price():
    """
    Max price is 0.95 (now, was 0.97).

    NEVER submit buy orders above this.
    """
    with pytest.raises(PriceTooHighError):
        order_manager.submit_order(
            token_id="tok_abc",
            side="BUY",
            price=Decimal("0.97"),  # Above max
            size=Decimal("20"),
        )
```

### 3. Exit Strategy for Long Positions
```python
def test_exit_strategy_capital_efficiency():
    """
    Long positions (>7 days) tie up capital.

    Apply 99c target + 90c stop to improve turnover.
    Short positions have 99%+ win rate - hold to resolution.
    """
    long_position = Position(
        entry_time=datetime.now() - timedelta(days=10)
    )

    # Should apply conditional exit
    assert exit_manager.get_strategy(long_position) == "conditional_exit"
```

## Running Tests

```bash
# All execution tests
pytest src/polymarket_bot/execution/tests/ -v

# Order manager tests
pytest src/polymarket_bot/execution/tests/test_order_manager.py -v

# Exit strategy tests
pytest src/polymarket_bot/execution/tests/test_exit_manager.py -v

# With coverage
pytest src/polymarket_bot/execution/tests/ --cov=src/polymarket_bot/execution
```

## Implementation Order

1. `balance_manager.py` - Balance tracking (needed for orders)
2. `order_manager.py` - Order submission (depends on balance)
3. `position_tracker.py` - Position tracking (depends on orders)
4. `exit_manager.py` - Exit strategies (depends on positions)

Each module: Write tests first, then implement.

---

## Implementation Notes (Post-Codex Review)

### Partial Fill Reservation Handling Fix

**Problem:** Reservations were not adjusted for partial fills. Unknown CLOB statuses (FAILED/REJECTED/EXPIRED) were not mapped, causing funds to remain locked indefinitely.

**Solution:** Added `adjust_reservation_for_partial_fill()` method in `balance_manager.py`:

```python
def adjust_reservation_for_partial_fill(
    self,
    order_id: str,
    filled_amount: Decimal,
) -> None:
    """
    Adjust reservation after a partial fill.

    FIX: Partial fills should reduce the reserved amount proportionally.
    The filled portion no longer needs to be reserved (it's now a position).
    """
    if order_id not in self._reservations:
        return

    reservation = self._reservations[order_id]
    new_amount = reservation.amount - filled_amount

    if new_amount <= Decimal("0"):
        self.release_reservation(order_id)
    else:
        # Update reservation with remaining amount
        self._reservations[order_id] = Reservation(
            order_id=order_id,
            amount=new_amount,
            created_at=reservation.created_at,
        )
```

### Exit Order Fill Confirmation Fix

**Problem:** `execute_exit` submitted SELL orders and immediately closed positions without confirming order acceptance/fill. This could desync holdings, PnL, and balance.

**Solution:** Added `_wait_for_order_fill()` method in `exit_manager.py`:

```python
async def _wait_for_order_fill(
    self,
    order_id: str,
    timeout_seconds: float = 30.0,
    poll_interval: float = 1.0,
) -> bool:
    """
    Wait for an order to be filled or reach a terminal state.

    Returns:
        True if order filled/confirmed, False if timeout or rejected
    """
    # Polls CLOB for status until MATCHED, LIVE, or terminal
```

**Updated `execute_exit`:**
```python
# FIX: Wait for order acceptance/fill before closing position
if wait_for_fill and order_id:
    order_confirmed = await self._wait_for_order_fill(
        order_id,
        timeout_seconds=fill_timeout_seconds,
    )
    if not order_confirmed:
        logger.warning(f"Exit order not confirmed. Position NOT closed.")
        return False

# Only close position after order confirmed
await self._position_tracker.close_position(...)
```

### Other Fixes

1. **CLOB Status Handling:** `order_manager.py` now handles FAILED, REJECTED, EXPIRED statuses
2. **Side Normalization:** Added `side = side.upper()` to prevent max price bypass
3. **Balance Refresh on Resolution:** `handle_resolution()` now calls `refresh_balance()` (G4)

### Tests Added

- `TestPartialFillHandling` - Tests for balance reservation adjustments
- `TestOrderFillConfirmation` - Tests for exit order confirmation waiting

### State Rehydration Fix

**Problem:** On restart, open orders were lost and balance reservations weren't restored, potentially causing over-allocation.

**Solution:** Added `load_orders()` method in `order_manager.py`:

```python
async def load_orders(self) -> int:
    """Load open orders from database and restore balance reservations."""
    query = """
        SELECT order_id, token_id, condition_id, side, price, size,
               filled_size, avg_fill_price, status, created_at, updated_at
        FROM orders WHERE status IN ('pending', 'live', 'partial')
    """
    # Restores orders to cache AND recreates balance reservations
    for order in orders:
        remaining_size = order.size - order.filled_size
        reservation_amount = remaining_size * order.price
        self._balance_manager.reserve(reservation_amount, order.order_id)
```

**Updated `ExecutionService.load_state()`:**
```python
async def load_state(self) -> None:
    # 1. Refresh balance from CLOB first
    self._balance_manager.refresh_balance()

    # 2. Load open orders and restore reservations
    orders_loaded = await self._order_manager.load_orders()

    # 3. Load open positions
    await self._position_tracker.load_positions()
```

### Partial Fill Position Tracking Fix

**Problem:** Only fully filled orders (FILLED status) created positions. Partial fills were ignored until completely filled.

**Solution:** Updated `PositionTracker.record_fill()` to accept PARTIAL status:

```python
async def record_fill(self, order: Order) -> Optional[Position]:
    # Accept both FILLED and PARTIAL orders
    if order.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
        return None

    # Use filled_size, not total size
    fill_size = order.filled_size
    if fill_size <= Decimal("0"):
        return None
```

**Updated `sync_open_orders()` to detect incremental fills:**
```python
async def sync_open_orders(self) -> int:
    for order in open_orders:
        old_filled = order.filled_size
        updated = await self._order_manager.sync_order_status(order.order_id)

        # Detect new fills
        new_filled = updated.filled_size - old_filled
        if new_filled > Decimal("0"):
            await self._position_tracker.record_fill(updated)
```
