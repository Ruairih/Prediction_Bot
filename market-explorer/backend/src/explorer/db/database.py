"""
Database connection management for Market Explorer.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

from explorer.config import settings


class Database:
    """Async PostgreSQL database connection pool."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or settings.database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create the connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=2,
                max_size=10,
            )

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._pool

    async def fetch(self, query: str, *args) -> list[dict]:
        """Fetch multiple rows."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch a single row."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetchval(self, query: str, *args):
        """Fetch a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a query."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


# Global database instance
db = Database()


@asynccontextmanager
async def get_db_connection() -> AsyncIterator[Database]:
    """Context manager for database access."""
    yield db
