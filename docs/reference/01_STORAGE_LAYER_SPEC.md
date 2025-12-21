# Storage Layer Specification

## Overview

The Storage Layer provides all data persistence for the trading bot. It is the foundation that all other layers depend on.

**Responsibilities:**
- SQLite database connection management
- Schema definition and migrations
- Repository pattern for data access
- Transaction management

**Does NOT:**
- Make trading decisions
- Call external APIs
- Contain business logic

---

## Directory Structure

```
src/polymarket_bot/storage/
├── CLAUDE.md                    # Component AI context
├── __init__.py                  # Public exports
├── database.py                  # Connection management
├── migrations.py                # Schema versioning
├── schema.sql                   # Full schema definition
├── repositories/
│   ├── __init__.py
│   ├── base.py                  # Base repository class
│   ├── market_repo.py           # Markets and tokens
│   ├── trade_repo.py            # Historical trades
│   ├── trigger_repo.py          # First-hit triggers
│   ├── order_repo.py            # Live orders
│   ├── position_repo.py         # Positions
│   └── watchlist_repo.py        # Strategy watchlists
└── tests/
    ├── __init__.py
    ├── conftest.py              # Fixtures
    ├── test_database.py
    ├── test_migrations.py
    └── test_repositories.py
```

---

## 1. Database Connection Management

### `database.py`

```python
"""
Database connection management.

Provides a thread-safe connection pool for SQLite with:
- Connection pooling
- Transaction context managers
- Health checking
- Automatic schema migrations on startup
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    """Database configuration."""
    path: Path
    timeout: float = 30.0
    check_same_thread: bool = False
    isolation_level: Optional[str] = None  # Autocommit mode
    journal_mode: str = "WAL"  # Write-Ahead Logging for concurrency
    synchronous: str = "NORMAL"  # Balance safety vs performance
    foreign_keys: bool = True


class Database:
    """
    Thread-safe SQLite database connection manager.

    Usage:
        db = Database(DatabaseConfig(path=Path("data/trading.db")))
        db.initialize()  # Run migrations

        with db.connection() as conn:
            rows = conn.execute("SELECT * FROM markets").fetchall()

        with db.transaction() as conn:
            conn.execute("INSERT INTO markets ...")
            # Auto-commits on success, rollbacks on exception
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self._local = threading.local()
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection, creating if needed."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.config.path),
                timeout=self.config.timeout,
                check_same_thread=self.config.check_same_thread,
                isolation_level=self.config.isolation_level,
            )
            conn.row_factory = sqlite3.Row

            # Apply pragmas
            conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
            conn.execute(f"PRAGMA synchronous = {self.config.synchronous}")
            if self.config.foreign_keys:
                conn.execute("PRAGMA foreign_keys = ON")

            self._local.connection = conn

        return self._local.connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get a connection for read operations."""
        yield self._get_connection()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Get a connection with automatic transaction management.

        Commits on successful exit, rolls back on exception.
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def initialize(self) -> None:
        """Initialize database: create directory, run migrations."""
        if self._initialized:
            return

        # Ensure directory exists
        self.config.path.parent.mkdir(parents=True, exist_ok=True)

        # Run migrations
        from .migrations import run_migrations
        with self.connection() as conn:
            run_migrations(conn)

        self._initialized = True

    def health_check(self) -> bool:
        """Check if database is accessible."""
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close thread-local connection if open."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
```

### Tests for `database.py`

