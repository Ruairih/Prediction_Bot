# Startup & Operations UX Improvement Plan

> **STATUS: PLANNED**
> **Created:** 2025-12-23
> **Author:** Codex + Claude Analysis

## Executive Summary

The bot currently has fragmented entry points, manual position sync, stale database records, and unclear live/paper mode distinction. This plan consolidates startup into a single command, adds automatic position reconciliation, provides a status command, and makes live vs paper mode crystal clear.

---

## Problem Statement

### Current Pain Points

| Issue | Current State | User Impact |
|-------|---------------|-------------|
| **Fragmented entry points** | `main.py`, `sync_positions.py`, 5+ scripts | Confusing, easy to miss steps |
| **Manual position sync** | CLI-only, never scheduled | Ghost positions, stale DB records |
| **No periodic reconciliation** | Background tasks skip position sync | `bot_trade` positions never cleaned up |
| **Live/Paper unclear** | Just a log line, defaults to dry-run | Users think they're trading when not |
| **No status command** | Must query DB manually | Can't quickly check health/P&L |
| **Complex environment setup** | Multiple files, env vars, credentials | High barrier to getting started |
| **Dashboard confusion** | Multiple dashboards, unclear which to use | Users don't know what's running |

### Evidence: Ghost Positions Bug

Discovered 2025-12-23: Database shows 7 `bot_trade` positions as "open" but they don't exist on Polymarket. The position sync only imports new positions but doesn't reconcile `bot_trade` positions that were closed externally.

```sql
-- Ghost positions in DB (don't exist on Polymarket)
SELECT COUNT(*) FROM positions
WHERE import_source = 'bot_trade' AND status = 'open';
-- Returns: 7

-- Actual positions on Polymarket (from sync)
SELECT COUNT(*) FROM positions
WHERE import_source = 'polymarket_sync' AND status = 'open';
-- Returns: 3
```

---

## Solution Architecture

### Target User Experience

```bash
# First time setup
python -m polymarket_bot bootstrap

# Start bot (paper trading - default, safe)
python -m polymarket_bot start

# Start bot (live trading - requires confirmation)
python -m polymarket_bot start --live --confirm

# Check status
python -m polymarket_bot status

# Manual position sync (if needed)
python -m polymarket_bot sync --dry-run
python -m polymarket_bot sync
```

### New File Structure

```
src/polymarket_bot/
├── __main__.py                    # NEW: enables `python -m polymarket_bot`
├── cli.py                         # NEW: CLI with subcommands
├── commands/                      # NEW: command implementations
│   ├── __init__.py
│   ├── start.py                   # Start command (wraps main.py)
│   ├── status.py                  # Status command
│   ├── sync.py                    # Sync command (wraps sync_positions.py)
│   └── bootstrap.py               # Bootstrap command
├── main.py                        # MODIFY: add preflight, startup sync
├── sync_positions.py              # KEEP: backward compat, add deprecation notice
├── core/
│   └── background_tasks.py        # MODIFY: add position sync loop
├── execution/
│   └── position_sync.py           # MODIFY: add auto mode, grace period
└── monitoring/
    └── health_checker.py          # MODIFY: add sync freshness check

seed/
└── 05_bot_runtime_status.sql      # NEW: heartbeat table for status command

scripts/
├── start.sh                       # NEW: simple shell wrapper
└── bootstrap.sh                   # MODIFY: consolidate setup steps
```

---

## Implementation Phases

### Phase 1: Automatic Position Reconciliation (HIGH PRIORITY)

**Goal:** Fix the ghost positions bug by adding periodic position sync to background tasks.

**Why First:** This is causing real data integrity issues right now.

#### 1.1 Extend BackgroundTaskConfig

**File:** `src/polymarket_bot/core/background_tasks.py`

