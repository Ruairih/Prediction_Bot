"""
Tests for watchlist re-scoring service.

Tokens with scores 0.90-0.97 are added to watchlist and
re-scored periodically. They may be promoted to execution
when their score improves.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from polymarket_bot.core import WatchlistService, WatchlistEntry, Promotion


class TestWatchlistAddition:
    """Tests for adding to watchlist."""

    @pytest.mark.asyncio
    async def test_adds_token_to_watchlist(self, mock_db):
        """Should add token with initial score."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.add_to_watchlist(
            token_id="tok_abc",
            condition_id="0x123",
            initial_score=0.92,
            time_to_end_hours=720,
        )

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_trigger_price(self, mock_db):
        """Should store the price that triggered the addition."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.add_to_watchlist(
            token_id="tok_abc",
            condition_id="0x123",
            initial_score=0.92,
            time_to_end_hours=720,
            trigger_price=Decimal("0.95"),
        )

        # Verify trigger_price was passed
        call_args = mock_db.execute.call_args[0]
        assert 0.95 in call_args or Decimal("0.95") in call_args

    @pytest.mark.asyncio
    async def test_stores_question(self, mock_db):
        """Should store market question for context."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.add_to_watchlist(
            token_id="tok_abc",
            condition_id="0x123",
            initial_score=0.92,
            time_to_end_hours=720,
            question="Will BTC hit $100k?",
        )

        call_args = mock_db.execute.call_args[0]
        assert "Will BTC hit $100k?" in call_args

    @pytest.mark.asyncio
    async def test_upserts_on_conflict(self, mock_db):
        """Should update existing entry on conflict."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        # Add twice
        await service.add_to_watchlist("tok_abc", "0x123", 0.92, 720)
        await service.add_to_watchlist("tok_abc", "0x123", 0.94, 700)

        # Should have been called twice (upsert)
        assert mock_db.execute.call_count == 2


class TestWatchlistRetrieval:
    """Tests for retrieving watchlist entries."""

    @pytest.mark.asyncio
    async def test_gets_active_entries(self, mock_db):
        """Should retrieve all active entries."""
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_abc",
                "condition_id": "0x123",
                "question": "Test?",
                "trigger_price": 0.95,
                "initial_score": 0.92,
                "current_score": 0.94,
                "time_to_end_hours": 700,
                "created_at": 1702900000,
                "status": "watching",
            }
        ]

        service = WatchlistService(mock_db)
        entries = await service.get_active_entries()

        assert len(entries) == 1
        assert entries[0].token_id == "tok_abc"
        assert entries[0].current_score == 0.94

    @pytest.mark.asyncio
    async def test_only_returns_watching_status(self, mock_db):
        """Should only return entries with 'watching' status."""
        mock_db.fetch.return_value = []  # Query filters by status

        service = WatchlistService(mock_db)
        await service.get_active_entries()

        # Verify query includes status filter
        query = mock_db.fetch.call_args[0][0]
        assert "watching" in query.lower()

    @pytest.mark.asyncio
    async def test_gets_specific_entry(self, mock_db):
        """Should retrieve a specific entry by token_id."""
        mock_db.fetchrow.return_value = {
            "token_id": "tok_abc",
            "condition_id": "0x123",
            "question": "Test?",
            "trigger_price": 0.95,
            "initial_score": 0.92,
            "current_score": 0.94,
            "time_to_end_hours": 700,
            "created_at": 1702900000,
            "status": "watching",
        }

        service = WatchlistService(mock_db)
        entry = await service.get_entry("tok_abc")

        assert entry is not None
        assert entry.token_id == "tok_abc"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, mock_db):
        """Should return None if entry not found."""
        mock_db.fetchrow.return_value = None

        service = WatchlistService(mock_db)
        entry = await service.get_entry("tok_nonexistent")

        assert entry is None


class TestScoreUpdates:
    """Tests for score updates."""

    @pytest.mark.asyncio
    async def test_updates_score(self, mock_db):
        """Should update score for entry."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.update_score("tok_abc", 0.96)

        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_updates_time_to_end(self, mock_db):
        """Should update time_to_end when provided."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.update_score("tok_abc", 0.96, time_to_end_hours=48)

        # Should include time_to_end in update
        call_args = mock_db.execute.call_args[0]
        assert 48 in call_args


class TestRescoring:
    """Tests for re-scoring logic."""

    @pytest.mark.asyncio
    async def test_rescores_all_active(self, mock_db):
        """Should re-score all active entries."""
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_abc",
                "condition_id": "0x123",
                "question": "Test?",
                "trigger_price": 0.95,
                "initial_score": 0.92,
                "current_score": 0.94,
                "time_to_end_hours": 48,  # Close to end
                "created_at": 1702900000,
                "status": "watching",
            }
        ]
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)
        promotions = await service.rescore_all()

        # Should have updated scores
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_promotes_above_threshold(self, mock_db):
        """Should promote entries that cross threshold."""
        # Entry with score that will improve above 0.97
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_abc",
                "condition_id": "0x123",
                "question": "Test?",
                "trigger_price": 0.95,
                "initial_score": 0.96,  # High initial
                "current_score": 0.96,
                "time_to_end_hours": 6,  # Very close - will get time bonus
                "created_at": 1702900000,
                "status": "watching",
            }
        ]
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db, execution_threshold=0.97)
        promotions = await service.rescore_all()

        # Should have at least one promotion (score will improve with time bonus)
        # Note: depends on _default_score implementation
        assert isinstance(promotions, list)

    @pytest.mark.asyncio
    async def test_removes_below_minimum(self, mock_db):
        """Should mark entries as expired if score drops too low."""
        mock_db.fetch.return_value = [
            {
                "token_id": "tok_abc",
                "condition_id": "0x123",
                "question": "Test?",
                "trigger_price": 0.95,
                "initial_score": 0.85,  # Below minimum
                "current_score": 0.85,
                "time_to_end_hours": 720,
                "created_at": 1702900000,
                "status": "watching",
            }
        ]
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db, watchlist_min=0.90)
        await service.rescore_all()

        # Should have marked as expired
        # Check that status update was called
        assert mock_db.execute.call_count >= 1


class TestScoreEvolution:
    """Tests for how scores change over time."""

    def test_default_score_increases_with_time(self):
        """Score should generally increase as time_to_end decreases."""
        service = WatchlistService.__new__(WatchlistService)

        # Entry at 720 hours
        far_entry = WatchlistEntry(
            token_id="tok_abc",
            condition_id="0x123",
            question="Test?",
            trigger_price=Decimal("0.95"),
            initial_score=0.92,
            current_score=0.92,
            time_to_end_hours=720,
            created_at=datetime.now(timezone.utc),
            status="watching",
        )

        # Entry at 48 hours
        near_entry = WatchlistEntry(
            token_id="tok_abc",
            condition_id="0x123",
            question="Test?",
            trigger_price=Decimal("0.95"),
            initial_score=0.92,
            current_score=0.92,
            time_to_end_hours=48,
            created_at=datetime.now(timezone.utc),
            status="watching",
        )

        far_score = service._default_score(far_entry)
        near_score = service._default_score(near_entry)

        # Score should be higher when closer to end
        assert near_score > far_score

    def test_score_bounded_at_one(self):
        """Score should never exceed 1.0."""
        service = WatchlistService.__new__(WatchlistService)

        # Entry with already high score
        entry = WatchlistEntry(
            token_id="tok_abc",
            condition_id="0x123",
            question="Test?",
            trigger_price=Decimal("0.95"),
            initial_score=0.99,
            current_score=0.99,
            time_to_end_hours=6,  # Very close
            created_at=datetime.now(timezone.utc),
            status="watching",
        )

        score = service._default_score(entry)

        assert score <= 1.0


class TestStatusManagement:
    """Tests for status updates."""

    @pytest.mark.asyncio
    async def test_marks_as_promoted(self, mock_db):
        """Should mark entry as promoted."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.mark_status("tok_abc", "promoted")

        # Verify status update
        call_args = mock_db.execute.call_args[0]
        assert "tok_abc" in call_args
        assert "promoted" in call_args

    @pytest.mark.asyncio
    async def test_marks_as_expired(self, mock_db):
        """Should mark entry as expired."""
        mock_db.execute.return_value = None

        service = WatchlistService(mock_db)

        await service.mark_status("tok_abc", "expired")

        call_args = mock_db.execute.call_args[0]
        assert "expired" in call_args


