"""
Repository layer for Market Explorer.

Implements the repository pattern for clean data access abstraction.
Repositories translate between database rows and domain models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from typing import Any, Generic, Optional, Protocol, Sequence, TypeVar

from explorer.models.market import (
    Market,
    MarketStatus,
    PriceData,
    LiquidityData,
)


class AsyncDatabase(Protocol):
    """Protocol for async database connections."""

    async def fetch(self, query: str, *args: Any) -> Sequence[dict[str, Any]]:
        """Fetch multiple rows."""
        ...

    async def fetchrow(self, query: str, *args: Any) -> Optional[dict[str, Any]]:
        """Fetch a single row."""
        ...

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Fetch a single value."""
        ...

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query."""
        ...


@dataclass
class MarketFilter:
    """Filter criteria for market queries."""

    categories: Optional[list[str]] = None
    status: Optional[list[MarketStatus]] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_volume_24h: Optional[Decimal] = None
    min_liquidity_score: Optional[Decimal] = None
    search_query: Optional[str] = None
    resolved: Optional[bool] = None
    tags: Optional[list[str]] = None
    min_time_to_expiry_hours: Optional[int] = None
    max_time_to_expiry_hours: Optional[int] = None
    # By default, only show active markets to avoid stale data issues
    # Set to False to include closed/resolved markets
    active_only: bool = True


@dataclass
class SortOrder:
    """Sort configuration for queries."""

    field: str = "volume_24h"
    descending: bool = True

    # Valid fields that can be sorted (must exist as DB columns)
    VALID_FIELDS = frozenset([
        "volume_24h",
        "volume_7d",
        "volume_num",      # Total/lifetime volume
        "open_interest",
        "liquidity_score",
        "yes_price",
        "spread",          # Best ask - best bid
        "end_time",
        "created_at",
        "updated_at",
    ])

    def __post_init__(self) -> None:
        """Validate sort field to prevent SQL injection."""
        if self.field not in self.VALID_FIELDS:
            raise ValueError(
                f"Invalid sort field: {self.field}. "
                f"Valid fields: {self.VALID_FIELDS}"
            )


T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """Paginated query result with metadata."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


def _row_to_market(row: dict[str, Any]) -> Market:
    """Convert a database row to a Market domain model."""
    # Parse status
    status_str = row.get("status", "active")
    try:
        status = MarketStatus(status_str)
    except ValueError:
        status = MarketStatus.ACTIVE

    # Build PriceData if prices exist
    price = None
    if row.get("yes_price") is not None:
        # Use 'is not None' to preserve zero values
        best_bid = row.get("best_bid")
        best_ask = row.get("best_ask")
        no_price = row.get("no_price")
        price = PriceData(
            yes_price=Decimal(str(row["yes_price"])),
            no_price=Decimal(str(no_price)) if no_price is not None else None,
            best_bid=Decimal(str(best_bid)) if best_bid is not None else None,
            best_ask=Decimal(str(best_ask)) if best_ask is not None else None,
        )

    # Build LiquidityData if ANY liquidity metrics exist (not just volume_24h)
    liquidity = None
    volume_24h = row.get("volume_24h")
    volume_7d = row.get("volume_7d")
    open_interest = row.get("open_interest")
    liquidity_score = row.get("liquidity_score")

    # Check if any liquidity field has data
    if any(v is not None for v in [volume_24h, volume_7d, open_interest, liquidity_score]):
        liquidity = LiquidityData(
            volume_24h=Decimal(str(volume_24h)) if volume_24h is not None else Decimal("0"),
            volume_7d=Decimal(str(volume_7d)) if volume_7d is not None else Decimal("0"),
            open_interest=Decimal(str(open_interest)) if open_interest is not None else Decimal("0"),
            liquidity_score=Decimal(str(liquidity_score)) if liquidity_score is not None else Decimal("0"),
        )

    return Market(
        condition_id=row["condition_id"],
        question=row["question"],
        market_id=row.get("market_id"),
        event_id=row.get("event_id"),
        description=row.get("description"),
        category=row.get("category"),
        auto_category=row.get("auto_category"),
        end_time=row.get("end_time"),
        resolution_time=row.get("resolution_time"),
        resolved=row.get("resolved", False),
        outcome=row.get("outcome"),
        status=status,
        price=price,
        liquidity=liquidity,
    )