```python
@dataclass
class BackgroundTaskConfig:
    # Existing fields...
    watchlist_rescore_interval_seconds: float = 3600
    watchlist_enabled: bool = True
    order_sync_interval_seconds: float = 30
    order_sync_enabled: bool = True
    exit_eval_interval_seconds: float = 60
    exit_eval_enabled: bool = True

    # NEW: Position sync configuration
    position_sync_interval_seconds: float = 300  # 5 minutes
    position_sync_enabled: bool = True
    position_sync_on_startup: bool = True

    # Safety: Only close positions after N consecutive misses
    # Prevents mass-close on API glitches
    position_sync_miss_threshold: int = 2
```

#### 1.2 Add Position Sync Loop

**File:** `src/polymarket_bot/core/background_tasks.py`

```python
class BackgroundTasksManager:
    def __init__(
        self,
        engine: "TradingEngine",
        execution_service: "ExecutionService",
        config: BackgroundTaskConfig,
        price_fetcher: Optional[Callable] = None,
        position_sync_service: Optional["PositionSyncService"] = None,  # NEW
        wallet_address: Optional[str] = None,  # NEW
    ):
        # ... existing init ...
        self._position_sync_service = position_sync_service
        self._wallet_address = wallet_address
        self._position_miss_counts: Dict[str, int] = {}  # Track consecutive misses

    async def _position_sync_loop(self) -> None:
        """Periodically sync positions from Polymarket."""
        while self._running:
            try:
                await asyncio.sleep(self._config.position_sync_interval_seconds)

                if not self._position_sync_service or not self._wallet_address:
                    continue

                result = await self._position_sync_service.sync_positions(
                    wallet_address=self._wallet_address,
                    dry_run=False,
                    hold_policy="new",  # Safe default for auto-discovered positions
                    sync_type="auto",
                    miss_threshold=self._config.position_sync_miss_threshold,
                    miss_counts=self._position_miss_counts,
                )

                logger.info(
                    f"Position sync: found={result.positions_found}, "
                    f"imported={result.positions_imported}, "
                    f"updated={result.positions_updated}, "
                    f"closed={result.positions_closed}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position sync error: {e}")
                await asyncio.sleep(60)  # Back off on error
```

#### 1.3 Add Grace Period to Position Sync

**File:** `src/polymarket_bot/execution/position_sync.py`

```python
async def sync_positions(
    self,
    wallet_address: str,
    dry_run: bool = True,
    hold_policy: str = "new",
    mature_days: int = 8,
    sync_type: str = "manual",  # NEW: "manual" | "auto" | "startup"
    miss_threshold: int = 2,     # NEW: consecutive misses before close
    miss_counts: Optional[Dict[str, int]] = None,  # NEW: track misses
) -> SyncResult:
    """
    Sync remote positions to local database.

    Safety Features:
    - miss_threshold: Only close positions after N consecutive sync misses
    - This prevents mass-closing on temporary API issues
    - Manual syncs (miss_threshold=1) close immediately for explicit user action
    """
    # ... existing code ...

    # Check for positions that exist locally but not remotely
    for token_id, local in local_positions.items():
        if token_id not in remote_token_ids:
            # Track consecutive misses (NEW)
            if miss_counts is not None:
                miss_counts[token_id] = miss_counts.get(token_id, 0) + 1

                if miss_counts[token_id] < miss_threshold:
                    logger.info(
                        f"[{run_id}] MISS {miss_counts[token_id]}/{miss_threshold}: "
                        f"{token_id[:20]}... (waiting for threshold)"
                    )
                    continue

            # Close position (existing logic)
            logger.info(f"[{run_id}] CLOSE: {token_id} (not found on Polymarket)")
            # ... close logic ...

    # Clear miss counts for positions that exist (NEW)
    if miss_counts is not None:
        for token_id in remote_token_ids:
            miss_counts.pop(token_id, None)
```

#### 1.4 Wire Into Main

**File:** `src/polymarket_bot/main.py`

