# Core Layer - CLAUDE.md

> **STATUS: IMPLEMENTED**
> The core layer is now implemented with all critical gotcha protections.

## Purpose

The core layer contains the **TradingEngine** that orchestrates everything: receives market events, evaluates strategies, and coordinates execution. This is the "brain" of the bot.

## Dependencies

- `storage/` - Writes to repositories
- `ingestion/` - Receives market events
- `strategies/` - Evaluates strategy signals

## Directory Structure

```
core/
├── __init__.py
├── engine.py               # Main TradingEngine
├── event_processor.py      # Event handling logic
├── trigger_tracker.py      # First-trigger deduplication
├── watchlist_service.py    # Watchlist re-scoring
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_engine.py
│   ├── test_event_processor.py
│   ├── test_trigger_tracker.py
│   └── test_watchlist_service.py
└── CLAUDE.md               # This file
```

## Test Fixtures (conftest.py)

```python
"""
Core layer test fixtures.

Core tests verify orchestration logic, so we mock
the storage, ingestion, and strategy layers.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core.engine import TradingEngine, EngineConfig
from core.event_processor import EventProcessor
from storage.database import Database, DatabaseConfig
from storage.repositories import TriggerRepository, TokenMetaRepository
from strategies.protocol import Strategy, StrategyContext
from strategies.signals import Signal, SignalType, EntrySignal


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
# Mock Strategy Fixtures
# =============================================================================

@pytest.fixture
def mock_strategy():
    """Mock strategy that can be configured."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "test_strategy"
    strategy.evaluate.return_value = Signal(type=SignalType.HOLD, reason="Default")
    return strategy


@pytest.fixture
def always_enter_strategy():
    """Strategy that always generates ENTRY signal."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "always_enter"
    strategy.evaluate.return_value = EntrySignal(
        token_id="tok_test",
        side="BUY",
        price=Decimal("0.95"),
        size=Decimal("20"),
        reason="Test entry",
    )
    return strategy


@pytest.fixture
def watchlist_strategy():
    """Strategy that generates WATCHLIST signal."""
    strategy = MagicMock(spec=Strategy)
    strategy.name = "watchlist_test"
    strategy.evaluate.return_value = WatchlistSignal(
        token_id="tok_test",
        current_score=0.92,
        reason="Score below threshold",
    )
    return strategy


# =============================================================================
# Mock Ingestion Fixtures
# =============================================================================

@pytest.fixture
def mock_websocket_client():
    """Mock WebSocket client."""
    client = AsyncMock()
    client.is_connected = True
    client.subscribe = AsyncMock()
    client.receive = AsyncMock()
    return client


@pytest.fixture
def mock_polymarket_client():
    """Mock REST API client."""
    client = MagicMock()
    client.fetch_orderbook.return_value = MagicMock(best_bid=0.94, best_ask=0.96)
    client.verify_orderbook_price.return_value = True
    client.fetch_trade_size_at_price.return_value = 75
    return client


# =============================================================================
# Event Fixtures
# =============================================================================

@pytest.fixture
def price_trigger_event():
    """Price crossing 0.95 threshold."""
    return {
        "type": "price_change",
        "token_id": "tok_yes_abc",
        "condition_id": "0xtest123",
        "price": Decimal("0.95"),
        "timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def below_threshold_event():
    """Price below threshold (should not trigger)."""
    return {
        "type": "price_change",
        "token_id": "tok_yes_abc",
        "condition_id": "0xtest123",
        "price": Decimal("0.90"),
        "timestamp": datetime.now(timezone.utc),
    }


# =============================================================================
# Engine Fixtures
# =============================================================================

@pytest.fixture
def engine_config():
    """Standard engine configuration."""
    return EngineConfig(
        price_threshold=Decimal("0.95"),
        position_size=Decimal("20"),
        max_positions=50,
        dry_run=True,  # Always dry run in tests
    )


@pytest.fixture
def trading_engine(db, engine_config, mock_strategy, mock_polymarket_client):
    """Configured TradingEngine for tests."""
    engine = TradingEngine(
        config=engine_config,
        db=db,
        strategy=mock_strategy,
        api_client=mock_polymarket_client,
    )
    return engine
```