```python
# tests/test_database.py

import pytest
import threading
from pathlib import Path
from polymarket_bot.storage.database import Database, DatabaseConfig


@pytest.fixture
def db_config(tmp_path: Path) -> DatabaseConfig:
    """Create config with temp database path."""
    return DatabaseConfig(path=tmp_path / "test.db")


@pytest.fixture
def db(db_config: DatabaseConfig) -> Database:
    """Create initialized database."""
    database = Database(db_config)
    database.initialize()
    return database


class TestDatabaseConnection:
    def test_creates_database_file(self, db_config: DatabaseConfig) -> None:
        """Database file should be created on initialize."""
        db = Database(db_config)
        assert not db_config.path.exists()
        db.initialize()
        assert db_config.path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        config = DatabaseConfig(path=tmp_path / "nested" / "dir" / "test.db")
        db = Database(config)
        db.initialize()
        assert config.path.exists()

    def test_connection_returns_row_factory(self, db: Database) -> None:
        """Connections should return Row objects, not tuples."""
        with db.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO test VALUES (1, 'foo')")
            row = conn.execute("SELECT * FROM test").fetchone()

        assert row["id"] == 1
        assert row["name"] == "foo"


class TestDatabaseTransaction:
    def test_commits_on_success(self, db: Database) -> None:
        """Transaction should commit on successful exit."""
        with db.transaction() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (1)")

        # Verify data persisted
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM test").fetchone()
        assert row["id"] == 1

    def test_rollback_on_exception(self, db: Database) -> None:
        """Transaction should rollback on exception."""
        with db.transaction() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")

        with pytest.raises(ValueError):
            with db.transaction() as conn:
                conn.execute("INSERT INTO test VALUES (1)")
                raise ValueError("Test error")

        # Verify data was rolled back
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM test").fetchone()
        assert row is None


class TestDatabaseThreadSafety:
    def test_separate_connections_per_thread(self, db: Database) -> None:
        """Each thread should get its own connection."""
        connections = []

        def get_conn():
            with db.connection() as conn:
                connections.append(id(conn))

        threads = [threading.Thread(target=get_conn) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All connections should be different
        assert len(set(connections)) == 3


class TestDatabaseHealthCheck:
    def test_health_check_returns_true_when_healthy(self, db: Database) -> None:
        """Health check should return True for working database."""
        assert db.health_check() is True

    def test_health_check_returns_false_when_broken(self, tmp_path: Path) -> None:
        """Health check should return False if database is inaccessible."""
        config = DatabaseConfig(path=tmp_path / "nonexistent" / "db.sqlite")
        db = Database(config)
        # Don't initialize - database doesn't exist
        assert db.health_check() is False
```

---

## 2. Schema and Migrations

### `schema.sql`

