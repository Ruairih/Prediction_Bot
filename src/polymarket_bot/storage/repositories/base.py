"""
Base repository class for async PostgreSQL access.
"""
from __future__ import annotations

from typing import Generic, Optional, Type, TypeVar

from pydantic import BaseModel

from polymarket_bot.storage.database import Database

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """
    Base class for async repositories.

    Provides common patterns for CRUD operations.
    Subclasses define table name and model type.
    """

    table_name: str
    model_class: Type[T]

    def __init__(self, db: Database) -> None:
        self.db = db

    def _record_to_model(self, record) -> T:
        """Convert asyncpg Record to Pydantic model."""
        if record is None:
            return None
        return self.model_class(**dict(record))

    def _records_to_models(self, records) -> list[T]:
        """Convert list of Records to list of models."""
        return [self._record_to_model(r) for r in records]

    async def get_by_id(self, id_value, id_column: str = "id") -> Optional[T]:
        """Get a single record by ID."""
        query = f"SELECT * FROM {self.table_name} WHERE {id_column} = $1"
        record = await self.db.fetchrow(query, id_value)
        return self._record_to_model(record)

    async def exists(self, id_value, id_column: str = "id") -> bool:
        """Check if record exists."""
        query = f"SELECT 1 FROM {self.table_name} WHERE {id_column} = $1"
        result = await self.db.fetchval(query, id_value)
        return result is not None

    async def delete(self, id_value, id_column: str = "id") -> bool:
        """Delete a record by ID. Returns True if deleted."""
        query = f"DELETE FROM {self.table_name} WHERE {id_column} = $1"
        result = await self.db.execute(query, id_value)
        return result != "DELETE 0"

    async def count(self) -> int:
        """Count all records in table."""
        query = f"SELECT COUNT(*) FROM {self.table_name}"
        return await self.db.fetchval(query)