```python
async def _init_background_tasks(self) -> None:
    """Initialize background task manager."""
    from polymarket_bot.core import BackgroundTasksManager, BackgroundTaskConfig
    from polymarket_bot.execution.position_sync import PositionSyncService

    # Get wallet address from credentials
    wallet_address = self.config.clob_credentials.get("funder")

    # Create position sync service
    position_sync_service = None
    if wallet_address:
        position_sync_service = PositionSyncService(
            db=self._db,
            position_tracker=self._execution_service._position_tracker,
        )

    config = BackgroundTaskConfig(
        # ... existing config ...
        position_sync_interval_seconds=300,  # 5 minutes
        position_sync_enabled=True,
        position_sync_on_startup=True,
        position_sync_miss_threshold=2,
    )

    self._background_tasks = BackgroundTasksManager(
        engine=self._engine,
        execution_service=self._execution_service,
        config=config,
        price_fetcher=price_fetcher,
        position_sync_service=position_sync_service,  # NEW
        wallet_address=wallet_address,  # NEW
    )
```

---

### Phase 2: Single-Command Startup (HIGH PRIORITY)

**Goal:** Unified entry point with preflight checks and clear mode indication.

#### 2.1 Create `__main__.py`

**File:** `src/polymarket_bot/__main__.py`

```python
"""
Enable running the bot as a module: python -m polymarket_bot

Usage:
    python -m polymarket_bot              # Start with defaults (paper mode)
    python -m polymarket_bot start        # Explicit start
    python -m polymarket_bot status       # Check bot status
    python -m polymarket_bot sync         # Sync positions
    python -m polymarket_bot bootstrap    # First-time setup
"""
from polymarket_bot.cli import main

if __name__ == "__main__":
    main()
```

#### 2.2 Create CLI

**File:** `src/polymarket_bot/cli.py`

```python
"""
Polymarket Trading Bot CLI

Provides a unified command-line interface for all bot operations.
"""
import argparse
import sys
from typing import List, Optional


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="polymarket_bot",
        description="Polymarket Trading Bot - Strategy-agnostic trading framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # START command
    start_parser = subparsers.add_parser(
        "start",
        help="Start the trading bot",
        description="Start the trading bot with all services",
    )
    start_parser.add_argument(
        "--paper", "--dry-run",
        action="store_true",
        dest="paper",
        help="Run in paper trading mode (default)",
    )
    start_parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live trading mode (requires --confirm)",
    )
    start_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm live trading mode",
    )
    start_parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip initial position sync on startup",
    )
    start_parser.add_argument(
        "--mode",
        choices=["all", "ingestion", "engine", "monitor"],
        default="all",
        help="Which services to run (default: all)",
    )
    start_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level",
    )

    # STATUS command
    status_parser = subparsers.add_parser(
        "status",
        help="Check bot status and positions",
        description="Display bot health, positions, and P&L",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # SYNC command
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync positions from Polymarket",
        description="Import/reconcile positions from Polymarket",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without making changes",
    )
    sync_parser.add_argument(
        "--wallet",
        type=str,
        help="Wallet address (defaults to funder from credentials)",
    )
    sync_parser.add_argument(
        "--policy",
        choices=["new", "mature", "actual"],
        default="new",
        help="Hold policy for imported positions",
    )

    # BOOTSTRAP command
    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="First-time setup",
        description="Set up configuration files and database",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing configuration files",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    parsed = parser.parse_args(args)

    # Default to 'start' if no command given
    if parsed.command is None:
        parsed.command = "start"
        parsed.paper = True
        parsed.live = False
        parsed.confirm = False
        parsed.skip_sync = False
        parsed.mode = "all"
        parsed.log_level = None

    if parsed.command == "start":
        return _run_start(parsed)
    elif parsed.command == "status":
        return _run_status(parsed)
    elif parsed.command == "sync":
        return _run_sync(parsed)
    elif parsed.command == "bootstrap":
        return _run_bootstrap(parsed)
    else:
        parser.print_help()
        return 1


def _run_start(args) -> int:
    """Run the start command."""
    import os

    # Handle live vs paper mode
    if args.live and not args.confirm:
        print("\n" + "=" * 60)
        print("  LIVE TRADING MODE REQUIRES CONFIRMATION")
        print("=" * 60)
        print("\nYou are about to start LIVE trading with real money.")
        print("This will submit real orders to Polymarket.\n")
        print("To confirm, run:")
        print("  python -m polymarket_bot start --live --confirm\n")
        print("Or set environment variable:")
        print("  LIVE_CONFIRM=1 python -m polymarket_bot start --live\n")
        return 1

    # Check for env var confirmation
    if args.live and not args.confirm:
        if os.environ.get("LIVE_CONFIRM", "").lower() not in ("1", "true", "yes"):
            print("ERROR: Live mode requires --confirm flag or LIVE_CONFIRM=1")
            return 1

    # Set DRY_RUN based on mode
    if args.live:
        os.environ["DRY_RUN"] = "false"
    else:
        os.environ["DRY_RUN"] = "true"

    # Set skip sync flag
    if args.skip_sync:
        os.environ["SKIP_STARTUP_SYNC"] = "true"

    # Import and run main
    from polymarket_bot.main import main as bot_main
    return bot_main()


def _run_status(args) -> int:
    """Run the status command."""
    import asyncio
    from polymarket_bot.commands.status import run_status
    return asyncio.run(run_status(json_output=args.json))


def _run_sync(args) -> int:
    """Run the sync command."""
    import asyncio
    import sys

    # Delegate to existing sync_positions module
    sys.argv = ["sync_positions"]
    if args.dry_run:
        sys.argv.append("--dry-run")
    if args.wallet:
        sys.argv.extend(["--wallet", args.wallet])
    if args.policy:
        sys.argv.extend(["--policy", args.policy])

    from polymarket_bot.sync_positions import main as sync_main
    return asyncio.run(sync_main())


def _run_bootstrap(args) -> int:
    """Run the bootstrap command."""
    from polymarket_bot.commands.bootstrap import run_bootstrap
    return run_bootstrap(force=args.force)


if __name__ == "__main__":
    sys.exit(main())
```