```sql
-- ============================================================
-- POLYMARKET TRADING BOT - DATABASE SCHEMA
-- ============================================================
-- Version: 1
-- This file is the source of truth for the database schema.
-- Migrations are generated from changes to this file.
-- ============================================================

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

-- ============================================================
-- MARKET DATA
-- ============================================================

-- Markets (condition_id is the primary identifier)
CREATE TABLE IF NOT EXISTS markets (
    condition_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,
    slug TEXT,

    -- Timing
    created_at_polymarket TEXT,  -- When Polymarket created it
    scheduled_end TEXT,          -- Expected end date
    resolved_at TEXT,            -- Actual resolution time

    -- Resolution
    is_resolved INTEGER DEFAULT 0,
    resolution_price REAL,       -- 1.0 for YES, 0.0 for NO

    -- Metadata
    volume REAL,
    liquidity REAL,

    -- Our tracking
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_markets_resolved ON markets(is_resolved);
CREATE INDEX IF NOT EXISTS idx_markets_end ON markets(scheduled_end);


-- Tokens (YES/NO tokens for each market)
CREATE TABLE IF NOT EXISTS tokens (
    token_id TEXT PRIMARY KEY,
    condition_id TEXT NOT NULL REFERENCES markets(condition_id),
    market_id TEXT,              -- Polymarket's market_id (may differ from condition_id)

    -- Token details
    outcome TEXT NOT NULL,       -- 'Yes', 'No', 'Over', 'Under', etc.
    outcome_index INTEGER,       -- 0 or 1 typically

    -- Tracking
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tokens_condition ON tokens(condition_id);
CREATE INDEX IF NOT EXISTS idx_tokens_market ON tokens(market_id);


-- ============================================================
-- TRADE DATA
-- ============================================================

-- Historical trades (for backtesting and feature computation)
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,

    -- Trade details
    price REAL NOT NULL,
    size REAL NOT NULL,
    side TEXT NOT NULL,          -- 'buy' or 'sell'
    timestamp INTEGER NOT NULL,  -- Unix timestamp

    -- Deduplication
    trade_hash TEXT UNIQUE,      -- Hash of (token_id, timestamp, price, size)

    -- Tracking
    ingested_at TEXT DEFAULT (datetime('now'))
);

-- CRITICAL: Index on token_id + timestamp for feature queries
CREATE INDEX IF NOT EXISTS idx_trades_token_ts ON trades(token_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);


-- ============================================================
-- TRIGGER TRACKING
-- ============================================================

-- First-hit triggers (when price first crosses threshold)
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,

    -- Trigger details
    threshold REAL NOT NULL,      -- e.g., 0.95
    price REAL NOT NULL,          -- Actual trigger price
    size REAL,                    -- Trade size that triggered
    timestamp INTEGER NOT NULL,   -- When triggered

    -- Strategy decision
    strategy_name TEXT,           -- Which strategy processed this
    signal_type TEXT,             -- 'execute', 'watchlist', 'reject'
    signal_reason TEXT,           -- Why this decision

    -- Model scoring (strategy-specific)
    model_score REAL,
    model_version TEXT,

    -- Filter results
    passed_filters INTEGER DEFAULT 1,
    filter_failures TEXT,         -- JSON array of failed filters

    -- Tracking
    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(token_id, threshold)
);

CREATE INDEX IF NOT EXISTS idx_triggers_condition ON triggers(condition_id, threshold);
CREATE INDEX IF NOT EXISTS idx_triggers_timestamp ON triggers(timestamp);
CREATE INDEX IF NOT EXISTS idx_triggers_strategy ON triggers(strategy_name);


-- ============================================================
-- WATCHLIST (Deferred Trading Decisions)
-- ============================================================

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT NOT NULL UNIQUE,
    condition_id TEXT NOT NULL,

    -- Original trigger
    trigger_price REAL NOT NULL,
    trigger_size REAL,
    trigger_timestamp INTEGER NOT NULL,

    -- Strategy info
    strategy_name TEXT NOT NULL,

    -- Scoring
    initial_score REAL NOT NULL,
    current_score REAL,
    score_history TEXT,           -- JSON array of {timestamp, score}

    -- Context
    question TEXT,
    time_to_end_hours REAL,

    -- Status
    status TEXT DEFAULT 'watching',  -- 'watching', 'promoted', 'expired', 'rejected'
    status_reason TEXT,

    -- Tracking
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status);
CREATE INDEX IF NOT EXISTS idx_watchlist_strategy ON watchlist(strategy_name);


-- ============================================================
-- ORDERS
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Polymarket identifiers
    order_id TEXT UNIQUE,         -- Polymarket's order ID

    -- What we're trading
    token_id TEXT NOT NULL,
    condition_id TEXT,
    trigger_id INTEGER REFERENCES triggers(id),

    -- Order parameters
    side TEXT NOT NULL,           -- 'buy' or 'sell'
    order_price REAL NOT NULL,
    order_size REAL NOT NULL,
    order_type TEXT DEFAULT 'GTC', -- GTC, FOK, etc.

    -- Fill info
    fill_price REAL,
    fill_size REAL,

    -- Status
    status TEXT NOT NULL,         -- 'pending', 'submitted', 'filled', 'partial',
                                  -- 'cancelled', 'rejected', 'error'
    status_reason TEXT,

    -- Strategy info
    strategy_name TEXT,

    -- Timing
    submitted_at TEXT,
    filled_at TEXT,

    -- Tracking
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_token ON orders(token_id);
CREATE INDEX IF NOT EXISTS idx_orders_condition ON orders(condition_id);


-- ============================================================
-- POSITIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- What we hold
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,

    -- Entry details
    entry_order_id INTEGER REFERENCES orders(id),
    entry_price REAL NOT NULL,
    shares REAL NOT NULL,
    entry_time TEXT NOT NULL,

    -- Exit details (filled when closed)
    exit_order_id INTEGER REFERENCES orders(id),
    exit_price REAL,
    exit_time TEXT,
    exit_type TEXT,               -- 'resolution', 'profit_target', 'stop_loss', 'manual'

    -- P&L
    realized_pnl REAL,
    fees_paid REAL DEFAULT 0,

    -- Status
    status TEXT NOT NULL,         -- 'open', 'closed'

    -- Strategy info
    strategy_name TEXT,

    -- Tracking
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_token ON positions(token_id);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions(strategy_name);


-- ============================================================
-- EXIT EVENTS (Audit Trail)
-- ============================================================

CREATE TABLE IF NOT EXISTS exit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES positions(id),

    -- What happened
    exit_type TEXT NOT NULL,      -- 'resolution', 'profit_target', 'stop_loss', 'manual'
    trigger_price REAL,           -- Price that triggered exit
    exit_price REAL,              -- Actual exit price

    -- Result
    gross_pnl REAL,
    fees REAL,
    net_pnl REAL,

    -- Tracking
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exit_events_position ON exit_events(position_id);
CREATE INDEX IF NOT EXISTS idx_exit_events_type ON exit_events(exit_type);


-- ============================================================
-- SERVICE HEALTH
-- ============================================================

CREATE TABLE IF NOT EXISTS service_health (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,         -- 'healthy', 'degraded', 'unhealthy'
    last_check TEXT NOT NULL,
    last_success TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    error_message TEXT,
    metadata TEXT                 -- JSON with service-specific info
);
```

