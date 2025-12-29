"""
FastAPI application for Market Explorer.

Provides REST API endpoints for querying Polymarket data.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from explorer import __version__
from explorer.config import settings
from explorer.db.database import db
from explorer.db.repositories import (
    MarketFilter,
    MarketRepository,
    PaginatedResult,
    SortOrder,
)
from explorer.models.market import Market, MarketStatus


# =============================================================================
# Pydantic Response Schemas
# =============================================================================


class PriceResponse(BaseModel):
    """Price data response schema."""

    yes_price: str
    no_price: Optional[str] = None  # Can be None if not extracted from API
    best_bid: Optional[str] = None
    best_ask: Optional[str] = None
    spread: Optional[str] = None
    mid_price: Optional[str] = None

    class Config:
        from_attributes = True


class LiquidityResponse(BaseModel):
    """Liquidity data response schema."""

    volume_24h: str
    volume_7d: str
    open_interest: str
    liquidity_score: str

    class Config:
        from_attributes = True


class MarketResponse(BaseModel):
    """Market response schema."""

    condition_id: str
    question: str
    market_id: Optional[str] = None
    event_id: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    auto_category: Optional[str] = None
    end_time: Optional[str] = None
    resolved: bool = False
    outcome: Optional[str] = None
    status: str = "active"
    price: Optional[PriceResponse] = None
    liquidity: Optional[LiquidityResponse] = None

    class Config:
        from_attributes = True


class PaginatedMarketsResponse(BaseModel):
    """Paginated markets response."""

    items: list[MarketResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


# =============================================================================
# Conversion Functions
# =============================================================================


def market_to_response(market: Market) -> MarketResponse:
    """Convert a Market domain model to a response schema."""
    price_resp = None
    if market.price:
        # Use 'is not None' to preserve zero values and avoid "None" strings
        price_resp = PriceResponse(
            yes_price=str(market.price.yes_price),
            no_price=str(market.price.no_price) if market.price.no_price is not None else None,
            best_bid=str(market.price.best_bid) if market.price.best_bid is not None else None,
            best_ask=str(market.price.best_ask) if market.price.best_ask is not None else None,
            spread=str(market.price.spread) if market.price.spread is not None else None,
            mid_price=str(market.price.mid_price) if market.price.mid_price is not None else None,
        )

    liquidity_resp = None
    if market.liquidity:
        liquidity_resp = LiquidityResponse(
            volume_24h=str(market.liquidity.volume_24h),
            volume_7d=str(market.liquidity.volume_7d),
            open_interest=str(market.liquidity.open_interest),
            liquidity_score=str(market.liquidity.liquidity_score),
        )

    return MarketResponse(
        condition_id=market.condition_id,
        question=market.question,
        market_id=market.market_id,
        event_id=market.event_id,
        description=market.description,
        category=market.category,
        auto_category=market.auto_category,
        end_time=market.end_time.isoformat() if market.end_time else None,
        resolved=market.resolved,
        outcome=market.outcome,
        status=market.status.value,
        price=price_resp,
        liquidity=liquidity_resp,
    )


# =============================================================================
# FastAPI App
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown."""
    # Startup
    await db.connect()
    set_market_repo(MarketRepository(db))
    yield
    # Shutdown
    await db.disconnect()


app = FastAPI(
    title="Market Explorer API",
    description="Professional Polymarket market explorer dashboard API",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Dependency Injection
# =============================================================================


# Global repository instance (will be set up with real DB in production)
_market_repo: Optional[MarketRepository] = None


def get_market_repo() -> MarketRepository:
    """Get the market repository instance.

    This is a dependency that can be overridden in tests.
    """
    if _market_repo is None:
        raise RuntimeError("Market repository not initialized")
    return _market_repo


def set_market_repo(repo: MarketRepository) -> None:
    """Set the market repository instance."""
    global _market_repo
    _market_repo = repo


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version=__version__)