#### 2.3 Add Preflight Checks to Main

**File:** `src/polymarket_bot/main.py` (add to `TradingBot.start()`)

```python
async def start(self, mode: str = "all") -> None:
    """Start the trading bot."""

    # NEW: Preflight checks
    if not await self._preflight_checks():
        return

    # NEW: Mode banner
    self._print_mode_banner()

    # ... existing startup code ...

    # NEW: Startup position sync (before engine)
    if mode in ("all", "engine") and not os.environ.get("SKIP_STARTUP_SYNC"):
        await self._startup_position_sync()

    # ... rest of startup ...

async def _preflight_checks(self) -> bool:
    """Run preflight checks before starting."""
    logger.info("Running preflight checks...")

    checks_passed = True

    # 1. Database URL
    if not self.config.database_url:
        logger.error("PREFLIGHT FAILED: DATABASE_URL not set")
        checks_passed = False

    # 2. Credentials for live mode
    if not self.config.dry_run:
        if not self.config.clob_credentials:
            logger.error("PREFLIGHT FAILED: Live mode requires Polymarket credentials")
            checks_passed = False
        else:
            required = ["api_key", "api_secret", "api_passphrase", "private_key", "funder"]
            missing = [f for f in required if f not in self.config.clob_credentials]
            if missing:
                logger.error(f"PREFLIGHT FAILED: Missing credential fields: {missing}")
                checks_passed = False

    # 3. Database connectivity
    if self.config.database_url:
        try:
            from polymarket_bot.storage import Database, DatabaseConfig
            db = Database(DatabaseConfig(url=self.config.database_url))
            await db.initialize()
            if not await db.health_check():
                raise Exception("Health check failed")
            await db.close()
            logger.info("  Database: OK")
        except Exception as e:
            logger.error(f"PREFLIGHT FAILED: Database connection failed: {e}")
            checks_passed = False

    if checks_passed:
        logger.info("Preflight checks: ALL PASSED")

    return checks_passed

def _print_mode_banner(self) -> None:
    """Print clear mode indication."""
    print()
    print("=" * 60)
    if self.config.dry_run:
        print("  PAPER TRADING MODE (DRY RUN)")
        print("  No real orders will be submitted")
    else:
        print("  LIVE TRADING MODE")
        print("  Real orders will be submitted to Polymarket")
        print("  Real money is at risk!")
    print("=" * 60)
    print()

async def _startup_position_sync(self) -> None:
    """Sync positions from Polymarket on startup."""
    wallet_address = self.config.clob_credentials.get("funder")
    if not wallet_address:
        logger.warning("Skipping startup sync: no wallet address in credentials")
        return

    logger.info("Running startup position sync...")

    from polymarket_bot.execution.position_sync import PositionSyncService
    from polymarket_bot.execution.position_tracker import PositionTracker

    position_tracker = PositionTracker(self._db)
    sync_service = PositionSyncService(self._db, position_tracker)

    result = await sync_service.sync_positions(
        wallet_address=wallet_address,
        dry_run=False,
        hold_policy="new",
        sync_type="startup",
    )

    logger.info(
        f"Startup sync complete: "
        f"found={result.positions_found}, "
        f"imported={result.positions_imported}, "
        f"updated={result.positions_updated}, "
        f"closed={result.positions_closed}"
    )
```

