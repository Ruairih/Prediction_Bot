# Polymarket Market Explorer

A professional, read-only dashboard for discovering, analyzing, and monitoring Polymarket prediction markets.

## Overview

Market Explorer provides a dense, professional interface for viewing all Polymarket markets. Unlike the trading bot dashboard (which monitors bot activity and positions), this tool is focused purely on **market discovery and analysis**.

### Features

- **Dense Market Screener**: View 1000+ markets with virtualized scrolling
- **Advanced Filtering**: Filter by category, price range, volume, liquidity, status
- **Real-time Updates**: Automatic refresh with React Query
- **Market Detail View**: Deep-dive into individual markets
- **Watchlists**: Save markets for quick access (coming soon)
- **Alerts**: Get notified on price/spread changes (coming soon)

## Architecture

```
market-explorer/
├── backend/           # FastAPI backend
│   ├── src/explorer/
│   │   ├── api/       # REST endpoints
│   │   ├── db/        # Repository layer
│   │   ├── models/    # Domain models
│   │   └── services/  # Background sync service
│   ├── sync_markets_v2.py  # Market data sync script
│   └── tests/         # TDD tests (80+ passing)
├── frontend/          # React + TanStack frontend
│   └── src/
│       ├── components/   # Reusable UI components
│       ├── pages/        # Page components
│       ├── hooks/        # React Query hooks
│       └── api/          # API client
├── shared/
│   └── migrations/    # Database schema
├── scripts/           # Utility scripts
│   └── refresh_markets.sh  # Sync script wrapper
└── docker-compose.yml # Container orchestration
```

## Tech Stack

### Backend
- **FastAPI** - Modern async Python API framework
- **PostgreSQL** - Primary database
- **asyncpg** - Async PostgreSQL driver
- **Pydantic** - Data validation

### Frontend
- **React 18** - UI framework
- **TanStack Table** - Virtualized, sortable tables
- **TanStack Query** - Server state management
- **Tailwind CSS** - Utility-first styling
- **Vite** - Fast build tool

## Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+

### Backend Setup

```bash
cd market-explorer/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ -v

# Start server
uvicorn explorer.api.main:app --reload --port 8080
```

### Frontend Setup

```bash
cd market-explorer/frontend

# Install dependencies
npm install

# Start dev server
npm run dev

# Runs at http://localhost:3004 (configured in vite.config.ts)

# Build for production
npm run build
```

### Database Setup

```bash
# Apply migrations
psql -d your_database -f shared/migrations/001_explorer_schema.sql
psql -d your_database -f shared/migrations/002_fix_liquidity_precision.sql
psql -d your_database -f shared/migrations/003_sync_status_tracking.sql
psql -d your_database -f shared/migrations/004_cleanup_stale_markets.sql
```

### Data Sync

Market data is synced from the Polymarket Gamma API:

```bash
# One-time sync (all active markets)
cd backend && python sync_markets_v2.py --active-only

# Full refresh with cleanup
./scripts/refresh_markets.sh
```

**Background Sync Service**: For production, run the sync service which provides:
- Full sync every 5 minutes
- Price updates every 30 seconds
- PostgreSQL advisory locks to prevent concurrent runs
- Status tracking in `explorer_sync_runs` table

```bash
# Run sync service
python -m explorer.services.sync_service
```

### Docker Deployment

```bash
# Start all services (API, sync service, frontend, postgres)
docker-compose up -d

# View logs
docker-compose logs -f explorer-sync
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/markets` | GET | List markets with filtering |
| `/api/markets/{id}` | GET | Get market by ID |
| `/api/markets/search` | GET | Search markets |
| `/api/markets/leaders/volume` | GET | Top volume markets |
| `/api/categories` | GET | Get categories with counts |
| `/api/events/{id}/markets` | GET | Get event markets |
| `/api/sync/status` | GET | Sync service health status |

### Query Parameters for `/api/markets`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `categories` | string | - | Comma-separated categories |
| `status` | string | - | Comma-separated statuses |
| `min_price` | float | - | Minimum YES price (0-1) |
| `max_price` | float | - | Maximum YES price (0-1) |
| `min_volume_24h` | float | - | Minimum 24h volume |
| `min_liquidity_score` | float | - | Minimum liquidity score (USD) |
| `search` | string | - | Search query |
| `resolved` | bool | - | Filter by resolved status |
| `include_closed` | bool | false | Include closed/resolved markets |
| `sort_by` | string | volume_24h | Sort field |
| `sort_desc` | bool | true | Sort descending |
| `page` | int | 1 | Page number |
| `page_size` | int | 100 | Items per page (max 500) |

> **Note**: By default, only active markets are returned to avoid stale data from resolved markets. Set `include_closed=true` to include historical data.

## Relationship to Trading Bot

This Market Explorer is **standalone** but can share data with the trading bot:

- **Same PostgreSQL instance** - Uses separate `explorer_*` tables
- **Shared ingestion** - Can consume data from bot's ingestion pipeline
- **Read-only** - No trading functionality for safety

## Testing

The project follows TDD (Test-Driven Development):

```bash
# Run all tests
cd backend && pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/explorer --cov-report=html
```

Current test coverage:
- Models: 45 tests
- Repositories: 18 tests
- API: 17 tests
- **Total: 80 tests passing**

## Known Issues & Gotchas

### Stale Data in Resolved Markets
Resolved/closed markets retain their last liquidity values, which can cause incorrect sorting if included. The API defaults to `include_closed=false` to prevent this.

### Event vs Market Liquidity
Polymarket's homepage shows **event-level** liquidity (aggregated across all markets in an event), while this dashboard shows **market-level** liquidity (individual market orderbook depth). For example:
- Event "Bitcoin prices 2025" = $5.7M (30 markets combined)
- Market "Bitcoin $200K" = $650K (individual market)

### Event ID Extraction
The Polymarket API returns event info in `events[0].id`, not a flat `eventId` field. The sync script handles this correctly.

## License

Private - Internal use only

## Contributing

Developed with TDD and reviewed by Claude at each step.
