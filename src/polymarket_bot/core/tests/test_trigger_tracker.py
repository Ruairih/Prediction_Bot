"""
Tests for trigger tracking and deduplication.

We only trade the FIRST time a token crosses threshold.
Critical: G2 protection - use (token_id, condition_id) as key.
"""
import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from polymarket_bot.core import TriggerTracker


class TestFirstTriggerDetection:
    """Tests for detecting first triggers."""

    @pytest.mark.asyncio
    async def test_identifies_first_trigger(self, mock_db):
        """Should identify first trigger for a token."""
        mock_db.fetchval.return_value = None  # No existing trigger

        tracker = TriggerTracker(mock_db)

        is_first = await tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        assert is_first is True

    @pytest.mark.asyncio
    async def test_rejects_duplicate_trigger(self, mock_db):
        """Should reject subsequent triggers for same token."""
        # Simulate existing trigger
        mock_db.fetchval.return_value = 1

        tracker = TriggerTracker(mock_db)

        is_first = await tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        assert is_first is False

    @pytest.mark.asyncio
    async def test_queries_with_correct_keys(self, mock_db):
        """Should query using token_id, condition_id, and threshold."""
        mock_db.fetchval.return_value = None

        tracker = TriggerTracker(mock_db)

        await tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        # Verify the query was called with correct parameters
        mock_db.fetchval.assert_called_once()
        call_args = mock_db.fetchval.call_args
        assert "tok_abc" in call_args[0]
        assert "0x123" in call_args[0]


class TestDualKeyDeduplication:
    """Tests for G2: dual-key deduplication."""

    @pytest.mark.asyncio
    async def test_same_token_different_condition_allowed(self, mock_db):
        """
        GOTCHA G2: Same token_id can appear in different markets.

        Should allow trigger if condition_id is different.
        """
        # First call: no existing trigger
        # Second call (for condition check): also no trigger
        mock_db.fetchval.side_effect = [None, None]

        tracker = TriggerTracker(mock_db)

        should_trigger = await tracker.should_trigger(
            token_id="tok_abc",
            condition_id="0x222",  # Different condition
            threshold=Decimal("0.95"),
        )

        assert should_trigger is True

    @pytest.mark.asyncio
    async def test_checks_condition_level_triggers(self, mock_db):
        """Should check if ANY token for this condition has triggered."""
        # Token check: no trigger
        # Condition check: has triggered
        mock_db.fetchval.side_effect = [None, 1]

        tracker = TriggerTracker(mock_db)

        should_trigger = await tracker.should_trigger(
            token_id="tok_xyz",  # Different token
            condition_id="0x123",  # Same condition
            threshold=Decimal("0.95"),
        )

        # Should be blocked because condition already triggered
        assert should_trigger is False

    @pytest.mark.asyncio
    async def test_has_condition_triggered(self, mock_db):
        """Should check if any token for condition has triggered."""
        mock_db.fetchval.return_value = 1  # Has triggered

        tracker = TriggerTracker(mock_db)

        has_triggered = await tracker.has_condition_triggered(
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        assert has_triggered is True


class TestTriggerRecording:
    """Tests for recording triggers."""

    @pytest.mark.asyncio
    async def test_records_trigger(self, mock_db):
        """Should record trigger to database."""
        mock_db.execute.return_value = None

        tracker = TriggerTracker(mock_db)

        await tracker.record_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
            price=Decimal("0.96"),
            trade_size=Decimal("75"),
            model_score=0.98,
        )

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_all_metadata(self, mock_db):
        """Should record all trigger metadata."""
        mock_db.execute.return_value = None

        tracker = TriggerTracker(mock_db)

        await tracker.record_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
            price=Decimal("0.96"),
            trade_size=Decimal("75"),
            model_score=0.98,
            outcome="Yes",
            outcome_index=0,
        )

        # Verify all data was passed
        call_args = mock_db.execute.call_args[0]
        assert "tok_abc" in call_args
        assert "0x123" in call_args

    @pytest.mark.asyncio
    async def test_handles_conflict_gracefully(self, mock_db):
        """Should handle duplicate inserts with ON CONFLICT."""
        mock_db.execute.return_value = None

        tracker = TriggerTracker(mock_db)

        # Recording same trigger twice should not raise
        await tracker.record_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )
        await tracker.record_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        # Should have been called twice without error
        assert mock_db.execute.call_count == 2


