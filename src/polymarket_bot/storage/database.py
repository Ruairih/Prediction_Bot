"""
Async PostgreSQL database connection management.

Provides connection pooling with asyncpg for high-performance async access.
"""
from __future__ import annotations

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


class Database:
    """
    Async PostgreSQL database connection manager.

    Uses asyncpg connection pooling for high performance.

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
        logger.info(f"Database pool initialized (min={self.config.min_connections}, max={self.config.max_connections})")

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Get a connection from the pool.

        Use for read operations or manual transaction control.
        """
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """
        Get a connection with automatic transaction management.

        Commits on successful exit, rolls back on exception.
        """
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def health_check(self) -> bool:
        """Check if database is accessible."""
        try:
            async with self.connection() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    async def execute(self, query: str, *args) -> str:
        """Execute a query and return status."""
        async with self.connection() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch all rows matching query."""
        async with self.connection() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row."""
        async with self.connection() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Fetch a single value."""
        async with self.connection() as conn:
            return await conn.fetchval(query, *args)