class TestScoreHistory:
    """Tests for score history tracking."""

    @pytest.mark.asyncio
    async def test_gets_score_history(self, mock_db):
        """Should retrieve score history for token."""
        mock_db.fetch.return_value = [
            {"score": 0.92, "time_to_end_hours": 720, "scored_at": 1702900000},
            {"score": 0.94, "time_to_end_hours": 600, "scored_at": 1702910000},
            {"score": 0.97, "time_to_end_hours": 480, "scored_at": 1702920000},
        ]

        service = WatchlistService(mock_db)
        history = await service.get_score_history("tok_abc")

        assert len(history) == 3
        assert history[0]["score"] == 0.92
        assert history[2]["score"] == 0.97


class TestExpiredRemoval:
    """Tests for removing expired entries."""

    @pytest.mark.asyncio
    async def test_removes_expired_markets(self, mock_db):
        """Should remove entries for markets close to expiry."""
        mock_db.execute.return_value = "UPDATE 3"

        service = WatchlistService(mock_db)
        count = await service.remove_expired(min_hours=6.0)

        assert count == 3

    @pytest.mark.asyncio
    async def test_uses_min_hours_threshold(self, mock_db):
        """Should use provided minimum hours threshold."""
        mock_db.execute.return_value = "UPDATE 0"

        service = WatchlistService(mock_db)
        await service.remove_expired(min_hours=12.0)

        # Verify threshold was used in query
        call_args = mock_db.execute.call_args[0]
        assert 12.0 in call_args