class TestTriggerRetrieval:
    """Tests for retrieving trigger information."""

    @pytest.mark.asyncio
    async def test_gets_trigger_info(self, mock_db):
        """Should retrieve trigger information."""
        mock_db.fetchrow.return_value = {
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "threshold": 0.95,
            "price": 0.96,
            "size": 75,
            "model_score": 0.98,
            "created_at": "2024-12-18T12:00:00+00:00",
        }

        tracker = TriggerTracker(mock_db)

        trigger = await tracker.get_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        assert trigger is not None
        assert trigger.token_id == "tok_abc"
        assert trigger.price == Decimal("0.96")

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, mock_db):
        """Should return None if trigger not found."""
        mock_db.fetchrow.return_value = None

        tracker = TriggerTracker(mock_db)

        trigger = await tracker.get_trigger(
            token_id="tok_nonexistent",
            condition_id="0xabc",
            threshold=Decimal("0.95"),
        )

        assert trigger is None

    @pytest.mark.asyncio
    async def test_gets_triggers_for_condition(self, mock_db):
        """Should retrieve all triggers for a condition."""
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_yes",
                "condition_id": "0x123",
                "threshold": 0.95,
                "price": 0.96,
                "size": 75,
                "model_score": 0.98,
                "created_at": "2024-12-18T12:00:00+00:00",
            },
            {
                "token_id": "tok_no",
                "condition_id": "0x123",
                "threshold": 0.95,
                "price": 0.97,
                "size": 50,
                "model_score": 0.99,
                "created_at": "2024-12-18T12:01:00+00:00",
            },
        ]

        tracker = TriggerTracker(mock_db)

        triggers = await tracker.get_triggers_for_condition("0x123")

        assert len(triggers) == 2
        assert triggers[0].token_id == "tok_yes"
        assert triggers[1].token_id == "tok_no"


class TestThresholdHandling:
    """Tests for different threshold values."""

    @pytest.mark.asyncio
    async def test_different_thresholds_independent(self, mock_db):
        """Same token at different thresholds should be independent."""
        # First check at 0.95 - not triggered
        # Second check at 0.97 - also not triggered
        mock_db.fetchval.side_effect = [None, None, None, None]

        tracker = TriggerTracker(mock_db)

        # Check 0.95 threshold
        at_95 = await tracker.should_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
        )

        # Check 0.97 threshold
        at_97 = await tracker.should_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.97"),
        )

        assert at_95 is True
        assert at_97 is True

    @pytest.mark.asyncio
    async def test_uses_default_threshold(self, mock_db):
        """Should use 0.95 as default threshold."""
        mock_db.fetchval.return_value = None

        tracker = TriggerTracker(mock_db)

        await tracker.is_first_trigger(
            token_id="tok_abc",
            condition_id="0x123",
            # No threshold specified - should default to 0.95
        )

        # Verify 0.95 was used in query
        call_args = mock_db.fetchval.call_args[0]
        assert 0.95 in call_args or "0.95" in str(call_args)