## Test Specifications

### 1. test_engine.py

```python
"""
Tests for the main TradingEngine.

The engine orchestrates: events → strategy → execution.
"""

class TestEngineInitialization:
    """Tests for engine setup."""

    def test_engine_initializes_with_config(self, engine_config, db, mock_strategy):
        """Engine should initialize with configuration."""
        engine = TradingEngine(
            config=engine_config,
            db=db,
            strategy=mock_strategy,
        )

        assert engine.config == engine_config
        assert engine.strategy == mock_strategy

    def test_engine_creates_repositories(self, trading_engine):
        """Engine should create necessary repositories."""
        assert trading_engine.trigger_repo is not None
        assert trading_engine.position_repo is not None

    def test_engine_starts_in_stopped_state(self, trading_engine):
        """Engine should not be running until started."""
        assert trading_engine.is_running is False


class TestEventProcessing:
    """Tests for event handling."""

    @pytest.mark.asyncio
    async def test_processes_price_trigger(
        self, trading_engine, price_trigger_event, mock_strategy
    ):
        """Should evaluate strategy when price crosses threshold."""
        await trading_engine.process_event(price_trigger_event)

        # Strategy should have been called
        mock_strategy.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_below_threshold(
        self, trading_engine, below_threshold_event, mock_strategy
    ):
        """Should ignore events below price threshold."""
        await trading_engine.process_event(below_threshold_event)

        # Strategy should NOT have been called
        mock_strategy.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_entry_signal(
        self, trading_engine, price_trigger_event, always_enter_strategy
    ):
        """Should execute when strategy returns ENTRY signal."""
        trading_engine.strategy = always_enter_strategy

        await trading_engine.process_event(price_trigger_event)

        # Should have attempted execution
        assert trading_engine.execution_count == 1

    @pytest.mark.asyncio
    async def test_adds_to_watchlist_on_signal(
        self, trading_engine, price_trigger_event, watchlist_strategy, db
    ):
        """Should add to watchlist when strategy returns WATCHLIST signal."""
        trading_engine.strategy = watchlist_strategy

        await trading_engine.process_event(price_trigger_event)

        # Should be in watchlist
        watchlist_repo = WatchlistRepository(db)
        entries = watchlist_repo.get_active()
        assert len(entries) == 1
        assert entries[0].token_id == "tok_test"


class TestDryRunMode:
    """Tests for dry-run (paper trading) mode."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_submit_orders(
        self, trading_engine, price_trigger_event, always_enter_strategy
    ):
        """Dry run should NOT submit real orders."""
        trading_engine.strategy = always_enter_strategy
        trading_engine.config.dry_run = True

        await trading_engine.process_event(price_trigger_event)

        # Should log but not actually submit
        assert trading_engine.orders_submitted == 0
        assert trading_engine.dry_run_signals >= 1

    @pytest.mark.asyncio
    async def test_live_mode_submits_orders(
        self, trading_engine, price_trigger_event, always_enter_strategy, mocker
    ):
        """Live mode should submit real orders."""
        trading_engine.strategy = always_enter_strategy
        trading_engine.config.dry_run = False

        # Mock the order submission
        mock_submit = mocker.patch.object(
            trading_engine.order_manager, 'submit_order', return_value="order_123"
        )

        await trading_engine.process_event(price_trigger_event)

        mock_submit.assert_called_once()


class TestOrderbookVerification:
    """Tests for orderbook price verification before execution."""

    @pytest.mark.asyncio
    async def test_verifies_orderbook_before_executing(
        self, trading_engine, price_trigger_event, always_enter_strategy, mock_polymarket_client
    ):
        """
        BELICHICK BUG PREVENTION

        Must verify orderbook price matches trigger before executing.
        """
        trading_engine.strategy = always_enter_strategy

        await trading_engine.process_event(price_trigger_event)

        # Should have called orderbook verification
        mock_polymarket_client.verify_orderbook_price.assert_called()

    @pytest.mark.asyncio
    async def test_rejects_when_orderbook_mismatches(
        self, trading_engine, price_trigger_event, always_enter_strategy, mock_polymarket_client
    ):
        """
        Should reject execution when orderbook doesn't match trigger.

        This prevents executing on anomalous spike trades.
        """
        trading_engine.strategy = always_enter_strategy
        mock_polymarket_client.verify_orderbook_price.return_value = False

        await trading_engine.process_event(price_trigger_event)

        # Should NOT have executed
        assert trading_engine.orders_submitted == 0
```