---

### Phase 3: Status Command (MEDIUM PRIORITY)

**Goal:** Easy way to check bot status, positions, and P&L.

#### 3.1 Create Heartbeat Table

**File:** `seed/05_bot_runtime_status.sql`

```sql
-- Bot runtime status for health monitoring
CREATE TABLE IF NOT EXISTS bot_runtime_status (
    id SERIAL PRIMARY KEY,
    instance_id TEXT NOT NULL,
    mode TEXT NOT NULL,  -- 'paper' or 'live'
    started_at TIMESTAMP NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    services_running JSONB,  -- {"engine": true, "ingestion": true, ...}
    stats JSONB,  -- {"triggers_evaluated": 100, "entries_executed": 5, ...}
    created_at TIMESTAMP DEFAULT NOW()
);

-- Only keep most recent status per instance
CREATE UNIQUE INDEX IF NOT EXISTS idx_runtime_status_instance
ON bot_runtime_status(instance_id);
```

#### 3.2 Create Status Command

**File:** `src/polymarket_bot/commands/status.py`

```python
"""
Status command - Display bot health, positions, and P&L.

Usage:
    python -m polymarket_bot status
    python -m polymarket_bot status --json
"""
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def run_status(json_output: bool = False) -> int:
    """Run the status command."""
    from polymarket_bot.storage import Database, DatabaseConfig

    # Get database URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try loading from .env
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DATABASE_URL="):
                        database_url = line.split("=", 1)[1].strip()
                        break

    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    # Connect to database
    db = Database(DatabaseConfig(url=database_url))
    await db.initialize()

    try:
        status = await _gather_status(db)

        if json_output:
            print(json.dumps(status, indent=2, default=str))
        else:
            _print_status(status)

        return 0
    finally:
        await db.close()


async def _gather_status(db) -> Dict[str, Any]:
    """Gather all status information."""
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bot": await _get_bot_status(db),
        "positions": await _get_positions(db),
        "recent_activity": await _get_recent_activity(db),
        "health": await _get_health(db),
    }
    return status


async def _get_bot_status(db) -> Dict[str, Any]:
    """Get bot runtime status."""
    query = """
        SELECT instance_id, mode, started_at, last_heartbeat, services_running, stats
        FROM bot_runtime_status
        ORDER BY last_heartbeat DESC
        LIMIT 1
    """
    row = await db.fetchrow(query)

    if not row:
        return {"running": False, "message": "No bot instance found"}

    last_heartbeat = row["last_heartbeat"]
    if isinstance(last_heartbeat, str):
        last_heartbeat = datetime.fromisoformat(last_heartbeat.replace("Z", "+00:00"))

    now = datetime.now(timezone.utc)
    heartbeat_age = (now - last_heartbeat.replace(tzinfo=timezone.utc)).total_seconds()

    return {
        "running": heartbeat_age < 60,  # Consider dead if no heartbeat in 60s
        "instance_id": row["instance_id"],
        "mode": row["mode"],
        "started_at": row["started_at"],
        "last_heartbeat": row["last_heartbeat"],
        "heartbeat_age_seconds": int(heartbeat_age),
        "services": row["services_running"],
        "stats": row["stats"],
    }


async def _get_positions(db) -> Dict[str, Any]:
    """Get open positions summary."""
    query = """
        SELECT
            id, description, outcome, side, size,
            entry_price, current_price, unrealized_pnl,
            import_source, entry_timestamp
        FROM positions
        WHERE status = 'open'
        ORDER BY unrealized_pnl DESC
    """
    rows = await db.fetch(query)

    positions = []
    total_invested = Decimal("0")
    total_pnl = Decimal("0")

    for row in rows:
        entry_cost = Decimal(str(row["size"])) * Decimal(str(row["entry_price"]))
        pnl = Decimal(str(row["unrealized_pnl"] or 0))

        positions.append({
            "id": row["id"],
            "description": row["description"] or "(no description)",
            "outcome": row["outcome"],
            "size": float(row["size"]),
            "entry_price": float(row["entry_price"]),
            "current_price": float(row["current_price"] or 0),
            "pnl": float(pnl),
            "pnl_pct": float(pnl / entry_cost * 100) if entry_cost > 0 else 0,
            "source": row["import_source"],
        })

        total_invested += entry_cost
        total_pnl += pnl

    return {
        "count": len(positions),
        "total_invested": float(total_invested),
        "total_pnl": float(total_pnl),
        "total_pnl_pct": float(total_pnl / total_invested * 100) if total_invested > 0 else 0,
        "positions": positions,
    }


async def _get_recent_activity(db) -> Dict[str, Any]:
    """Get recent trades and exits."""
    # Recent syncs
    sync_query = """
        SELECT run_id, sync_type, positions_found, positions_imported,
               positions_updated, positions_closed, completed_at
        FROM positions_sync_log
        ORDER BY completed_at DESC
        LIMIT 5
    """
    syncs = await db.fetch(sync_query)

    # Recent exits
    exit_query = """
        SELECT id, description, outcome, exit_timestamp, realized_pnl, resolution
        FROM positions
        WHERE status = 'closed' AND exit_timestamp IS NOT NULL
        ORDER BY exit_timestamp DESC
        LIMIT 5
    """
    exits = await db.fetch(exit_query)

    return {
        "recent_syncs": [dict(s) for s in syncs],
        "recent_exits": [dict(e) for e in exits],
    }


async def _get_health(db) -> Dict[str, Any]:
    """Get component health status."""
    health = {
        "database": "healthy",
        "components": {},
    }

    # Check database
    try:
        await db.execute("SELECT 1")
    except Exception as e:
        health["database"] = f"unhealthy: {e}"

    return health


def _print_status(status: Dict[str, Any]) -> None:
    """Print status in human-readable format."""
    print()
    print("BOT STATUS")
    print("=" * 60)

    # Bot status
    bot = status["bot"]
    if bot.get("running"):
        uptime = ""
        if bot.get("started_at"):
            # Calculate uptime
            pass
        print(f"Running: YES ({bot.get('mode', 'unknown')} mode)")
        print(f"Last heartbeat: {bot.get('heartbeat_age_seconds', '?')}s ago")
    else:
        print("Running: NO")
        print(f"  {bot.get('message', 'Unknown status')}")

    # Positions
    print()
    print("POSITIONS")
    print("-" * 60)

    pos = status["positions"]
    if pos["count"] == 0:
        print("  No open positions")
    else:
        for p in pos["positions"][:10]:  # Show top 10
            desc = p["description"][:40] if p["description"] else "(unknown)"
            pnl_sign = "+" if p["pnl"] >= 0 else ""
            print(f"  {desc:<42} {pnl_sign}${p['pnl']:.2f} ({pnl_sign}{p['pnl_pct']:.1f}%)")

        if pos["count"] > 10:
            print(f"  ... and {pos['count'] - 10} more")

        print("-" * 60)
        total_sign = "+" if pos["total_pnl"] >= 0 else ""
        print(f"  Total: ${pos['total_invested']:.2f} invested, "
              f"{total_sign}${pos['total_pnl']:.2f} P&L ({total_sign}{pos['total_pnl_pct']:.1f}%)")

    # Health
    print()
    print("HEALTH")
    print("-" * 60)
    health = status["health"]
    print(f"  Database: {health['database']}")

    print()
```