class TestAtomicTriggerRecording:
    """
    Tests for atomic trigger recording.

    FIX: G2 TOCTOU race condition prevention.
    The atomic method prevents race conditions where two events
    check for existing triggers simultaneously, both find none,
    and both attempt to record.
    """

    @pytest.mark.asyncio
    async def test_atomic_returns_true_for_first_trigger(self, mock_db):
        """
        Atomic method should return True when trigger is new.

        This is the G2-safe method that uses transactions.
        """
        # Use the mock_conn from the fixture and configure it
        mock_conn = mock_db._mock_conn
        mock_conn.fetchval.side_effect = [None, "tok_abc"]  # No existing, insert succeeds

        tracker = TriggerTracker(mock_db)

        result = await tracker.try_record_trigger_atomic(
            token_id="tok_abc",
            condition_id="0x123",
            threshold=Decimal("0.95"),
            price=Decimal("0.96"),
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_atomic_returns_false_for_duplicate(self, mock_db):
        """
        Atomic method should return False for duplicate triggers.

        G2 FIX: This prevents TOCTOU race where parallel events
        both think they're first.
        """
        # Use the mock_conn from the fixture and configure it
        mock_conn = mock_db._mock_conn
        mock_conn.fetchval.side_effect = None  # Reset side_effect
        mock_conn.fetchval.return_value = 1  # Existing trigger found

        tracker = TriggerTracker(mock_db)

        result = await tracker.try_record_trigger_atomic(
            token_id="tok_xyz",
            condition_id="0x123",  # Same condition as existing
            threshold=Decimal("0.95"),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_atomic_uses_transaction(self, mock_db):
        """
        Atomic method must use database transaction.

        This ensures the check-and-insert is indivisible.
        """
        # Use the mock_conn from the fixture and configure it
        mock_conn = mock_db._mock_conn
        mock_conn.fetchval.side_effect = [None, "tok_abc"]

        tracker = TriggerTracker(mock_db)

        await tracker.try_record_trigger_atomic(
            token_id="tok_abc",
            condition_id="0x123",
        )

        # Verify transaction was used
        mock_db.transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_atomic_checks_condition_first(self, mock_db):
        """
        Should check condition-level trigger before inserting.

        G2: Different tokens for same condition should be blocked.
        """
        # Use the mock_conn from the fixture and configure it
        mock_conn = mock_db._mock_conn
        mock_conn.fetchval.side_effect = None  # Reset side_effect
        mock_conn.fetchval.return_value = 1  # Condition check returns existing trigger

        tracker = TriggerTracker(mock_db)

        # Try to trigger with different token_id but same condition_id
        result = await tracker.try_record_trigger_atomic(
            token_id="tok_new",
            condition_id="0x123",  # Condition already triggered
        )

        assert result is False


class TestAtomicTriggerConcurrency:
    """Tests for concurrent atomic trigger recording."""

    @pytest.mark.asyncio
    async def test_concurrent_atomic_calls_only_one_succeeds(self):
        """Concurrent calls should allow only one trigger per condition."""
        lock = asyncio.Lock()
        store: set[tuple[str, float]] = set()

        class FakeConn:
            def __init__(self, shared_lock, shared_store):
                self._lock = shared_lock
                self._store = shared_store
                self._lock_acquired = False

            async def execute(self, query, *args):
                if "pg_advisory_xact_lock" in query:
                    await self._lock.acquire()
                    self._lock_acquired = True
                return "OK"

            async def fetchval(self, query, *args):
                normalized = " ".join(query.split()).upper()
                if normalized.startswith("SELECT 1 FROM POLYMARKET_FIRST_TRIGGERS"):
                    condition_id = args[0]
                    threshold = float(args[1])
                    return 1 if (condition_id, threshold) in self._store else None
                if normalized.startswith("INSERT INTO POLYMARKET_FIRST_TRIGGERS"):
                    token_id = args[0]
                    condition_id = args[1]
                    threshold = float(args[2])
                    key = (condition_id, threshold)
                    if key in self._store:
                        return None
                    self._store.add(key)
                    return token_id
                return None

        class FakeTransaction:
            def __init__(self, shared_lock, shared_store):
                self._lock = shared_lock
                self._conn = FakeConn(shared_lock, shared_store)

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                if self._conn._lock_acquired:
                    self._lock.release()
                    self._conn._lock_acquired = False

        class FakeDB:
            def __init__(self, shared_lock, shared_store):
                self._lock = shared_lock
                self._store = shared_store

            def transaction(self):
                return FakeTransaction(self._lock, self._store)

        tracker = TriggerTracker(FakeDB(lock, store))

        results = await asyncio.gather(
            tracker.try_record_trigger_atomic(
                token_id="tok_a",
                condition_id="cond_1",
                threshold=Decimal("0.95"),
            ),
            tracker.try_record_trigger_atomic(
                token_id="tok_b",
                condition_id="cond_1",
                threshold=Decimal("0.95"),
            ),
        )

        assert results.count(True) == 1
        assert results.count(False) == 1
        assert ("cond_1", 0.95) in store