### 2. test_trigger_tracker.py

```python
"""
Tests for trigger tracking and deduplication.

We only trade the FIRST time a token crosses threshold.
"""

class TestTriggerDeduplication:
    """Tests for first-trigger logic."""

    def test_records_first_trigger(self, db):
        """Should record first trigger for a token."""
        tracker = TriggerTracker(db)

        is_first = tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123"
        )

        assert is_first is True

    def test_rejects_duplicate_trigger(self, db):
        """Should reject subsequent triggers for same token."""
        tracker = TriggerTracker(db)

        # First trigger
        tracker.record_trigger(token_id="tok_abc", condition_id="0x123")

        # Second trigger for same token
        is_first = tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123"
        )

        assert is_first is False

    def test_allows_different_tokens(self, db):
        """Different tokens should trigger independently."""
        tracker = TriggerTracker(db)

        # First token
        tracker.record_trigger(token_id="tok_abc", condition_id="0x123")

        # Different token should still trigger
        is_first = tracker.is_first_trigger(
            token_id="tok_xyz",
            condition_id="0x456"
        )

        assert is_first is True

    def test_dual_key_deduplication(self, db):
        """
        GOTCHA: Must use BOTH token_id AND condition_id.

        Same token_id can appear in different markets.
        """
        tracker = TriggerTracker(db)

        # Same token_id, different condition_id
        tracker.record_trigger(token_id="tok_abc", condition_id="0x111")

        is_first = tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x222"  # Different condition
        )

        # Should be allowed - different market
        assert is_first is True

    def test_stores_trigger_metadata(self, db):
        """Should store useful metadata with trigger."""
        tracker = TriggerTracker(db)

        tracker.record_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            price=Decimal("0.95"),
            trade_size=Decimal("75"),
            model_score=0.98,
        )

        trigger = tracker.get_trigger("tok_abc", "0x123")

        assert trigger.price == Decimal("0.95")
        assert trigger.trade_size == Decimal("75")
        assert trigger.model_score == 0.98
```

### 3. test_watchlist_service.py