---

### Phase 4: Live vs Paper Clarity (MEDIUM PRIORITY)

Already included in Phase 2 CLI implementation:
- `--paper` / `--live` flags
- `--confirm` requirement for live mode
- Clear mode banner at startup
- Environment variable override (`LIVE_CONFIRM=1`)

---

### Phase 5: Bootstrap Command (LOWER PRIORITY)

**Goal:** Single command to set up everything from scratch.

#### 5.1 Create Bootstrap Command

**File:** `src/polymarket_bot/commands/bootstrap.py`

```python
"""
Bootstrap command - First-time setup for the bot.

Creates configuration files and sets up the database.
"""
import os
import shutil
from pathlib import Path


def run_bootstrap(force: bool = False) -> int:
    """Run the bootstrap setup."""
    print()
    print("POLYMARKET BOT BOOTSTRAP")
    print("=" * 60)
    print()

    workspace = Path.cwd()

    # 1. Create .env from example
    env_example = workspace / ".env.example"
    env_file = workspace / ".env"

    if env_file.exists() and not force:
        print(f"  .env already exists (use --force to overwrite)")
    elif env_example.exists():
        shutil.copy(env_example, env_file)
        print(f"  Created .env from .env.example")
    else:
        print(f"  WARNING: .env.example not found")

    # 2. Create credentials from example
    creds_example = workspace / "polymarket_api_creds.json.example"
    creds_file = workspace / "polymarket_api_creds.json"

    if creds_file.exists() and not force:
        print(f"  polymarket_api_creds.json already exists (use --force to overwrite)")
    elif creds_example.exists():
        shutil.copy(creds_example, creds_file)
        print(f"  Created polymarket_api_creds.json from example")
    else:
        print(f"  WARNING: polymarket_api_creds.json.example not found")

    # 3. Print next steps
    print()
    print("NEXT STEPS")
    print("-" * 60)
    print("1. Edit .env and set DATABASE_URL")
    print("2. Edit polymarket_api_creds.json with your Polymarket API keys")
    print("3. Start the bot:")
    print("     python -m polymarket_bot start          # Paper trading")
    print("     python -m polymarket_bot start --live   # Live trading")
    print()

    return 0
```