### `migrations.py`

```python
"""
Database migration management.

Migrations are defined as SQL statements that transform the schema
from one version to the next. Each migration has:
- version: Incrementing integer
- description: Human-readable description
- up_sql: SQL to apply migration
- down_sql: SQL to revert migration (optional)
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@dataclass
class Migration:
    """A single migration step."""
    version: int
    description: str
    up_sql: str
    down_sql: Optional[str] = None


# Define migrations as incremental changes
# Version 1 is the initial schema
MIGRATIONS: List[Migration] = [
    Migration(
        version=1,
        description="Initial schema",
        up_sql=SCHEMA_PATH.read_text() if SCHEMA_PATH.exists() else "",
    ),
    # Future migrations go here:
    # Migration(
    #     version=2,
    #     description="Add column X to table Y",
    #     up_sql="ALTER TABLE Y ADD COLUMN X TEXT;",
    #     down_sql="ALTER TABLE Y DROP COLUMN X;",
    # ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get current schema version from database."""
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def run_migrations(conn: sqlite3.Connection) -> int:
    """
    Run all pending migrations.

    Returns:
        Number of migrations applied.
    """
    current = get_current_version(conn)
    applied = 0

    for migration in MIGRATIONS:
        if migration.version <= current:
            continue

        logger.info(f"Applying migration {migration.version}: {migration.description}")

        try:
            # Execute migration SQL (may contain multiple statements)
            conn.executescript(migration.up_sql)

            # Record migration
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (migration.version, migration.description),
            )
            conn.commit()
            applied += 1

        except Exception as e:
            conn.rollback()
            logger.error(f"Migration {migration.version} failed: {e}")
            raise

    if applied:
        logger.info(f"Applied {applied} migrations. Now at version {get_current_version(conn)}")
    else:
        logger.debug(f"Database already at version {current}, no migrations needed")

    return applied


def rollback_migration(conn: sqlite3.Connection, to_version: int) -> int:
    """
    Rollback migrations to a specific version.

    Returns:
        Number of migrations rolled back.
    """
    current = get_current_version(conn)
    if to_version >= current:
        return 0

    rolled_back = 0

    # Apply down migrations in reverse order
    for migration in reversed(MIGRATIONS):
        if migration.version <= to_version:
            break
        if migration.version > current:
            continue
        if not migration.down_sql:
            raise ValueError(
                f"Migration {migration.version} has no down_sql, cannot rollback"
            )

        logger.info(f"Rolling back migration {migration.version}")

        try:
            conn.executescript(migration.down_sql)
            conn.execute(
                "DELETE FROM schema_version WHERE version = ?",
                (migration.version,),
            )
            conn.commit()
            rolled_back += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"Rollback of {migration.version} failed: {e}")
            raise

    return rolled_back
```