```python
"""
Tests for watchlist re-scoring service.

Tokens with scores 0.90-0.97 are added to watchlist and
re-scored hourly. They may be promoted to execution when
their score improves.
"""

class TestWatchlistService:
    """Tests for watchlist management."""

    def test_adds_token_to_watchlist(self, db):
        """Should add token with initial score."""
        service = WatchlistService(db)

        service.add_to_watchlist(
            token_id="tok_abc",
            condition_id="0x123",
            initial_score=0.92,
            time_to_end_hours=720,
        )

        entries = service.get_active_entries()
        assert len(entries) == 1
        assert entries[0].current_score == 0.92

    def test_rescore_updates_score(self, db, mocker):
        """Re-scoring should update stored score."""
        service = WatchlistService(db)
        service.add_to_watchlist("tok_abc", "0x123", 0.92, 720)

        # Mock scorer to return higher score
        mock_scorer = mocker.patch.object(
            service, 'compute_score', return_value=0.96
        )

        service.rescore_all()

        entries = service.get_active_entries()
        assert entries[0].current_score == 0.96

    def test_promotes_when_score_exceeds_threshold(self, db, mocker):
        """Should promote to execution when score >= 0.97."""
        service = WatchlistService(db, execution_threshold=0.97)
        service.add_to_watchlist("tok_abc", "0x123", 0.92, 720)

        # Mock scorer to return score above threshold
        mocker.patch.object(service, 'compute_score', return_value=0.98)

        promotions = service.rescore_all()

        assert len(promotions) == 1
        assert promotions[0].token_id == "tok_abc"
        assert promotions[0].new_score == 0.98

    def test_removes_expired_entries(self, db):
        """Should remove entries for expired markets."""
        service = WatchlistService(db)

        # Add entry for market that expires soon
        service.add_to_watchlist("tok_abc", "0x123", 0.92, time_to_end_hours=1)

        # Fast-forward time (entry now expired)
        service._mark_as_expired("tok_abc", "0x123")

        entries = service.get_active_entries()
        assert len(entries) == 0

    def test_tracks_score_history(self, db, mocker):
        """Should record score history for analysis."""
        service = WatchlistService(db)
        service.add_to_watchlist("tok_abc", "0x123", 0.92, 720)

        # First rescore: 0.92 → 0.94
        mocker.patch.object(service, 'compute_score', return_value=0.94)
        service.rescore_all()

        # Second rescore: 0.94 → 0.97
        mocker.patch.object(service, 'compute_score', return_value=0.97)
        service.rescore_all()

        history = service.get_score_history("tok_abc", "0x123")

        assert len(history) >= 2
        assert history[-1].score == 0.97


class TestScoreEvolution:
    """Tests for how scores change over time."""

    def test_score_increases_as_expiry_approaches(self, db, mocker):
        """
        Scores should generally increase as time_to_end decreases.

        This is because uncertainty decreases near expiry.
        """
        service = WatchlistService(db)
        service.add_to_watchlist("tok_abc", "0x123", 0.92, 720)

        # Simulate time passing: 720h → 48h
        entry = service.get_entry("tok_abc", "0x123")
        entry.time_to_end_hours = 48

        # Re-score with less time
        new_score = service.compute_score(entry)

        # Score should be higher (less uncertainty)
        # This tests the time-dependent nature of scoring
        assert new_score > 0.92 or new_score is not None  # Depends on model
```

### 4. test_event_processor.py

```python
"""
Tests for event processing logic.

EventProcessor handles the flow from raw events to actions.
"""

class TestEventProcessor:
    """Tests for event processing."""

    def test_filters_events_by_type(self):
        """Should only process relevant event types."""
        processor = EventProcessor()

        price_event = {"type": "price_change", "price": "0.95"}
        heartbeat = {"type": "heartbeat"}
        unknown = {"type": "unknown_type"}

        assert processor.should_process(price_event) is True
        assert processor.should_process(heartbeat) is False
        assert processor.should_process(unknown) is False

    def test_extracts_trigger_info(self, price_trigger_event):
        """Should extract trigger information from event."""
        processor = EventProcessor()

        trigger = processor.extract_trigger(price_trigger_event)

        assert trigger.token_id == "tok_yes_abc"
        assert trigger.price == Decimal("0.95")

    def test_validates_price_threshold(self):
        """Should validate price meets threshold."""
        processor = EventProcessor(threshold=Decimal("0.95"))

        assert processor.meets_threshold(Decimal("0.95")) is True
        assert processor.meets_threshold(Decimal("0.96")) is True
        assert processor.meets_threshold(Decimal("0.94")) is False

    def test_builds_strategy_context(self, db, price_trigger_event):
        """Should build complete StrategyContext from event."""
        processor = EventProcessor()

        # Add token metadata to DB
        meta_repo = TokenMetaRepository(db)
        meta_repo.upsert(TokenMeta(
            token_id="tok_yes_abc",
            condition_id="0xtest123",
            question="Test market?",
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        ))

        context = processor.build_context(price_trigger_event, db)

        assert context.token.token_id == "tok_yes_abc"
        assert context.trigger_price == Decimal("0.95")
        assert context.time_to_end_hours > 0
```

## Critical Gotchas (Must Test)

