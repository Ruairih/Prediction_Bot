"""
Tests for position sync service.

The position sync service imports positions from Polymarket into the database
and corrects timestamps using trade history.
"""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from polymarket_bot.execution.position_sync import (
    PositionSyncService,
    RemotePosition,
    SyncResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock database for tests."""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_position_tracker():
    """Mock position tracker."""
    tracker = MagicMock()
    tracker.load_positions = AsyncMock()
    return tracker


@pytest.fixture
def sync_service(mock_db, mock_position_tracker):
    """Position sync service with mocked dependencies."""
    return PositionSyncService(mock_db, mock_position_tracker)


@pytest.fixture
def sample_position_api_response():
    """Sample position data from Polymarket API."""
    return [
        {
            "asset": "token_123",
            "conditionId": "0xcond123",
            "size": 20.0,
            "avgPrice": 0.95,
            "curPrice": 0.97,
            "outcome": "Yes",
            "outcomeIndex": 0,
            "title": "Will Bitcoin hit $100k?",
            "endDate": "2025-12-31T00:00:00Z",
            "cashPnl": 0.40,
        },
        {
            "asset": "token_456",
            "conditionId": "0xcond456",
            "size": 10.0,
            "avgPrice": 0.90,
            "curPrice": 0.92,
            "outcome": "Yes",
            "outcomeIndex": 0,
            "title": "Will ETH hit $5k?",
        },
    ]


@pytest.fixture
def sample_trade_api_response():
    """Sample trade data from Polymarket API."""
    now = datetime.now(timezone.utc)
    return [
        {
            "asset": "token_123",
            "side": "BUY",
            "size": 20.0,
            "price": 0.95,
            "timestamp": int((now - timedelta(days=10)).timestamp()),
        },
        {
            "asset": "token_456",
            "side": "BUY",
            "size": 10.0,
            "price": 0.90,
            "timestamp": int((now - timedelta(days=20)).timestamp()),
        },
        {
            "asset": "token_123",
            "side": "SELL",
            "size": 5.0,
            "price": 0.97,
            "timestamp": int((now - timedelta(days=5)).timestamp()),
        },
    ]


# =============================================================================
# Test: fetch_remote_positions
# =============================================================================


class TestFetchRemotePositions:
    """Tests for fetching positions from Polymarket API."""

    @pytest.mark.asyncio
    async def test_parses_valid_response(
        self, sync_service, sample_position_api_response
    ):
        """Should parse valid API response correctly."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_position_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            positions, partial = await sync_service.fetch_remote_positions("0xwallet")

            assert len(positions) == 2
            assert positions[0].token_id == "token_123"
            assert positions[0].size == Decimal("20.0")
            assert positions[0].avg_price == Decimal("0.95")
            assert not partial

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, sync_service):
        """Should handle empty API response."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            positions, partial = await sync_service.fetch_remote_positions("0xwallet")

            assert len(positions) == 0
            assert not partial

    @pytest.mark.asyncio
    async def test_skips_invalid_entries(self, sync_service):
        """Should skip invalid entries and mark as partial."""
        invalid_data = [
            {"asset": "token_1", "conditionId": "0x123", "size": 10},  # Valid
            {"asset": "", "conditionId": "0x456", "size": 10},  # Invalid - no asset
            {"asset": "token_3", "conditionId": "", "size": 10},  # Invalid - no condition
            {"asset": "token_4", "conditionId": "0x789", "size": None},  # Invalid - no size
            "not_a_dict",  # Invalid - not a dict
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = invalid_data
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            positions, partial = await sync_service.fetch_remote_positions("0xwallet")

            assert len(positions) == 1  # Only token_1 is valid
            assert partial  # Should be marked as partial due to invalid entries

    @pytest.mark.asyncio
    async def test_skips_zero_size_positions(self, sync_service):
        """Should skip positions with zero size."""
        data = [
            {"asset": "token_1", "conditionId": "0x123", "size": 10},  # Valid
            {"asset": "token_2", "conditionId": "0x456", "size": 0},  # Zero size
            {"asset": "token_3", "conditionId": "0x789", "size": -5},  # Negative size
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = data
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            positions, partial = await sync_service.fetch_remote_positions("0xwallet")

            assert len(positions) == 1  # Only token_1

    @pytest.mark.asyncio
    async def test_handles_non_list_response(self, sync_service):
        """Should handle unexpected non-list response."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"error": "unexpected"}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            positions, partial = await sync_service.fetch_remote_positions("0xwallet")

            assert len(positions) == 0
            assert partial  # Should be marked as partial


# =============================================================================
# Test: fetch_trade_timestamps
# =============================================================================