---

## 3. Repository Pattern

### `repositories/base.py`

```python
"""
Base repository class.

All repositories inherit from this and get:
- Database connection access
- Common CRUD operations
- Type-safe query building
"""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel

from ..database import Database

T = TypeVar("T", bound=BaseModel)


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository.

    Subclasses must define:
    - table_name: Name of the database table
    - model_class: Pydantic model for rows
    - primary_key: Name of primary key column
    """

    table_name: str
    model_class: Type[T]
    primary_key: str = "id"

    def __init__(self, db: Database) -> None:
        self.db = db

    def _row_to_model(self, row: sqlite3.Row) -> T:
        """Convert database row to Pydantic model."""
        return self.model_class(**dict(row))

    def _rows_to_models(self, rows: List[sqlite3.Row]) -> List[T]:
        """Convert multiple rows to models."""
        return [self._row_to_model(row) for row in rows]

    def get_by_id(self, id_value: Any) -> Optional[T]:
        """Get single record by primary key."""
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = ?",
                (id_value,),
            ).fetchone()
        return self._row_to_model(row) if row else None

    def get_all(self, limit: int = 1000, offset: int = 0) -> List[T]:
        """Get all records with pagination."""
        with self.db.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.table_name} LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return self._rows_to_models(rows)

    def count(self) -> int:
        """Count total records."""
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()
        return row[0] if row else 0

    def exists(self, id_value: Any) -> bool:
        """Check if record exists."""
        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT 1 FROM {self.table_name} WHERE {self.primary_key} = ? LIMIT 1",
                (id_value,),
            ).fetchone()
        return row is not None

    def delete_by_id(self, id_value: Any) -> bool:
        """Delete record by primary key. Returns True if deleted."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"DELETE FROM {self.table_name} WHERE {self.primary_key} = ?",
                (id_value,),
            )
        return cursor.rowcount > 0

    @abstractmethod
    def create(self, model: T) -> T:
        """Create a new record. Must be implemented by subclass."""
        ...

    @abstractmethod
    def update(self, model: T) -> T:
        """Update an existing record. Must be implemented by subclass."""
        ...
```

### `repositories/market_repo.py`

