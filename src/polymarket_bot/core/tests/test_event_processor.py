"""
Tests for event processing logic.

EventProcessor handles the flow from raw events to StrategyContext.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from polymarket_bot.core import EventProcessor, TriggerData


class TestEventFiltering:
    """Tests for event type filtering."""

    def test_processes_price_change_events(self):
        """Should process price_change events."""
        processor = EventProcessor()
        event = {"type": "price_change", "price": "0.95"}
        assert processor.should_process(event) is True

    def test_processes_trade_events(self):
        """Should process trade events."""
        processor = EventProcessor()
        event = {"type": "trade", "price": "0.95"}
        assert processor.should_process(event) is True

    def test_processes_price_update_events(self):
        """Should process price_update events."""
        processor = EventProcessor()
        event = {"type": "price_update", "price": "0.95"}
        assert processor.should_process(event) is True

    def test_ignores_heartbeat_events(self):
        """Should ignore heartbeat events."""
        processor = EventProcessor()
        event = {"type": "heartbeat"}
        assert processor.should_process(event) is False

    def test_ignores_unknown_event_types(self):
        """Should ignore unknown event types."""
        processor = EventProcessor()
        event = {"type": "unknown_type"}
        assert processor.should_process(event) is False

    def test_handles_event_type_key_variants(self):
        """Should handle both 'type' and 'event_type' keys."""
        processor = EventProcessor()

        event1 = {"type": "price_change"}
        event2 = {"event_type": "price_change"}

        assert processor.should_process(event1) is True
        assert processor.should_process(event2) is True


class TestTriggerExtraction:
    """Tests for extracting trigger info from events."""

    def test_extracts_basic_trigger_info(self, price_trigger_event):
        """Should extract token_id, condition_id, and price."""
        processor = EventProcessor()
        trigger = processor.extract_trigger(price_trigger_event)

        assert trigger is not None
        assert trigger.token_id == "tok_yes_abc"
        assert trigger.condition_id == "0xtest123"
        assert trigger.price == Decimal("0.95")

    def test_extracts_size_when_present(self):
        """Should extract trade size when available."""
        processor = EventProcessor()
        event = {
            "type": "trade",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "size": "75",
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        trigger = processor.extract_trigger(event)

        assert trigger.size == Decimal("75")

    def test_handles_missing_size(self):
        """Should handle events without size (G3 - WebSocket)."""
        processor = EventProcessor()
        event = {
            "type": "price_change",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }
        trigger = processor.extract_trigger(event)

        assert trigger.size is None

    def test_calculates_trade_age(self):
        """Should calculate age of trade in seconds."""
        processor = EventProcessor()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        event = {
            "type": "trade",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "timestamp": old_time.timestamp(),
        }
        trigger = processor.extract_trigger(event)

        # Should be approximately 120 seconds old
        assert 115 <= trigger.trade_age_seconds <= 125

    def test_handles_millisecond_timestamps(self):
        """Should correctly handle millisecond timestamps."""
        processor = EventProcessor()
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        event = {
            "type": "trade",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "timestamp": now_ms,
        }
        trigger = processor.extract_trigger(event)

        # Should be recent (< 5 seconds)
        assert trigger.trade_age_seconds < 5

    def test_handles_datetime_timestamp(self):
        """Should handle datetime objects as timestamps."""
        processor = EventProcessor()
        event = {
            "type": "trade",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "timestamp": datetime.now(timezone.utc),
        }
        trigger = processor.extract_trigger(event)

        assert trigger.trade_age_seconds < 5

    def test_returns_none_for_event_without_timestamp(self):
        """
        G1 Protection: Should return None for events without valid timestamp.

        This prevents the Belichick bug where stale trades appear fresh
        by defaulting to now().
        """
        processor = EventProcessor()

        # Missing timestamp - G1 requires rejection
        event = {"type": "trade", "token_id": "tok_123", "price": "0.95"}
        trigger = processor.extract_trigger(event)

        # G1: Should return None for missing timestamp
        assert trigger is None

    def test_parses_event_with_valid_timestamp(self):
        """Should parse events with valid timestamps."""
        processor = EventProcessor()

        event = {
            "type": "trade",
            "token_id": "tok_123",
            "price": "0.95",
            "timestamp": 1704067200,  # Valid Unix timestamp
        }
        trigger = processor.extract_trigger(event)

        assert trigger is not None
        assert trigger.token_id == "tok_123"


class TestPriceThreshold:
    """Tests for price threshold validation."""

    def test_meets_threshold_at_exact_value(self):
        """Should pass when price equals threshold."""
        processor = EventProcessor(threshold=Decimal("0.95"))
        assert processor.meets_threshold(Decimal("0.95")) is True

    def test_meets_threshold_above_value(self):
        """Should pass when price exceeds threshold."""
        processor = EventProcessor(threshold=Decimal("0.95"))
        assert processor.meets_threshold(Decimal("0.96")) is True
        assert processor.meets_threshold(Decimal("0.99")) is True

    def test_fails_threshold_below_value(self):
        """Should fail when price is below threshold."""
        processor = EventProcessor(threshold=Decimal("0.95"))
        assert processor.meets_threshold(Decimal("0.94")) is False
        assert processor.meets_threshold(Decimal("0.50")) is False

    def test_threshold_boundary_precision(self):
        """Should handle precise boundary cases."""
        processor = EventProcessor(threshold=Decimal("0.95"))

        # Just below
        assert processor.meets_threshold(Decimal("0.9499")) is False

        # Exactly at
        assert processor.meets_threshold(Decimal("0.9500")) is True

        # Just above
        assert processor.meets_threshold(Decimal("0.9501")) is True


class TestContextBuilding:
    """Tests for building StrategyContext."""

    @pytest.mark.asyncio
    async def test_builds_context_from_event(self, mock_db, price_trigger_event):
        """Should build StrategyContext with all required fields."""
        processor = EventProcessor()

        # Mock token metadata
        mock_db.fetchrow.return_value = {
            "question": "Test question?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }

        trigger = processor.extract_trigger(price_trigger_event)
        context = await processor.build_context(price_trigger_event, mock_db, trigger)

        assert context is not None
        assert context.token_id == "tok_yes_abc"
        assert context.condition_id == "0xtest123"
        assert context.trigger_price == Decimal("0.95")

    @pytest.mark.asyncio
    async def test_context_includes_question(self, mock_db, price_trigger_event):
        """Should include market question in context."""
        processor = EventProcessor()

        mock_db.fetchrow.return_value = {
            "question": "Will BTC hit $100k?",
            "outcome": "Yes",
            "outcome_index": 0,
            "market_id": "market_123",
        }

        trigger = processor.extract_trigger(price_trigger_event)
        context = await processor.build_context(price_trigger_event, mock_db, trigger)

        assert context.question == "Will BTC hit $100k?"

    @pytest.mark.asyncio
    async def test_context_includes_time_to_end(self, mock_db):
        """Should calculate time to end in hours."""
        processor = EventProcessor()

        end_date = datetime.now(timezone.utc) + timedelta(days=30)
        event = {
            "type": "trade",
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "price": "0.95",
            "end_date": end_date.isoformat(),
            "timestamp": datetime.now(timezone.utc).timestamp(),
        }

        mock_db.fetchrow.return_value = None

        trigger = processor.extract_trigger(event)
        context = await processor.build_context(event, mock_db, trigger)

        # Should be approximately 720 hours (30 days)
        assert 700 < context.time_to_end_hours < 740

    @pytest.mark.asyncio
    async def test_context_handles_missing_metadata(self, mock_db, price_trigger_event):
        """Should handle cases where token metadata is not in DB."""
        processor = EventProcessor()

        mock_db.fetchrow.return_value = None

        trigger = processor.extract_trigger(price_trigger_event)
        context = await processor.build_context(price_trigger_event, mock_db, trigger)

        assert context is not None
        # Should use defaults or event data
        assert context.question == ""  # Default when not found


class TestHardFilters:
    """Tests for hard filter application."""

    def test_rejects_weather_markets(self, base_context):
        """Should reject weather markets (G6)."""
        processor = EventProcessor()
        base_context.question = "Will it rain in NYC tomorrow?"

        should_reject, reason = processor.apply_filters(base_context)

        assert should_reject is True
        assert "weather" in reason.lower()

    def test_allows_rainbow_six(self, base_context):
        """
        REGRESSION TEST: Rainbow Six should NOT be blocked.

        G6 fix: Use word boundaries, not substring match.
        """
        processor = EventProcessor()
        base_context.question = "Will Team A win Rainbow Six Siege tournament?"
        base_context.category = "Esports"

        should_reject, reason = processor.apply_filters(base_context)

        assert should_reject is False

    def test_rejects_expiring_markets(self, base_context):
        """Should reject markets expiring in < 6 hours."""
        processor = EventProcessor()
        base_context.time_to_end_hours = 5

        should_reject, reason = processor.apply_filters(base_context)

        assert should_reject is True
        assert "time" in reason.lower() or "expir" in reason.lower()

    def test_allows_markets_with_time(self, base_context):
        """Should allow markets with sufficient time remaining."""
        processor = EventProcessor()
        base_context.time_to_end_hours = 720  # 30 days

        should_reject, reason = processor.apply_filters(base_context)

        assert should_reject is False
