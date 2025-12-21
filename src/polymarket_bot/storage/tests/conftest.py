"""
Test fixtures for async PostgreSQL storage tests.

These fixtures connect to the docker-compose PostgreSQL instance.
Ensure docker-compose is running before running tests:
    docker-compose up -d postgres

Each test gets a clean database state through transaction rollback.
"""
import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from polymarket_bot.storage.database import Database, DatabaseConfig
from polymarket_bot.storage.models import (
    LiveOrder,
    PaperTrade,
    PolymarketCandidate,
    PolymarketFirstTrigger,
    PolymarketTrade,
    Position,
)
from polymarket_bot.storage.repositories import (
    CandidateRepository,
    LiveOrderRepository,
    PaperTradeRepository,
    PositionRepository,
    TradeRepository,
    TradeWatermarkRepository,
    TriggerRepository,
    TriggerWatermarkRepository,
)


# =============================================================================
# EVENT LOOP FIXTURE
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# DATABASE FIXTURES
# =============================================================================


@pytest.fixture
def db_config() -> DatabaseConfig:
    """Database config from environment or defaults."""
    return DatabaseConfig(
        url=os.environ.get(
            "DATABASE_URL",
            "postgresql://predict:predict@localhost:5433/predict"
        )
    )


@pytest_asyncio.fixture
async def db(db_config: DatabaseConfig) -> AsyncGenerator[Database, None]:
    """
    Fresh database connection for each test.

    Uses transaction rollback to isolate tests without deleting data.
    """
    database = Database(db_config)
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def clean_db(db: Database) -> AsyncGenerator[Database, None]:
    """
    Database with test tables cleared.

    Use this when you need a clean slate for testing.
    WARNING: This deletes data from test tables.
    """
    # Clear test-relevant tables (be careful in shared environments)
    tables_to_clear = [
        "polymarket_trades",
        "trade_watermarks",
        "polymarket_first_triggers",
        "trigger_watermarks",
        "polymarket_candidates",
        "candidate_watermarks",
        "paper_trades",
        "live_orders",
        "positions",
        "exit_events",
    ]
    async with db.transaction() as conn:
        for table in tables_to_clear:
            await conn.execute(f"DELETE FROM {table}")
    yield db


# =============================================================================
# REPOSITORY FIXTURES
# =============================================================================


@pytest_asyncio.fixture
async def trade_repo(clean_db: Database) -> TradeRepository:
    """Trade repository with clean database."""
    return TradeRepository(clean_db)


@pytest_asyncio.fixture
async def trade_watermark_repo(clean_db: Database) -> TradeWatermarkRepository:
    """Trade watermark repository."""
    return TradeWatermarkRepository(clean_db)


@pytest_asyncio.fixture
async def trigger_repo(clean_db: Database) -> TriggerRepository:
    """Trigger repository with clean database."""
    return TriggerRepository(clean_db)


@pytest_asyncio.fixture
async def trigger_watermark_repo(clean_db: Database) -> TriggerWatermarkRepository:
    """Trigger watermark repository."""
    return TriggerWatermarkRepository(clean_db)


@pytest_asyncio.fixture
async def candidate_repo(clean_db: Database) -> CandidateRepository:
    """Candidate repository with clean database."""
    return CandidateRepository(clean_db)


@pytest_asyncio.fixture
async def paper_trade_repo(clean_db: Database) -> PaperTradeRepository:
    """Paper trade repository."""
    return PaperTradeRepository(clean_db)


@pytest_asyncio.fixture
async def live_order_repo(clean_db: Database) -> LiveOrderRepository:
    """Live order repository."""
    return LiveOrderRepository(clean_db)


@pytest_asyncio.fixture
async def position_repo(clean_db: Database) -> PositionRepository:
    """Position repository with clean database."""
    return PositionRepository(clean_db)


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_trade() -> PolymarketTrade:
    """Sample trade for testing."""
    return PolymarketTrade(
        condition_id="0xabc123",
        trade_id="trade_001",
        token_id="0xtoken123",
        price=0.75,
        size=100.0,
        side="buy",
        timestamp=int(datetime.utcnow().timestamp()),
        outcome="Yes",
        outcome_index=0,
    )


@pytest.fixture
def sample_trigger() -> PolymarketFirstTrigger:
    """Sample trigger for testing."""
    return PolymarketFirstTrigger(
        token_id="0xtoken123",
        condition_id="0xabc123",
        threshold=0.95,
        trigger_timestamp=int(datetime.utcnow().timestamp()),
        price=0.95,
        size=50.0,
        created_at=datetime.utcnow().isoformat(),
        model_score=0.87,
        outcome="Yes",
        outcome_index=0,
    )


@pytest.fixture
def sample_candidate() -> PolymarketCandidate:
    """Sample candidate for testing."""
    return PolymarketCandidate(
        token_id="0xtoken123",
        condition_id="0xabc123",
        threshold=0.95,
        trigger_timestamp=int(datetime.utcnow().timestamp()),
        price=0.95,
        status="pending",
        score=0.87,
        created_at=datetime.utcnow().isoformat(),
        model_score=0.87,
        outcome="Yes",
        outcome_index=0,
    )


@pytest.fixture
def sample_position() -> Position:
    """Sample position for testing."""
    now = datetime.utcnow().isoformat()
    return Position(
        token_id="0xtoken123",
        condition_id="0xabc123",
        outcome="Yes",
        outcome_index=0,
        side="BUY",
        size=100.0,
        entry_price=0.75,
        entry_cost=75.0,
        status="open",
        entry_timestamp=now,
        created_at=now,
    )


@pytest.fixture
def sample_live_order(sample_candidate: PolymarketCandidate) -> LiveOrder:
    """Sample live order for testing."""
    return LiveOrder(
        order_id="poly_order_123",
        candidate_id=1,  # Will be updated after candidate is created
        token_id="0xtoken123",
        condition_id="0xabc123",
        threshold=0.95,
        order_price=0.95,
        order_size=25.0,
        status="submitted",
        submitted_at=datetime.utcnow().isoformat(),
    )


@pytest.fixture
def sample_paper_trade(sample_candidate: PolymarketCandidate) -> PaperTrade:
    """Sample paper trade for testing."""
    return PaperTrade(
        candidate_id=1,  # Will be updated after candidate is created
        token_id="0xtoken123",
        condition_id="0xabc123",
        threshold=0.95,
        trigger_timestamp=int(datetime.utcnow().timestamp()),
        candidate_price=0.95,
        fill_price=0.94,
        size=25.0,
        model_score=0.87,
        decision="buy",
        reason="High confidence signal",
        created_at=datetime.utcnow().isoformat(),
        outcome="Yes",
        outcome_index=0,
    )