```python
"""
Market and Token repositories.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .base import BaseRepository


class Market(BaseModel):
    """Market model."""
    condition_id: str
    question: str
    description: Optional[str] = None
    category: Optional[str] = None
    slug: Optional[str] = None
    created_at_polymarket: Optional[str] = None
    scheduled_end: Optional[str] = None
    resolved_at: Optional[str] = None
    is_resolved: bool = False
    resolution_price: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Token(BaseModel):
    """Token model."""
    token_id: str
    condition_id: str
    market_id: Optional[str] = None
    outcome: str
    outcome_index: Optional[int] = None
    created_at: Optional[str] = None


class MarketRepository(BaseRepository[Market]):
    """Repository for markets."""

    table_name = "markets"
    model_class = Market
    primary_key = "condition_id"

    def create(self, market: Market) -> Market:
        """Create a new market."""
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO markets (
                    condition_id, question, description, category, slug,
                    created_at_polymarket, scheduled_end, volume, liquidity,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market.condition_id,
                    market.question,
                    market.description,
                    market.category,
                    market.slug,
                    market.created_at_polymarket,
                    market.scheduled_end,
                    market.volume,
                    market.liquidity,
                    now,
                ),
            )
        market.created_at = now
        return market

    def update(self, market: Market) -> Market:
        """Update an existing market."""
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE markets SET
                    question = ?, description = ?, category = ?, slug = ?,
                    scheduled_end = ?, resolved_at = ?, is_resolved = ?,
                    resolution_price = ?, volume = ?, liquidity = ?,
                    updated_at = ?
                WHERE condition_id = ?
                """,
                (
                    market.question,
                    market.description,
                    market.category,
                    market.slug,
                    market.scheduled_end,
                    market.resolved_at,
                    market.is_resolved,
                    market.resolution_price,
                    market.volume,
                    market.liquidity,
                    now,
                    market.condition_id,
                ),
            )
        market.updated_at = now
        return market

    def upsert(self, market: Market) -> Market:
        """Insert or update market."""
        if self.exists(market.condition_id):
            return self.update(market)
        return self.create(market)

    def get_unresolved(self, limit: int = 1000) -> List[Market]:
        """Get all unresolved markets."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM markets WHERE is_resolved = 0 LIMIT ?",
                (limit,),
            ).fetchall()
        return self._rows_to_models(rows)

    def get_expiring_soon(self, hours: int = 24) -> List[Market]:
        """Get markets expiring within N hours."""
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM markets
                WHERE is_resolved = 0
                AND scheduled_end IS NOT NULL
                AND datetime(scheduled_end) <= datetime('now', '+' || ? || ' hours')
                ORDER BY scheduled_end
                """,
                (hours,),
            ).fetchall()
        return self._rows_to_models(rows)


class TokenRepository(BaseRepository[Token]):
    """Repository for tokens."""

    table_name = "tokens"
    model_class = Token
    primary_key = "token_id"

    def create(self, token: Token) -> Token:
        """Create a new token."""
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tokens (
                    token_id, condition_id, market_id, outcome, outcome_index,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token.token_id,
                    token.condition_id,
                    token.market_id,
                    token.outcome,
                    token.outcome_index,
                    now,
                ),
            )
        token.created_at = now
        return token

    def update(self, token: Token) -> Token:
        """Update token - rarely needed."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE tokens SET
                    condition_id = ?, market_id = ?, outcome = ?, outcome_index = ?
                WHERE token_id = ?
                """,
                (
                    token.condition_id,
                    token.market_id,
                    token.outcome,
                    token.outcome_index,
                    token.token_id,
                ),
            )
        return token

    def get_by_condition(self, condition_id: str) -> List[Token]:
        """Get all tokens for a market (YES and NO)."""
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tokens WHERE condition_id = ?",
                (condition_id,),
            ).fetchall()
        return self._rows_to_models(rows)

    def get_sibling(self, token_id: str) -> Optional[Token]:
        """Get the sibling token (YES if this is NO, vice versa)."""
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT t2.* FROM tokens t1
                JOIN tokens t2 ON t1.condition_id = t2.condition_id
                WHERE t1.token_id = ? AND t2.token_id != ?
                """,
                (token_id, token_id),
            ).fetchone()
        return self._row_to_model(row) if row else None
```

### `repositories/trigger_repo.py`

