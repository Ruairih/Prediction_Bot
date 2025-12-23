"""
Trigger repository tests.

CRITICAL: Tests for dual-key deduplication (G2 gotcha fix).
"""
from datetime import datetime

import pytest

from polymarket_bot.storage.models import PolymarketFirstTrigger
from polymarket_bot.storage.repositories import TriggerRepository, TriggerWatermarkRepository


@pytest.mark.asyncio
class TestTriggerRepository:
    """Tests for TriggerRepository."""

    async def test_create_trigger(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test creating a trigger."""
        result = await trigger_repo.create(sample_trigger)

        assert result.token_id == sample_trigger.token_id
        assert result.threshold == pytest.approx(sample_trigger.threshold, rel=1e-5)
        assert float(result.price) == pytest.approx(float(sample_trigger.price), rel=1e-5)

    async def test_has_triggered_returns_true(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test has_triggered returns True for existing trigger."""
        await trigger_repo.create(sample_trigger)

        result = await trigger_repo.has_triggered(
            sample_trigger.token_id,
            sample_trigger.condition_id,
            sample_trigger.threshold,
        )

        assert result is True

    async def test_has_triggered_returns_false(self, trigger_repo: TriggerRepository):
        """Test has_triggered returns False for non-existent trigger."""
        result = await trigger_repo.has_triggered("nonexistent", "0xcondition", 0.95)

        assert result is False

    async def test_has_triggered_different_condition_returns_false(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """
        Test has_triggered returns False for different condition_id.

        This tests the fix where old migrated rows with empty condition_id
        should not suppress new triggers with actual condition_ids.
        """
        await trigger_repo.create(sample_trigger)

        # Same token_id but different condition_id should return False
        result = await trigger_repo.has_triggered(
            sample_trigger.token_id,
            "0xdifferent_condition",  # Different condition
            sample_trigger.threshold,
        )

        assert result is False, "Different condition_id should not match"

    async def test_has_condition_triggered_critical(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """
        CRITICAL TEST: G2 gotcha - dual-key deduplication.

        Multiple token_ids can map to the same condition_id.
        We must check condition_id to prevent duplicate trades.
        """
        await trigger_repo.create(sample_trigger)

        # Different token_id, SAME condition_id
        result = await trigger_repo.has_condition_triggered(
            sample_trigger.condition_id, sample_trigger.threshold
        )

        assert result is True, "Must detect trigger by condition_id to prevent duplicates"

    async def test_should_trigger_blocks_same_token(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test should_trigger returns False for existing token_id."""
        await trigger_repo.create(sample_trigger)

        result = await trigger_repo.should_trigger(
            sample_trigger.token_id,
            sample_trigger.condition_id,
            sample_trigger.threshold,
        )

        assert result is False

    async def test_should_trigger_blocks_same_condition(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """
        CRITICAL TEST: should_trigger blocks duplicate condition_id.

        Even with a NEW token_id, if the condition_id already triggered,
        should_trigger must return False.
        """
        await trigger_repo.create(sample_trigger)

        # New token_id but same condition_id
        result = await trigger_repo.should_trigger(
            "0xdifferent_token",  # Different token
            sample_trigger.condition_id,  # Same condition
            sample_trigger.threshold,
        )

        assert result is False, "Must block same condition_id even with different token_id"

    async def test_should_trigger_allows_new(self, trigger_repo: TriggerRepository):
        """Test should_trigger returns True for completely new trigger."""
        result = await trigger_repo.should_trigger(
            "0xnew_token", "0xnew_condition", 0.95
        )

        assert result is True

    async def test_different_thresholds_allowed(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test same token can trigger at different thresholds."""
        await trigger_repo.create(sample_trigger)

        # Same token, different threshold
        result = await trigger_repo.should_trigger(
            sample_trigger.token_id,
            sample_trigger.condition_id,
            0.90,  # Different threshold
        )

        assert result is True

    async def test_duplicate_insert_is_noop(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test duplicate insert doesn't error (ON CONFLICT DO NOTHING)."""
        await trigger_repo.create(sample_trigger)

        # Should not raise
        result = await trigger_repo.create(sample_trigger)

        # Count should still be 1
        count = await trigger_repo.count()
        assert count == 1

    async def test_get_by_token(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test getting triggers by token_id."""
        await trigger_repo.create(sample_trigger)

        # Create another with different threshold
        trigger2 = sample_trigger.model_copy()
        trigger2.threshold = 0.90
        await trigger_repo.create(trigger2)

        results = await trigger_repo.get_by_token(sample_trigger.token_id)

        assert len(results) == 2

    async def test_get_by_condition(
        self, trigger_repo: TriggerRepository, sample_trigger: PolymarketFirstTrigger
    ):
        """Test getting triggers by condition_id."""
        await trigger_repo.create(sample_trigger)

        results = await trigger_repo.get_by_condition(sample_trigger.condition_id)

        assert len(results) == 1
        assert results[0].condition_id == sample_trigger.condition_id


@pytest.mark.asyncio
class TestTriggerWatermarkRepository:
    """Tests for TriggerWatermarkRepository."""

    async def test_get_timestamp_returns_zero_if_none(
        self, trigger_watermark_repo: TriggerWatermarkRepository
    ):
        """Test get_timestamp returns 0 for non-existent watermark."""
        result = await trigger_watermark_repo.get_timestamp(0.95)

        assert result == 0

    async def test_update_creates_watermark(
        self, trigger_watermark_repo: TriggerWatermarkRepository
    ):
        """Test update creates new watermark."""
        timestamp = int(datetime.utcnow().timestamp())

        result = await trigger_watermark_repo.update(0.95, timestamp)

        assert result.threshold == pytest.approx(0.95, rel=1e-5)
        assert result.last_timestamp == timestamp

    async def test_update_advances_watermark(
        self, trigger_watermark_repo: TriggerWatermarkRepository
    ):
        """Test update advances watermark (uses GREATEST)."""
        await trigger_watermark_repo.update(0.95, 1000)
        await trigger_watermark_repo.update(0.95, 2000)

        result = await trigger_watermark_repo.get_timestamp(0.95)

        assert result == 2000

    async def test_update_does_not_go_backwards(
        self, trigger_watermark_repo: TriggerWatermarkRepository
    ):
        """Test watermark doesn't go backwards."""
        await trigger_watermark_repo.update(0.95, 2000)
        await trigger_watermark_repo.update(0.95, 1000)  # Try to go back

        result = await trigger_watermark_repo.get_timestamp(0.95)

        assert result == 2000, "Watermark should not go backwards"