---

### Phase 6: Dashboard Clarity (LOWER PRIORITY)

**Goal:** Clear documentation on which dashboard does what.

#### 6.1 Add DASHBOARD_MODE Config

**File:** `src/polymarket_bot/main.py`

```python
# In BotConfig
dashboard_mode: str = "monitor"  # "monitor" | "ingestion" | "both" | "none"
```

#### 6.2 Update Documentation

**File:** `docs/USER_GUIDE.md` (or CLAUDE.md)

```markdown
## Dashboards

The bot has two dashboard components:

| Dashboard | Port | Purpose | When to Use |
|-----------|------|---------|-------------|
| **Monitor** | 5055 | Health, positions, P&L | Primary dashboard for operations |
| **Ingestion** | 8080 | WebSocket status, data flow | Debugging data issues |

### Configuration

```bash
# Run only monitor dashboard (default)
DASHBOARD_MODE=monitor python -m polymarket_bot start

# Run only ingestion dashboard
DASHBOARD_MODE=ingestion python -m polymarket_bot start

# Run both dashboards
DASHBOARD_MODE=both python -m polymarket_bot start

# Disable all dashboards
DASHBOARD_MODE=none python -m polymarket_bot start
```
```

---

## Backward Compatibility Matrix

| Old Interface | Behavior | New Equivalent |
|--------------|----------|----------------|
| `python -m polymarket_bot.main` | Works unchanged | `python -m polymarket_bot start` |
| `python -m polymarket_bot.sync_positions` | Works, shows deprecation notice | `python -m polymarket_bot sync` |
| `--dry-run` flag | Works as alias | `--paper` |
| `--mode all/ingestion/engine/monitor` | Works unchanged | Same |
| `DRY_RUN=true` env var | Works unchanged | Same |
| `DASHBOARD_*` env vars | Work unchanged | Same |
| Scripts in `scripts/` | Work unchanged | Same |

