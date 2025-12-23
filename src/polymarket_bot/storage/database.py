"""
Async PostgreSQL database connection management.

Provides connection pooling with asyncpg for high-performance async access.
Includes automatic reconnection with exponential backoff.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class DatabaseConfig(BaseModel):
    """PostgreSQL database configuration."""

    model_config = ConfigDict(frozen=True)

    url: str = os.environ.get(
        "DATABASE_URL", "postgresql://predict:predict@localhost:5432/predict"
    )
    min_connections: int = 2
    max_connections: int = 10
    command_timeout: float = 60.0

    # Reconnection settings
    reconnect_max_attempts: int = 5
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    reconnect_multiplier: float = 2.0

    # Retry settings for transient errors
    retry_max_attempts: int = 3
    retry_initial_delay: float = 0.1
    retry_max_delay: float = 2.0


class Database:
    """
    Async PostgreSQL database connection manager.

    Uses asyncpg connection pooling for high performance.
    Includes automatic reconnection with exponential backoff.

    Usage:
        db = Database(DatabaseConfig())
        await db.initialize()

        async with db.connection() as conn:
            rows = await conn.fetch("SELECT * FROM positions WHERE status = $1", "open")

        async with db.transaction() as conn:
            await conn.execute("INSERT INTO positions ...")
            # Auto-commits on success, rollbacks on exception

        await db.close()
    """

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        self.config = config or DatabaseConfig()
        self._pool: Optional[asyncpg.Pool] = None
        self._reconnecting = False
        self._reconnect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if pool is connected and ready."""
        return self._pool is not None and not self._pool._closed

    async def _close_pool(self) -> None:
        """Close the pool, marking it as needing reconnect."""
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:
                pass
            self._pool = None

    async def initialize(self) -> None:
        """Initialize connection pool."""
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            self.config.url,
            min_size=self.config.min_connections,
            max_size=self.config.max_connections,
            command_timeout=self.config.command_timeout,
        )
        logger.info(
            f"Database pool initialized "
            f"(min={self.config.min_connections}, max={self.config.max_connections})"
        )

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

    async def _ensure_connected(self) -> None:
        """Ensure database is connected, attempt reconnect if not."""
        if self.is_connected:
            return

        async with self._reconnect_lock:
            # Double-check after acquiring lock
            if self.is_connected:
                return

            if self._reconnecting:
                # Another coroutine is already reconnecting, wait
                return

            self._reconnecting = True
            try:
                await self._reconnect()
            finally:
                self._reconnecting = False

    async def _reconnect(self) -> None:
        """
        Attempt to reconnect with exponential backoff.

        Raises RuntimeError if all attempts fail.
        """
        delay = self.config.reconnect_initial_delay

        for attempt in range(1, self.config.reconnect_max_attempts + 1):
            try:
                logger.info(f"Database reconnect attempt {attempt}/{self.config.reconnect_max_attempts}")

                # Close existing pool if any
                if self._pool is not None:
                    try:
                        await self._pool.close()
                    except Exception:
                        pass
                    self._pool = None

                # Create new pool
                self._pool = await asyncpg.create_pool(
                    self.config.url,
                    min_size=self.config.min_connections,
                    max_size=self.config.max_connections,
                    command_timeout=self.config.command_timeout,
                )

                # Verify connection works
                async with self._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")

                logger.info("Database reconnected successfully")
                return

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.warning(f"Database reconnect attempt {attempt} failed: {e}")

                if attempt < self.config.reconnect_max_attempts:
                    logger.info(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    delay = min(delay * self.config.reconnect_multiplier, self.config.reconnect_max_delay)

        raise RuntimeError(
            f"Database reconnect failed after {self.config.reconnect_max_attempts} attempts"
        )

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Get a connection from the pool.

        Use for read operations or manual transaction control.
        Automatically attempts reconnect if pool is disconnected.
        """
        await self._ensure_connected()

        if self._pool is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        try:
            async with self._pool.acquire() as conn:
                yield conn
        except (
            asyncpg.InterfaceError,
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.ConnectionFailureError,
            ConnectionResetError,
            ConnectionRefusedError,
            OSError,
        ) as e:
            # Connection issue - close pool to force reconnect for next caller
            logger.warning(f"Database connection error: {e}")
            await self._close_pool()
            raise

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Get a connection with automatic transaction management.

        Commits on successful exit, rolls back on exception.
        """
        await self._ensure_connected()

        if self._pool is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    yield conn
        except (
            asyncpg.InterfaceError,
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.ConnectionFailureError,
            ConnectionResetError,
            ConnectionRefusedError,
            OSError,
        ) as e:
            # Connection issue - close pool to force reconnect for next caller
            logger.warning(f"Database transaction error: {e}")
            await self._close_pool()
            raise

    async def health_check(self) -> bool:
        """
        Check if database is accessible.

        Returns True if healthy, False if not.
        Does NOT attempt reconnection - use ensure_healthy() for that.
        """
        if not self.is_connected:
            return False

        try:
            async with self.connection() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    async def ensure_healthy(self) -> bool:
        """
        Ensure database is healthy, attempting reconnect if needed.

        Returns True if healthy after any reconnection attempts,
        False if reconnection failed.
        """
        if await self.health_check():
            return True

        try:
            await self._ensure_connected()
            return await self.health_check()
        except Exception as e:
            logger.error(f"Database ensure_healthy failed: {e}")
            return False

    async def _with_retry(self, operation, *args, **kwargs):
        """
        Execute an operation with retry logic for transient errors.

        Retries on connection errors with exponential backoff.
        """
        delay = self.config.retry_initial_delay
        last_error = None

        for attempt in range(1, self.config.retry_max_attempts + 1):
            try:
                return await operation(*args, **kwargs)
            except (
                asyncpg.InterfaceError,
                asyncpg.ConnectionDoesNotExistError,
                asyncpg.ConnectionFailureError,
                ConnectionResetError,
                ConnectionRefusedError,
                OSError,
            ) as e:
                last_error = e
                if attempt < self.config.retry_max_attempts:
                    logger.warning(
                        f"Transient DB error (attempt {attempt}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.config.retry_max_delay)
                    # Try to reconnect
                    await self._ensure_connected()

        # All retries exhausted
        logger.error(f"DB operation failed after {self.config.retry_max_attempts} attempts")
        raise last_error

    async def execute(self, query: str, *args) -> str:
        """Execute a query and return status. Retries on transient errors."""
        async def _do_execute():
            async with self.connection() as conn:
                return await conn.execute(query, *args)
        return await self._with_retry(_do_execute)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch all rows matching query. Retries on transient errors."""
        async def _do_fetch():
            async with self.connection() as conn:
                return await conn.fetch(query, *args)
        return await self._with_retry(_do_fetch)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row. Retries on transient errors."""
        async def _do_fetchrow():
            async with self.connection() as conn:
                return await conn.fetchrow(query, *args)
        return await self._with_retry(_do_fetchrow)

    async def fetchval(self, query: str, *args):
        """Fetch a single value. Retries on transient errors."""
        async def _do_fetchval():
            async with self.connection() as conn:
                return await conn.fetchval(query, *args)
        return await self._with_retry(_do_fetchval)