@app.get("/api/markets", response_model=PaginatedMarketsResponse)
async def list_markets(
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
    categories: Annotated[Optional[str], Query(description="Comma-separated categories")] = None,
    status: Annotated[Optional[str], Query(description="Comma-separated statuses")] = None,
    min_price: Annotated[Optional[float], Query(ge=0, le=1)] = None,
    max_price: Annotated[Optional[float], Query(ge=0, le=1)] = None,
    min_volume_24h: Annotated[Optional[float], Query(ge=0)] = None,
    min_liquidity_score: Annotated[Optional[float], Query(ge=0)] = None,  # No upper cap - liquidity is in dollars
    search: Annotated[Optional[str], Query(min_length=2, max_length=200, description="Search query")] = None,
    resolved: Annotated[Optional[bool], Query()] = None,
    include_closed: Annotated[bool, Query(description="Include closed/resolved markets (default: false to avoid stale data)")] = False,
    sort_by: Annotated[str, Query(description="Sort field")] = "volume_24h",
    sort_desc: Annotated[bool, Query(description="Sort descending")] = True,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, description="Items per page")] = 100,
) -> PaginatedMarketsResponse:
    """List markets with filtering, sorting, and pagination."""
    # Build filter
    # Parse status values with error handling
    status_list = None
    if status:
        try:
            status_list = [MarketStatus(s.strip()) for s in status.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid status value: {e}")

    market_filter = MarketFilter(
        categories=categories.split(",") if categories else None,
        status=status_list,
        min_price=Decimal(str(min_price)) if min_price is not None else None,
        max_price=Decimal(str(max_price)) if max_price is not None else None,
        min_volume_24h=Decimal(str(min_volume_24h)) if min_volume_24h is not None else None,
        min_liquidity_score=Decimal(str(min_liquidity_score)) if min_liquidity_score is not None else None,
        search_query=search,
        resolved=resolved,
        active_only=not include_closed,  # Default to active-only to avoid stale data
    )

    # Build sort
    try:
        sort = SortOrder(field=sort_by, descending=sort_desc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Query repository
    result = await repo.list_markets(
        market_filter=market_filter,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    # Convert to response
    return PaginatedMarketsResponse(
        items=[market_to_response(m) for m in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        has_next=result.has_next,
        has_prev=result.has_prev,
    )


@app.get("/api/markets/search")
async def search_markets(
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
    q: Annotated[str, Query(min_length=1, description="Search query")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[MarketResponse]:
    """Search markets by question text."""
    markets = await repo.search_markets(q, limit=limit)
    return [market_to_response(m) for m in markets]


@app.get("/api/markets/leaders/volume")
async def get_volume_leaders(
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
    category: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[MarketResponse]:
    """Get markets with highest 24h volume."""
    markets = await repo.get_volume_leaders(limit=limit, category=category)
    return [market_to_response(m) for m in markets]


@app.get("/api/markets/{condition_id}", response_model=MarketResponse)
async def get_market_by_id(
    condition_id: str,
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
) -> MarketResponse:
    """Get a market by its condition ID."""
    market = await repo.get_by_id(condition_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Market {condition_id} not found")
    return market_to_response(market)


@app.get("/api/categories")
async def get_categories(
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
    resolved: Annotated[Optional[bool], Query(description="Filter by resolved status")] = None,
    include_closed: Annotated[bool, Query(description="Include closed/resolved markets")] = False,
) -> dict[str, int]:
    """Get all categories with their market counts."""
    return await repo.get_categories(resolved=resolved, active_only=not include_closed)


class CategoryDetailResponse(BaseModel):
    """Detailed category statistics."""

    category: str
    market_count: int
    total_volume_24h: float
    total_liquidity: float
    avg_price: float
    active_markets: int


class PaginatedCategoriesResponse(BaseModel):
    """Paginated categories response."""

    items: list[CategoryDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@app.get("/api/categories/detailed", response_model=PaginatedCategoriesResponse)
async def get_categories_detailed(
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
    include_closed: Annotated[bool, Query(description="Include closed/resolved markets")] = False,
    min_markets: Annotated[int, Query(ge=1, description="Minimum markets per category")] = 1,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, description="Items per page")] = 50,
    search: Annotated[Optional[str], Query(description="Search category names")] = None,
) -> PaginatedCategoriesResponse:
    """Get detailed category stats with volume and liquidity totals.

    Returns categories sorted by total 24h volume descending.
    Supports pagination and search.
    """
    cats = await repo.get_categories_detailed(
        active_only=not include_closed,
        min_markets=min_markets,
    )

    # Filter by search if provided
    if search:
        search_lower = search.lower()
        cats = [c for c in cats if search_lower in c["category"].lower()]

    # Paginate
    total = len(cats)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = cats[start:end]

    return PaginatedCategoriesResponse(
        items=[CategoryDetailResponse(**c) for c in page_items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/events/{event_id}/markets")
async def get_event_markets(
    event_id: str,
    repo: Annotated[MarketRepository, Depends(get_market_repo)],
) -> list[MarketResponse]:
    """Get all markets for an event."""
    markets = await repo.get_by_event_id(event_id)
    return [market_to_response(m) for m in markets]


# =============================================================================
# Events Endpoints (Aggregated View)
# =============================================================================


class EventResponse(BaseModel):
    """Event response with aggregated metrics."""

    event_id: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    volume: float  # Total lifetime volume
    volume_24h: float
    volume_7d: float
    liquidity: float
    market_count: int
    active_market_count: int
    active: bool
    closed: bool


class PaginatedEventsResponse(BaseModel):
    """Paginated events response."""

    items: list[EventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


@app.get("/api/events", response_model=PaginatedEventsResponse)
async def list_events(
    category: Annotated[Optional[str], Query(description="Filter by category")] = None,
    search: Annotated[Optional[str], Query(min_length=2, description="Search event titles")] = None,
    active_only: Annotated[bool, Query(description="Only show active events")] = True,
    min_volume: Annotated[Optional[float], Query(ge=0, description="Minimum total volume")] = None,
    sort_by: Annotated[str, Query(description="Sort field: volume, volume_24h, market_count")] = "volume",
    sort_desc: Annotated[bool, Query(description="Sort descending")] = True,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Items per page")] = 50,
) -> PaginatedEventsResponse:
    """List events with aggregated volume metrics.

    Events group multiple related markets. For example, "2028 Democratic Presidential Nominee"
    contains 128 individual candidate markets with a combined $412M volume.
    """
    # Build query
    conditions = []
    params = []
    param_idx = 1

    if active_only:
        conditions.append("active = true AND closed = false")

    if category:
        conditions.append(f"category ILIKE ${param_idx}")
        params.append(f"%{category}%")
        param_idx += 1

    if search:
        conditions.append(f"title ILIKE ${param_idx}")
        params.append(f"%{search}%")
        param_idx += 1

    if min_volume is not None:
        conditions.append(f"volume >= ${param_idx}")
        params.append(min_volume)
        param_idx += 1

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Validate sort field
    valid_sort_fields = {"volume", "volume_24h", "volume_7d", "market_count", "liquidity", "end_date"}
    if sort_by not in valid_sort_fields:
        sort_by = "volume"

    direction = "DESC" if sort_desc else "ASC"

    # Count total
    count_query = f"SELECT COUNT(*) FROM explorer_events {where_clause}"
    total = await db.fetchval(count_query, *params)
    total = total or 0

    # Calculate pagination
    from math import ceil
    total_pages = max(1, ceil(total / page_size))
    offset = (page - 1) * page_size

    # Main query
    query = f"""
        SELECT event_id, title, slug, description, category, image,
               start_date, end_date, volume, volume_24h, volume_7d,
               liquidity, market_count, active_market_count, active, closed
        FROM explorer_events
        {where_clause}
        ORDER BY {sort_by} {direction} NULLS LAST
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    rows = await db.fetch(query, *params)

    items = [
        EventResponse(
            event_id=row["event_id"],
            title=row["title"],
            slug=row["slug"],
            description=row["description"],
            category=row["category"],
            image=row["image"],
            start_date=row["start_date"].isoformat() if row["start_date"] else None,
            end_date=row["end_date"].isoformat() if row["end_date"] else None,
            volume=float(row["volume"] or 0),
            volume_24h=float(row["volume_24h"] or 0),
            volume_7d=float(row["volume_7d"] or 0),
            liquidity=float(row["liquidity"] or 0),
            market_count=row["market_count"] or 0,
            active_market_count=row["active_market_count"] or 0,
            active=row["active"],
            closed=row["closed"],
        )
        for row in rows
    ]

    return PaginatedEventsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@app.get("/api/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: str) -> EventResponse:
    """Get a single event by ID."""
    query = """
        SELECT event_id, title, slug, description, category, image,
               start_date, end_date, volume, volume_24h, volume_7d,
               liquidity, market_count, active_market_count, active, closed
        FROM explorer_events
        WHERE event_id = $1
    """
    row = await db.fetchrow(query, event_id)

    if row is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    return EventResponse(
        event_id=row["event_id"],
        title=row["title"],
        slug=row["slug"],
        description=row["description"],
        category=row["category"],
        image=row["image"],
        start_date=row["start_date"].isoformat() if row["start_date"] else None,
        end_date=row["end_date"].isoformat() if row["end_date"] else None,
        volume=float(row["volume"] or 0),
        volume_24h=float(row["volume_24h"] or 0),
        volume_7d=float(row["volume_7d"] or 0),
        liquidity=float(row["liquidity"] or 0),
        market_count=row["market_count"] or 0,
        active_market_count=row["active_market_count"] or 0,
        active=row["active"],
        closed=row["closed"],
    )


class SyncStatusResponse(BaseModel):
    """Sync status response."""

    job_name: str
    status: str
    health_status: str
    last_run: Optional[str] = None
    seconds_since_run: Optional[int] = None
    rows_upserted: Optional[int] = None
    error_message: Optional[str] = None


class SyncHealthResponse(BaseModel):
    """Overall sync health response."""

    overall_status: str
    jobs: list[SyncStatusResponse]
    is_healthy: bool


@app.get("/api/sync/status", response_model=SyncHealthResponse)
async def get_sync_status() -> SyncHealthResponse:
    """Get sync service health status.

    Returns the status of all sync jobs and overall health.
    Health statuses:
    - healthy: Last sync within 2 minutes
    - warning: Last sync 2-10 minutes ago
    - stale: Last sync over 10 minutes ago
    - error: Last sync failed
    - syncing: Sync currently running
    """
    try:
        # Query sync status from database
        query = """
            SELECT DISTINCT ON (job_name)
                job_name,
                status,
                started_at,
                finished_at,
                duration_ms,
                rows_upserted,
                rows_failed,
                error_message,
                EXTRACT(EPOCH FROM (NOW() - COALESCE(finished_at, started_at)))::INT AS seconds_since_run,
                CASE
                    WHEN status = 'running' THEN 'syncing'
                    WHEN status = 'failed' THEN 'error'
                    WHEN EXTRACT(EPOCH FROM (NOW() - finished_at)) > 600 THEN 'stale'
                    WHEN EXTRACT(EPOCH FROM (NOW() - finished_at)) > 120 THEN 'warning'
                    ELSE 'healthy'
                END AS health_status
            FROM explorer_sync_runs
            ORDER BY job_name, started_at DESC
        """

        rows = await db.fetch(query)

        jobs = []
        has_error = False
        has_stale = False

        for row in rows:
            health = row["health_status"]
            if health == "error":
                has_error = True
            elif health == "stale":
                has_stale = True

            jobs.append(SyncStatusResponse(
                job_name=row["job_name"],
                status=row["status"],
                health_status=health,
                last_run=row["finished_at"].isoformat() if row["finished_at"] else None,
                seconds_since_run=row["seconds_since_run"],
                rows_upserted=row["rows_upserted"],
                error_message=row["error_message"],
            ))

        # Determine overall status
        if has_error:
            overall_status = "error"
        elif has_stale:
            overall_status = "stale"
        elif not jobs:
            overall_status = "no_data"
        else:
            overall_status = "healthy"

        return SyncHealthResponse(
            overall_status=overall_status,
            jobs=jobs,
            is_healthy=overall_status == "healthy",
        )

    except Exception as e:
        # Table might not exist yet
        return SyncHealthResponse(
            overall_status="unknown",
            jobs=[],
            is_healthy=False,
        )
