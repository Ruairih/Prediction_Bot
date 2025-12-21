"""
Position repository tests.

Tests for position tracking, P&L calculation, and exit events.
"""
from datetime import datetime

import pytest

from polymarket_bot.storage.models import ExitEvent, Position
from polymarket_bot.storage.repositories import (
    ExitEventRepository,
    PositionRepository,
)


@pytest.mark.asyncio
class TestPositionRepository:
    """Tests for PositionRepository."""

    async def test_create_position(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test creating a position."""
        result = await position_repo.create(sample_position)

        assert result.id is not None
        assert result.token_id == sample_position.token_id
        assert result.entry_price == sample_position.entry_price
        assert result.status == "open"

    async def test_get_open_positions(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test getting open positions."""
        await position_repo.create(sample_position)

        results = await position_repo.get_open()

        assert len(results) == 1
        assert results[0].status == "open"

    async def test_get_open_by_token(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test getting open position for specific token."""
        await position_repo.create(sample_position)

        result = await position_repo.get_open_by_token(sample_position.token_id)

        assert result is not None
        assert result.token_id == sample_position.token_id

    async def test_update_price_recalculates_pnl(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test that update_price recalculates unrealized P&L."""
        created = await position_repo.create(sample_position)

        # Update price (position was entered at 0.75, now at 0.85)
        result = await position_repo.update_price(created.id, 0.85)

        assert float(result.current_price) == pytest.approx(0.85, rel=1e-5)
        assert float(result.current_value) == pytest.approx(100.0 * 0.85, rel=1e-5)  # size * price
        # P&L = current_value - entry_cost = 85 - 75 = 10
        assert result.unrealized_pnl == 10.0

    async def test_close_position(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test closing a position."""
        created = await position_repo.create(sample_position)

        result = await position_repo.close(
            created.id, exit_price=0.90, exit_order_id="exit_123"
        )

        assert result.status == "closed"
        assert result.exit_order_id == "exit_123"
        assert result.exit_timestamp is not None
        # P&L = (100 * 0.90) - 75 = 90 - 75 = 15
        assert result.realized_pnl == 15.0
        assert result.unrealized_pnl == 0

    async def test_resolve_position(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test resolving a position (market resolution)."""
        created = await position_repo.create(sample_position)

        # Token won (paid out at $1)
        result = await position_repo.resolve(
            created.id, resolution="won", final_value=100.0
        )

        assert result.status == "resolved"
        assert result.resolution == "won"
        # P&L = 100 - 75 = 25
        assert result.realized_pnl == 25.0

    async def test_get_total_exposure(
        self, position_repo: PositionRepository, sample_position: Position
    ):
        """Test calculating total exposure."""
        # Create two positions
        await position_repo.create(sample_position)

        pos2 = sample_position.model_copy()
        pos2.token_id = "0xtoken456"
        pos2.entry_cost = 50.0
        await position_repo.create(pos2)

        result = await position_repo.get_total_exposure()

        assert result == 125.0  # 75 + 50


@pytest.mark.asyncio
class TestExitEventRepository:
    """Tests for ExitEventRepository."""

    async def test_create_exit_event(
        self, position_repo: PositionRepository, sample_position: Position, clean_db
    ):
        """Test creating an exit event."""
        from polymarket_bot.storage.repositories.position_repo import ExitEventRepository

        position = await position_repo.create(sample_position)
        exit_repo = ExitEventRepository(clean_db)

        event = ExitEvent(
            position_id=position.id,
            token_id=position.token_id,
            condition_id=position.condition_id,
            exit_type="take_profit",
            entry_price=0.75,
            exit_price=0.90,
            size=100.0,
            gross_pnl=15.0,
            net_pnl=14.5,  # After fees
            hours_held=24.0,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )

        result = await exit_repo.create(event)

        assert result.id is not None
        assert result.exit_type == "take_profit"
        assert result.status == "pending"

    async def test_get_pending_exits(
        self, position_repo: PositionRepository, sample_position: Position, clean_db
    ):
        """Test getting pending exit events."""
        from polymarket_bot.storage.repositories.position_repo import ExitEventRepository

        position = await position_repo.create(sample_position)
        exit_repo = ExitEventRepository(clean_db)

        event = ExitEvent(
            position_id=position.id,
            token_id=position.token_id,
            exit_type="stop_loss",
            entry_price=0.75,
            exit_price=0.60,
            size=100.0,
            gross_pnl=-15.0,
            net_pnl=-15.5,
            hours_held=2.0,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )
        await exit_repo.create(event)

        results = await exit_repo.get_pending()

        assert len(results) == 1
        assert results[0].exit_type == "stop_loss"

    async def test_mark_exit_executed(
        self, position_repo: PositionRepository, sample_position: Position, clean_db
    ):
        """Test marking exit as executed."""
        from polymarket_bot.storage.repositories.position_repo import ExitEventRepository

        position = await position_repo.create(sample_position)
        exit_repo = ExitEventRepository(clean_db)

        event = ExitEvent(
            position_id=position.id,
            token_id=position.token_id,
            exit_type="manual",
            entry_price=0.75,
            exit_price=0.80,
            size=100.0,
            gross_pnl=5.0,
            net_pnl=4.5,
            hours_held=48.0,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )
        created = await exit_repo.create(event)

        result = await exit_repo.mark_executed(created.id)

        assert result.status == "executed"
        assert result.executed_at is not None
