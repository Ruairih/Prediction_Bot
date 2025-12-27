"""
Database connection tests.

Tests for async PostgreSQL connection management.
"""
import pytest
from unittest.mock import AsyncMock

from polymarket_bot.storage.database import Database, DatabaseConfig


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DatabaseConfig()
        assert config.min_connections == 2
        assert config.max_connections == 10
        assert config.command_timeout == 60.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = DatabaseConfig(
            url="postgresql://test:test@localhost:5432/test",
            min_connections=5,
            max_connections=20,
        )
        assert config.url == "postgresql://test:test@localhost:5432/test"
        assert config.min_connections == 5
        assert config.max_connections == 20


@pytest.mark.asyncio
class TestDatabaseConnection:
    """Tests for database connections."""

    async def test_initialize_creates_pool(self, db: Database):
        """Test that initialize creates a connection pool."""
        assert db._pool is not None

    async def test_health_check_returns_true(self, db: Database):
        """Test health check on working database."""
        result = await db.health_check()
        assert result is True

    async def test_fetch_returns_records(self, db: Database):
        """Test basic fetch operation."""
        result = await db.fetchval("SELECT 1")
        assert result == 1

    async def test_connection_context_manager(self, db: Database):
        """Test connection context manager."""
        async with db.connection() as conn:
            result = await conn.fetchval("SELECT 42")
        assert result == 42

    async def test_transaction_commits_on_success(self, db: Database):
        """Test transaction commits successfully."""
        # Create a temp table for testing
        await db.execute("""
            CREATE TEMP TABLE test_commit (id INT, value TEXT)
        """)

        async with db.transaction() as conn:
            await conn.execute("INSERT INTO test_commit VALUES (1, 'test')")

        # Verify data persisted
        result = await db.fetchval("SELECT value FROM test_commit WHERE id = 1")
        assert result == "test"

    async def test_transaction_rollback_on_exception(self, db: Database):
        """Test transaction rolls back on exception."""
        # Create a temp table for testing
        await db.execute("""
            CREATE TEMP TABLE test_rollback (id INT, value TEXT)
        """)

        with pytest.raises(ValueError):
            async with db.transaction() as conn:
                await conn.execute("INSERT INTO test_rollback VALUES (1, 'test')")
                raise ValueError("Simulated error")

        # Verify data was rolled back
        result = await db.fetchval("SELECT COUNT(*) FROM test_rollback")
        assert result == 0


@pytest.mark.asyncio
class TestDatabaseUnreachable:
    """Tests for unreachable database."""

    async def test_connection_raises_with_bad_url(self):
        """Test that connection raises when database is unreachable."""
        bad_config = DatabaseConfig(
            url="postgresql://bad:bad@localhost:59999/nonexistent",
            reconnect_max_attempts=1,  # Fail fast
            reconnect_initial_delay=0.1,
        )
        db = Database(bad_config)

        with pytest.raises(Exception):  # Connection error
            async with db.connection():
                pass

    async def test_transaction_raises_with_bad_url(self):
        """Test that transaction raises when database is unreachable."""
        bad_config = DatabaseConfig(
            url="postgresql://bad:bad@localhost:59999/nonexistent",
            reconnect_max_attempts=1,  # Fail fast
            reconnect_initial_delay=0.1,
        )
        db = Database(bad_config)

        with pytest.raises(Exception):  # Connection error
            async with db.transaction():
                pass


@pytest.mark.asyncio
class TestDatabaseRecovery:
    """Tests for reconnection and retry behavior."""

    async def test_ensure_connected_triggers_reconnect_when_pool_closed(self):
        """Should attempt reconnect when pool is missing/closed."""
        db = Database(DatabaseConfig())
        db._pool = None
        db._reconnect = AsyncMock()

        await db._ensure_connected()

        db._reconnect.assert_awaited_once()

    async def test_with_retry_reconnects_after_transient_error(self):
        """Transient errors should trigger reconnect and retry."""
        config = DatabaseConfig(
            retry_max_attempts=2,
            retry_initial_delay=0.0,
            retry_max_delay=0.0,
        )
        db = Database(config)
        db._ensure_connected = AsyncMock()

        attempts = {"count": 0}

        async def flaky_operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ConnectionResetError("lost connection")
            return "ok"

        result = await db._with_retry(flaky_operation)

        assert result == "ok"
        db._ensure_connected.assert_awaited()