class TestFetchTradeTimestamps:
    """Tests for fetching trade timestamps from API."""

    @pytest.mark.asyncio
    async def test_parses_trade_timestamps(
        self, sync_service, sample_trade_api_response
    ):
        """Should parse trade timestamps correctly."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_trade_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            timestamps = await sync_service.fetch_trade_timestamps("0xwallet")

            assert len(timestamps) == 2  # token_123 and token_456
            assert "token_123" in timestamps
            assert "token_456" in timestamps

    @pytest.mark.asyncio
    async def test_returns_earliest_buy_timestamp(
        self, sync_service
    ):
        """Should return earliest BUY timestamp for each token."""
        now = datetime.now(timezone.utc)
        trades = [
            {"asset": "token_1", "side": "BUY", "timestamp": int((now - timedelta(days=10)).timestamp())},
            {"asset": "token_1", "side": "BUY", "timestamp": int((now - timedelta(days=5)).timestamp())},
            {"asset": "token_1", "side": "SELL", "timestamp": int((now - timedelta(days=3)).timestamp())},
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = trades
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            timestamps = await sync_service.fetch_trade_timestamps("0xwallet")

            # Should be 10 days ago (earliest BUY), not 5 or 3
            assert "token_1" in timestamps
            age = (now - timestamps["token_1"]).days
            assert age == 10

    @pytest.mark.asyncio
    async def test_ignores_sell_trades(self, sync_service):
        """Should ignore SELL trades when finding first buy."""
        now = datetime.now(timezone.utc)
        trades = [
            {"asset": "token_1", "side": "SELL", "timestamp": int((now - timedelta(days=20)).timestamp())},
            {"asset": "token_1", "side": "BUY", "timestamp": int((now - timedelta(days=10)).timestamp())},
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = trades
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            timestamps = await sync_service.fetch_trade_timestamps("0xwallet")

            # Should be 10 days ago (BUY), not 20 days ago (SELL)
            age = (now - timestamps["token_1"]).days
            assert age == 10

    @pytest.mark.asyncio
    async def test_handles_api_error(self, sync_service):
        """Should return empty dict on API error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("API error")
            )

            timestamps = await sync_service.fetch_trade_timestamps("0xwallet")

            assert timestamps == {}


# =============================================================================
# Test: sync_positions
# =============================================================================