```python
"""
Trigger repository - tracks first-hit price triggers.

CRITICAL: This repository has dual-key deduplication:
1. By token_id + threshold (backwards compat)
2. By condition_id + threshold (prevents duplicate token spam)

See "Duplicate Token IDs" gotcha in main CLAUDE.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .base import BaseRepository


class Trigger(BaseModel):
    """First-hit trigger record."""
    id: Optional[int] = None
    token_id: str
    condition_id: str
    threshold: float
    price: float
    size: Optional[float] = None
    timestamp: int
    strategy_name: Optional[str] = None
    signal_type: Optional[str] = None
    signal_reason: Optional[str] = None
    model_score: Optional[float] = None
    model_version: Optional[str] = None
    passed_filters: bool = True
    filter_failures: Optional[str] = None  # JSON array
    created_at: Optional[str] = None


class TriggerRepository(BaseRepository[Trigger]):
    """Repository for first-hit triggers."""

    table_name = "triggers"
    model_class = Trigger
    primary_key = "id"

    def create(self, trigger: Trigger) -> Trigger:
        """Create a new trigger record."""
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO triggers (
                    token_id, condition_id, threshold, price, size, timestamp,
                    strategy_name, signal_type, signal_reason,
                    model_score, model_version,
                    passed_filters, filter_failures,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trigger.token_id,
                    trigger.condition_id,
                    trigger.threshold,
                    trigger.price,
                    trigger.size,
                    trigger.timestamp,
                    trigger.strategy_name,
                    trigger.signal_type,
                    trigger.signal_reason,
                    trigger.model_score,
                    trigger.model_version,
                    1 if trigger.passed_filters else 0,
                    trigger.filter_failures,
                    now,
                ),
            )
            trigger.id = cursor.lastrowid
        trigger.created_at = now
        return trigger

    def update(self, trigger: Trigger) -> Trigger:
        """Update trigger (e.g., after scoring)."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE triggers SET
                    signal_type = ?, signal_reason = ?,
                    model_score = ?, model_version = ?,
                    passed_filters = ?, filter_failures = ?
                WHERE id = ?
                """,
                (
                    trigger.signal_type,
                    trigger.signal_reason,
                    trigger.model_score,
                    trigger.model_version,
                    1 if trigger.passed_filters else 0,
                    trigger.filter_failures,
                    trigger.id,
                ),
            )
        return trigger

    def has_triggered(self, token_id: str, threshold: float) -> bool:
        """Check if token has already triggered at this threshold."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM triggers WHERE token_id = ? AND threshold = ? LIMIT 1",
                (token_id, threshold),
            ).fetchone()
        return row is not None

    def has_condition_triggered(self, condition_id: str, threshold: float) -> bool:
        """
        Check if ANY token for this condition has triggered.

        CRITICAL: Use this to prevent duplicate triggers from
        multiple token_ids pointing to the same market.
        """
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM triggers WHERE condition_id = ? AND threshold = ? LIMIT 1",
                (condition_id, threshold),
            ).fetchone()
        return row is not None

    def get_by_token_threshold(
        self, token_id: str, threshold: float
    ) -> Optional[Trigger]:
        """Get trigger for specific token and threshold."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM triggers WHERE token_id = ? AND threshold = ?",
                (token_id, threshold),
            ).fetchone()
        return self._row_to_model(row) if row else None

    def get_recent(
        self,
        limit: int = 100,
        strategy_name: Optional[str] = None,
    ) -> List[Trigger]:
        """Get recent triggers, optionally filtered by strategy."""
        with self.db.connection() as conn:
            if strategy_name:
                rows = conn.execute(
                    """
                    SELECT * FROM triggers
                    WHERE strategy_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (strategy_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM triggers ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return self._rows_to_models(rows)

    def get_executed(self, since_timestamp: Optional[int] = None) -> List[Trigger]:
        """Get triggers that resulted in execution."""
        with self.db.connection() as conn:
            if since_timestamp:
                rows = conn.execute(
                    """
                    SELECT * FROM triggers
                    WHERE signal_type = 'execute'
                    AND timestamp >= ?
                    ORDER BY timestamp DESC
                    """,
                    (since_timestamp,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM triggers
                    WHERE signal_type = 'execute'
                    ORDER BY timestamp DESC
                    """,
                ).fetchall()
        return self._rows_to_models(rows)
```

---

## 4. CLAUDE.md for Storage Layer

```markdown
# Storage Layer

## Purpose
Persist and query all trading bot data using SQLite.

## Responsibilities
- Database connection management (thread-safe)
- Schema definition and migrations
- Repository pattern for data access
- Transaction management

## NOT Responsibilities
- Making trading decisions
- Calling external APIs
- Business logic
- Data transformation/enrichment

## Key Files

| File | Purpose |
|------|---------|
| `database.py` | Connection management, transactions |
| `migrations.py` | Schema versioning, migration runner |
| `schema.sql` | Complete database schema (source of truth) |
| `repositories/base.py` | Base repository with common CRUD |
| `repositories/market_repo.py` | Markets and tokens |
| `repositories/trigger_repo.py` | First-hit triggers |
| `repositories/trade_repo.py` | Historical trades |
| `repositories/order_repo.py` | Live orders |
| `repositories/position_repo.py` | Positions |
| `repositories/watchlist_repo.py` | Strategy watchlists |

## Public Interfaces

```python
# Database
db = Database(DatabaseConfig(path=Path("data/trading.db")))
db.initialize()  # Run migrations
db.health_check() -> bool