class MarketRepository:
    """Repository for Market entities.

    Handles all database operations for markets with filtering,
    pagination, and sorting support.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Initialize with a database connection."""
        self._db = db

    async def get_by_id(self, condition_id: str) -> Optional[Market]:
        """Get a market by its condition ID.

        Args:
            condition_id: The unique condition identifier

        Returns:
            Market if found, None otherwise
        """
        query = """
            SELECT *
            FROM explorer_markets
            WHERE condition_id = $1
        """
        row = await self._db.fetchrow(query, condition_id)
        if row is None:
            return None
        return _row_to_market(dict(row))

    async def list_markets(
        self,
        market_filter: Optional[MarketFilter] = None,
        sort: Optional[SortOrder] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult[Market]:
        """List markets with filtering, sorting, and pagination.

        Args:
            market_filter: Optional filter criteria
            sort: Optional sort order (default: volume_24h DESC)
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            PaginatedResult containing markets and metadata

        Raises:
            ValueError: If page < 1 or page_size not in valid range
        """
        # Validate pagination parameters
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")
        if page_size < 1 or page_size > 500:
            raise ValueError(f"page_size must be between 1 and 500, got {page_size}")

        if sort is None:
            sort = SortOrder()

        # Use market_filter to avoid shadowing builtin
        filter = market_filter

        # Build WHERE clause
        conditions: list[str] = []
        params: list[Any] = []
        param_idx = 1

        # Default: filter to active markets only (to avoid stale data)
        if filter is None or filter.active_only:
            conditions.append("(status = 'active' AND (active = true OR active IS NULL))")

        if filter:
            if filter.categories:
                conditions.append(f"category = ANY(${param_idx})")
                params.append(filter.categories)
                param_idx += 1

            if filter.status:
                status_values = [s.value for s in filter.status]
                conditions.append(f"status = ANY(${param_idx})")
                params.append(status_values)
                param_idx += 1

            if filter.min_price is not None:
                conditions.append(f"yes_price >= ${param_idx}")
                params.append(filter.min_price)
                param_idx += 1

            if filter.max_price is not None:
                conditions.append(f"yes_price <= ${param_idx}")
                params.append(filter.max_price)
                param_idx += 1

            if filter.min_volume_24h is not None:
                conditions.append(f"volume_24h >= ${param_idx}")
                params.append(filter.min_volume_24h)
                param_idx += 1

            if filter.min_liquidity_score is not None:
                conditions.append(f"liquidity_score >= ${param_idx}")
                params.append(filter.min_liquidity_score)
                param_idx += 1

            if filter.search_query:
                conditions.append(f"question ILIKE ${param_idx}")
                params.append(f"%{filter.search_query}%")
                param_idx += 1

            if filter.resolved is not None:
                conditions.append(f"resolved = ${param_idx}")
                params.append(filter.resolved)
                param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Sort direction
        direction = "DESC" if sort.descending else "ASC"

        # Count total
        count_query = f"""
            SELECT COUNT(*)
            FROM explorer_markets
            {where_clause}
        """
        total = await self._db.fetchval(count_query, *params)
        total = total or 0

        # Calculate pagination
        total_pages = max(1, ceil(total / page_size))
        offset = (page - 1) * page_size

        # Main query - NULLS LAST ensures null values sort to end regardless of direction
        query = f"""
            SELECT *
            FROM explorer_markets
            {where_clause}
            ORDER BY {sort.field} {direction} NULLS LAST
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        rows = await self._db.fetch(query, *params)
        markets = [_row_to_market(dict(row)) for row in rows]

        return PaginatedResult(
            items=markets,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_categories(
        self,
        resolved: Optional[bool] = None,
        active_only: bool = True,
    ) -> dict[str, int]:
        """Get all categories with their market counts.

        Args:
            resolved: If provided, filter by resolved status
            active_only: If True, only count active markets (default: True)

        Returns:
            Dict mapping category name to count
        """
        conditions = ["category IS NOT NULL"]
        params = []
        param_idx = 1

        if active_only:
            conditions.append("(status = 'active' AND (active = true OR active IS NULL))")

        if resolved is not None:
            conditions.append(f"resolved = ${param_idx}")
            params.append(resolved)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT category, COUNT(*) as count
            FROM explorer_markets
            WHERE {where_clause}
            GROUP BY category
            ORDER BY count DESC
        """
        rows = await self._db.fetch(query, *params)
        return {row["category"]: row["count"] for row in rows}

    async def get_categories_detailed(
        self,
        active_only: bool = True,
        min_markets: int = 1,
    ) -> list[dict]:
        """Get detailed category stats including volume and liquidity.

        Args:
            active_only: If True, only count active markets
            min_markets: Minimum number of markets to include category

        Returns:
            List of category stats dicts
        """
        active_filter = ""
        if active_only:
            active_filter = "AND (status = 'active' AND (active = true OR active IS NULL))"

        query = f"""
            SELECT
                category,
                COUNT(*) as market_count,
                COALESCE(SUM(volume_24h), 0) as total_volume_24h,
                COALESCE(SUM(liquidity_score), 0) as total_liquidity,
                COALESCE(AVG(yes_price), 0) as avg_price,
                COUNT(*) FILTER (WHERE volume_24h > 0) as active_markets
            FROM explorer_markets
            WHERE category IS NOT NULL {active_filter}
            GROUP BY category
            HAVING COUNT(*) >= $1
            ORDER BY COALESCE(SUM(volume_24h), 0) DESC
        """
        rows = await self._db.fetch(query, min_markets)
        return [
            {
                "category": row["category"],
                "market_count": row["market_count"],
                "total_volume_24h": float(row["total_volume_24h"] or 0),
                "total_liquidity": float(row["total_liquidity"] or 0),
                "avg_price": float(row["avg_price"] or 0),
                "active_markets": row["active_markets"],
            }
            for row in rows
        ]

    async def search_markets(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Market]:
        """Search markets by question text.

        Args:
            query: Search query string
            limit: Maximum results to return

        Returns:
            List of matching markets
        """
        sql = """
            SELECT *
            FROM explorer_markets
            WHERE question ILIKE $1
               OR description ILIKE $1
            ORDER BY volume_24h DESC
            LIMIT $2
        """
        rows = await self._db.fetch(sql, f"%{query}%", limit)
        return [_row_to_market(dict(row)) for row in rows]

    async def get_volume_leaders(
        self,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[Market]:
        """Get markets with highest 24h volume.

        Args:
            limit: Number of markets to return
            category: Optional category filter

        Returns:
            List of top volume markets
        """
        if category:
            query = """
                SELECT *
                FROM explorer_markets
                WHERE category = $1 AND resolved = FALSE
                ORDER BY volume_24h DESC
                LIMIT $2
            """
            rows = await self._db.fetch(query, category, limit)
        else:
            query = """
                SELECT *
                FROM explorer_markets
                WHERE resolved = FALSE
                ORDER BY volume_24h DESC
                LIMIT $1
            """
            rows = await self._db.fetch(query, limit)

        return [_row_to_market(dict(row)) for row in rows]

    async def get_by_event_id(self, event_id: str) -> list[Market]:
        """Get all markets belonging to an event.

        Args:
            event_id: The event identifier

        Returns:
            List of markets in the event
        """
        query = """
            SELECT *
            FROM explorer_markets
            WHERE event_id = $1
            ORDER BY volume_24h DESC
        """
        rows = await self._db.fetch(query, event_id)
        return [_row_to_market(dict(row)) for row in rows]

    async def get_expiring_soon(
        self,
        hours: int = 24,
        limit: int = 20,
    ) -> list[Market]:
        """Get markets expiring within specified hours.

        Args:
            hours: Hours until expiration
            limit: Maximum markets to return

        Returns:
            List of soon-to-expire markets
        """
        # Use interval arithmetic with parameterized hours
        # $1 * interval '1 hour' correctly multiplies the parameter
        query = """
            SELECT *
            FROM explorer_markets
            WHERE end_time IS NOT NULL
              AND end_time <= NOW() + ($1 * INTERVAL '1 hour')
              AND end_time > NOW()
              AND resolved = FALSE
            ORDER BY end_time ASC
            LIMIT $2
        """
        rows = await self._db.fetch(query, hours, limit)
        return [_row_to_market(dict(row)) for row in rows]