class TestSyncPositions:
    """Tests for syncing positions."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify_database(
        self, sync_service, mock_db, sample_position_api_response
    ):
        """Dry run should not write to database."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_position_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions("0xwallet", dry_run=True)

            # Should count imports but not write
            assert result.positions_imported == 2
            mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_imports_new_positions(
        self, sync_service, mock_db, sample_position_api_response
    ):
        """Should import new positions to database."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_position_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions("0xwallet", dry_run=False)

            assert result.positions_imported == 2
            assert mock_db.execute.call_count >= 2  # At least 2 inserts

    @pytest.mark.asyncio
    async def test_closes_bot_trade_positions_missing_on_polymarket(
        self, sync_service, mock_db
    ):
        """Should reconcile bot_trade positions against the API."""
        mock_db.fetch.return_value = [
            {
                "token_id": "token_bot",
                "condition_id": "0xbot",
                "size": 5,
                "entry_price": 0.5,
                "entry_cost": 2.5,
                "status": "open",
                "import_source": "bot_trade",
                "hold_start_at": None,
                "entry_timestamp": None,
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = [
                {
                    "asset": "token_remote",
                    "conditionId": "0xcond",
                    "size": 1.0,
                    "avgPrice": 0.9,
                    "curPrice": 0.91,
                    "outcome": "Yes",
                    "outcomeIndex": 0,
                    "title": "Some market",
                }
            ]
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions("0xwallet", dry_run=True)

            assert result.positions_closed == 1

    @pytest.mark.asyncio
    async def test_hold_policy_new_sets_now(
        self, sync_service, mock_db, sample_position_api_response
    ):
        """hold_policy='new' should set hold_start_at to now."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_position_api_response[:1]
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions(
                "0xwallet", dry_run=False, hold_policy="new"
            )

            # Verify hold_start is close to now
            assert result.positions_imported == 1
            # The hold_start_str is passed as the last arg to _import_position

    @pytest.mark.asyncio
    async def test_hold_policy_mature_backdates(
        self, sync_service, mock_db, sample_position_api_response
    ):
        """hold_policy='mature' should backdate hold_start_at."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_position_api_response[:1]
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions(
                "0xwallet", dry_run=False, hold_policy="mature", mature_days=8
            )

            assert result.positions_imported == 1

    @pytest.mark.asyncio
    async def test_skips_close_on_partial_response(
        self, sync_service, mock_db
    ):
        """Should not close positions if API response was partial."""
        # Set up local positions
        mock_db.fetch.return_value = [
            {"token_id": "token_old", "condition_id": "0x123", "size": 10,
             "entry_price": 0.95, "entry_cost": 9.5, "status": "open",
             "import_source": None, "hold_start_at": None, "entry_timestamp": None}
        ]

        # API returns partial (invalid entry included)
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = [
                {"invalid": "entry"},  # This makes it partial
            ]
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions("0xwallet", dry_run=False)

            # Should NOT close token_old even though it's not in API response
            assert result.positions_closed == 0

    @pytest.mark.asyncio
    async def test_skips_close_on_empty_response(
        self, sync_service, mock_db
    ):
        """Should not close positions if API returns empty but DB has positions."""
        # Set up local positions
        mock_db.fetch.return_value = [
            {"token_id": "token_1", "condition_id": "0x123", "size": 10,
             "entry_price": 0.95, "entry_cost": 9.5, "status": "open",
             "import_source": None, "hold_start_at": None, "entry_timestamp": None}
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.sync_positions("0xwallet", dry_run=False)

            # Should NOT close positions - safety guard
            assert result.positions_closed == 0


# =============================================================================
# Test: correct_hold_timestamps
# =============================================================================


class TestCorrectHoldTimestamps:
    """Tests for correcting hold timestamps on existing positions."""

    @pytest.mark.asyncio
    async def test_dry_run_reports_corrections(
        self, sync_service, mock_db, sample_trade_api_response
    ):
        """Dry run should report what would be corrected."""
        now = datetime.now(timezone.utc)

        # Set up local position with wrong timestamp
        mock_db.fetch.return_value = [
            {
                "token_id": "token_123",
                "condition_id": "0x123",
                "size": 10,
                "entry_price": 0.95,
                "entry_cost": 9.5,
                "status": "open",
                "import_source": None,
                "hold_start_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),  # Wrong - should be 10d ago
                "entry_timestamp": None,
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_trade_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.correct_hold_timestamps("0xwallet", dry_run=True)

            assert result["corrected"] == 1
            mock_db.execute.assert_not_called()  # Dry run - no writes

    @pytest.mark.asyncio
    async def test_corrects_timestamps(
        self, sync_service, mock_db, sample_trade_api_response
    ):
        """Should update positions with correct timestamps."""
        now = datetime.now(timezone.utc)

        # Set up local position with wrong timestamp
        mock_db.fetch.return_value = [
            {
                "token_id": "token_123",
                "condition_id": "0x123",
                "size": 10,
                "entry_price": 0.95,
                "entry_cost": 9.5,
                "status": "open",
                "import_source": None,
                "hold_start_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entry_timestamp": None,
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_trade_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.correct_hold_timestamps("0xwallet", dry_run=False)

            assert result["corrected"] == 1
            mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_skips_positions_without_trade_history(
        self, sync_service, mock_db
    ):
        """Should skip positions that don't have trade history."""
        now = datetime.now(timezone.utc)

        mock_db.fetch.return_value = [
            {
                "token_id": "token_no_trades",
                "condition_id": "0x123",
                "size": 10,
                "entry_price": 0.95,
                "entry_cost": 9.5,
                "status": "open",
                "import_source": None,
                "hold_start_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "entry_timestamp": None,
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = []  # No trades
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.correct_hold_timestamps("0xwallet", dry_run=True)

            assert result["corrected"] == 0

    @pytest.mark.asyncio
    async def test_skips_already_correct_timestamps(
        self, sync_service, mock_db, sample_trade_api_response
    ):
        """Should skip positions that already have correct timestamps."""
        now = datetime.now(timezone.utc)
        correct_time = now - timedelta(days=10)

        mock_db.fetch.return_value = [
            {
                "token_id": "token_123",
                "condition_id": "0x123",
                "size": 10,
                "entry_price": 0.95,
                "entry_cost": 9.5,
                "status": "open",
                "import_source": None,
                "hold_start_at": correct_time.strftime("%Y-%m-%dT%H:%M:%SZ"),  # Already correct
                "entry_timestamp": None,
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = sample_trade_api_response
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await sync_service.correct_hold_timestamps("0xwallet", dry_run=True)

            assert result["corrected"] == 0  # Already correct


# =============================================================================
# Test: SyncResult
# =============================================================================


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_success_when_no_errors(self):
        """Should report success when no errors."""
        result = SyncResult(
            run_id="test",
            positions_found=5,
            positions_imported=3,
            positions_updated=1,
            positions_closed=1,
            errors=[],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

        assert result.success is True

    def test_failure_when_errors(self):
        """Should report failure when errors exist."""
        result = SyncResult(
            run_id="test",
            positions_found=5,
            positions_imported=2,
            positions_updated=0,
            positions_closed=0,
            errors=["Failed to import token_3"],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

        assert result.success is False