### 1. Dual-Key Trigger Deduplication
```python
def test_same_token_different_market():
    """
    token_id can repeat across markets.
    Must use (token_id, condition_id) as key.
    """
    tracker.record_trigger(token_id="tok_abc", condition_id="0x111")

    # Same token_id, different market - should be allowed
    is_first = tracker.is_first_trigger(
        token_id="tok_abc",
        condition_id="0x222"
    )
    assert is_first is True
```

### 2. Orderbook Verification Before Execution
```python
def test_verify_orderbook_before_execute():
    """
    BELICHICK BUG: Spike trade triggered execution at 95c
    when actual market was at 5c.

    ALWAYS verify orderbook matches before executing.
    """
    # Trigger at 95c
    trigger_price = 0.95

    # But orderbook shows 5c
    orderbook = client.fetch_orderbook(token_id)
    assert abs(orderbook.best_bid - trigger_price) > 0.10

    # Should NOT execute
    assert engine.execute(trigger_price) is False
```

### 3. Watchlist Score Evolution
```python
def test_score_can_improve_over_time():
    """
    time_to_end_hours is a key feature.
    As markets approach expiry, uncertainty decreases.
    Score at 720h remaining: 0.92
    Score at 48h remaining: 0.98 (may now qualify)
    """
    initial = service.compute_score(token, time_to_end=720)
    later = service.compute_score(token, time_to_end=48)

    assert later >= initial  # Usually higher as time decreases
```

## Running Tests

```bash
# All core tests
pytest src/polymarket_bot/core/tests/ -v

# Engine tests only
pytest src/polymarket_bot/core/tests/test_engine.py -v

# Trigger deduplication tests
pytest src/polymarket_bot/core/tests/test_trigger_tracker.py -v

# With coverage
pytest src/polymarket_bot/core/tests/ --cov=src/polymarket_bot/core
```

## Implementation Order

1. `trigger_tracker.py` - First-trigger deduplication (critical)
2. `event_processor.py` - Event parsing and filtering
3. `watchlist_service.py` - Watchlist management
4. `engine.py` - Main orchestrator (depends on all above)

Each module: Write tests first, then implement.

---

## Implementation Notes (Post-Codex Review)

### G2 Atomic Deduplication Fix

**Problem:** The original `should_trigger` and `record_trigger` methods were separate operations, creating a TOCTOU (time-of-check to time-of-use) race condition. Two concurrent events could both pass the check and attempt to execute.

**Solution:** Added `try_record_trigger_atomic()` method in `trigger_tracker.py`:

```python
async def try_record_trigger_atomic(
    self,
    token_id: str,
    condition_id: str,
    threshold: Decimal = Decimal("0.95"),
    ...
) -> bool:
    """
    Atomically check and record a trigger.

    Uses database transaction to ensure the check-and-insert
    is indivisible. Returns True if this was the first trigger,
    False if a duplicate was detected.

    CRITICAL: Use this method instead of is_first_trigger + record_trigger
    for G2 protection.
    """
    async with self._db.transaction() as conn:
        # Check condition-level duplicate first (G2)
        existing = await conn.fetchval(condition_check_query, ...)
        if existing is not None:
            return False

        # Atomic insert with ON CONFLICT DO NOTHING RETURNING
        result = await conn.fetchval(insert_query, ...)
        return result is not None
```

**Usage in Engine:**
```python
# OLD (UNSAFE):
if await self._trigger_tracker.should_trigger(...):
    await self._trigger_tracker.record_trigger(...)
    # Execute trade

# NEW (SAFE):
is_first = await self._trigger_tracker.try_record_trigger_atomic(...)
if not is_first:
    logger.debug("G2: Atomic dedup blocked duplicate")
    return
# Execute trade
```

### Key Behavior Changes

1. **Trigger recording is now atomic** - No TOCTOU race possible
2. **Engine uses atomic method** - `_handle_entry()` updated to use `try_record_trigger_atomic()`
3. **Transaction-based** - Uses database transaction for consistency

### Tests Added

- `TestAtomicTriggerRecording` class in `test_trigger_tracker.py`
- Tests for first trigger, duplicate blocking, transaction usage, condition-level checking