# Connections
with db.connection() as conn: ...  # Read-only
with db.transaction() as conn: ... # Auto-commit/rollback

# Repositories
market_repo = MarketRepository(db)
market_repo.create(market) -> Market
market_repo.get_by_id(condition_id) -> Optional[Market]
market_repo.upsert(market) -> Market
market_repo.get_unresolved() -> List[Market]

trigger_repo = TriggerRepository(db)
trigger_repo.has_triggered(token_id, threshold) -> bool
trigger_repo.has_condition_triggered(condition_id, threshold) -> bool  # CRITICAL
```

## Critical Gotchas

### 1. Dual-Key Trigger Deduplication
Multiple token_ids can point to the same market (condition_id).
ALWAYS check both `has_triggered()` AND `has_condition_triggered()`.

### 2. WAL Mode Required
SQLite WAL mode is required for concurrent access. Set in DatabaseConfig.

### 3. Foreign Keys Must Be Enabled
SQLite doesn't enforce foreign keys by default. The Database class enables them.

### 4. Timestamp Format
All timestamps stored as ISO format strings, except:
- `trades.timestamp`: Unix timestamp (int) for performance
- `triggers.timestamp`: Unix timestamp (int)

## Testing

```bash
pytest src/polymarket_bot/storage/tests/ -v
```

## Configuration

```python
DatabaseConfig(
    path=Path("data/trading.db"),
    timeout=30.0,
    journal_mode="WAL",
    synchronous="NORMAL",
    foreign_keys=True,
)
```
```

---

## 5. Test Fixtures

### `tests/conftest.py`

```python
"""
Shared test fixtures for storage tests.
"""
import pytest
from pathlib import Path

from polymarket_bot.storage.database import Database, DatabaseConfig
from polymarket_bot.storage.repositories.market_repo import (
    Market, Token, MarketRepository, TokenRepository
)
from polymarket_bot.storage.repositories.trigger_repo import (
    Trigger, TriggerRepository
)


@pytest.fixture
def db_config(tmp_path: Path) -> DatabaseConfig:
    """Database config with temp path."""
    return DatabaseConfig(path=tmp_path / "test.db")


@pytest.fixture
def db(db_config: DatabaseConfig) -> Database:
    """Initialized database."""
    database = Database(db_config)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def market_repo(db: Database) -> MarketRepository:
    """Market repository."""
    return MarketRepository(db)


@pytest.fixture
def token_repo(db: Database) -> TokenRepository:
    """Token repository."""
    return TokenRepository(db)


@pytest.fixture
def trigger_repo(db: Database) -> TriggerRepository:
    """Trigger repository."""
    return TriggerRepository(db)


@pytest.fixture
def sample_market() -> Market:
    """Sample market for testing."""
    return Market(
        condition_id="0x123abc",
        question="Will BTC reach $100k by end of 2025?",
        category="crypto",
        scheduled_end="2025-12-31T23:59:59Z",
    )


@pytest.fixture
def sample_tokens(sample_market: Market) -> tuple[Token, Token]:
    """Sample YES and NO tokens for testing."""
    yes_token = Token(
        token_id="0xyes123",
        condition_id=sample_market.condition_id,
        outcome="Yes",
        outcome_index=0,
    )
    no_token = Token(
        token_id="0xno456",
        condition_id=sample_market.condition_id,
        outcome="No",
        outcome_index=1,
    )
    return yes_token, no_token


@pytest.fixture
def sample_trigger(sample_tokens: tuple[Token, Token]) -> Trigger:
    """Sample trigger for testing."""
    yes_token, _ = sample_tokens
    return Trigger(
        token_id=yes_token.token_id,
        condition_id=yes_token.condition_id,
        threshold=0.95,
        price=0.95,
        size=100.0,
        timestamp=1700000000,
    )
```

---

This completes the Storage Layer specification. Ready for the next layer?