---

## Testing Plan

### Phase 1 Tests

```python
# test_position_sync_auto.py
class TestAutomaticPositionSync:
    def test_syncs_on_interval(self):
        """Position sync runs every 5 minutes."""

    def test_respects_miss_threshold(self):
        """Positions only closed after N consecutive misses."""

    def test_clears_miss_count_on_found(self):
        """Miss count resets when position found again."""

    def test_reconciles_all_import_sources(self):
        """Syncs bot_trade and polymarket_sync positions."""
```

### Phase 2 Tests

```python
# test_cli.py
class TestCLI:
    def test_default_command_is_start(self):
        """Running without command defaults to start."""

    def test_live_requires_confirm(self):
        """Live mode without --confirm fails."""

    def test_paper_is_default(self):
        """Default mode is paper trading."""
```

### Phase 3 Tests

```python
# test_status.py
class TestStatusCommand:
    def test_shows_running_status(self):
        """Status shows if bot is running."""

    def test_shows_positions(self):
        """Status shows open positions and P&L."""

    def test_json_output(self):
        """--json flag outputs valid JSON."""
```

---

## Migration Guide

### For Existing Users

1. **No immediate action required** - all existing commands continue to work
2. **Recommended**: Switch to new commands for cleaner UX:
   - `python -m polymarket_bot.main` → `python -m polymarket_bot start`
   - `python -m polymarket_bot.sync_positions` → `python -m polymarket_bot sync`

### For New Users

1. Run `python -m polymarket_bot bootstrap`
2. Edit configuration files
3. Run `python -m polymarket_bot start`

---

## Implementation Priority

| Phase | Priority | Effort | Impact |
|-------|----------|--------|--------|
| Phase 1: Auto Position Sync | HIGH | Medium | Fixes ghost positions bug |
| Phase 2: Single-Command Startup | HIGH | Medium | Major UX improvement |
| Phase 3: Status Command | MEDIUM | Low | Visibility improvement |
| Phase 4: Live/Paper Clarity | MEDIUM | Low | Safety improvement |
| Phase 5: Bootstrap | LOW | Low | Onboarding improvement |
| Phase 6: Dashboard Clarity | LOW | Low | Documentation |

**Recommended order:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

---

## Appendix: Environment Variables

### New Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SKIP_STARTUP_SYNC` | `false` | Skip position sync on startup |
| `POSITION_SYNC_INTERVAL` | `300` | Seconds between position syncs |
| `POSITION_SYNC_ENABLED` | `true` | Enable/disable auto position sync |
| `POSITION_SYNC_MISS_THRESHOLD` | `2` | Consecutive misses before closing |
| `LIVE_CONFIRM` | (unset) | Set to `1` to confirm live mode |
| `DASHBOARD_MODE` | `monitor` | Which dashboard(s) to run |

### Existing Variables (Unchanged)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `DRY_RUN` | `true` | Paper trading mode |
| `STRATEGY_NAME` | `high_prob_yes` | Strategy to use |
| `PRICE_THRESHOLD` | `0.95` | Price threshold for triggers |
| `POSITION_SIZE` | `20` | Position size in dollars |
| `DASHBOARD_ENABLED` | `true` | Enable dashboard |
| `DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind address |
| `DASHBOARD_PORT` | `5055` | Dashboard port |
