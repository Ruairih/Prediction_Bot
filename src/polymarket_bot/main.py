"""
Polymarket Trading Bot - Main Entry Point

This is the main entry point for running the trading bot.
The bot is strategy-agnostic - strategies are loaded from a registry.

Usage:
    python -m polymarket_bot.main [--dry-run] [--config CONFIG_PATH]
    python -m polymarket_bot.main --mode ingestion  # Run only ingestion
    python -m polymarket_bot.main --mode monitor    # Run only monitoring
    python -m polymarket_bot.main --mode all        # Run full system (default)

Configuration:
    The bot reads configuration from:
    1. Environment variables (see .env.example)
    2. polymarket_api_creds.json for CLOB API credentials
    3. Command line arguments

Environment Variables:
    DATABASE_URL              PostgreSQL connection string (required)
    POLYMARKET_CREDS_PATH     Path to polymarket_api_creds.json
    TELEGRAM_BOT_TOKEN        Telegram bot token for alerts
    TELEGRAM_CHAT_ID          Telegram chat ID for alerts
    LOG_LEVEL                 Logging level (DEBUG/INFO/WARNING/ERROR)
    DRY_RUN                   Set to "true" for paper trading (default: true)
    STRATEGY_NAME             Strategy to use from registry (default: high_prob_yes)
    PRICE_THRESHOLD           Price threshold for triggers (default: 0.95)
    POSITION_SIZE             Position size in dollars (default: 20)
    MAX_POSITIONS             Maximum concurrent positions (default: 50)
    MAX_PRICE_DEVIATION       Max orderbook deviation allowed (default: 0.10)
    MIN_BALANCE_RESERVE       Minimum balance to keep reserved (default: 100)
    PROFIT_TARGET             Exit at this price for long positions (default: 0.99)
    STOP_LOSS                 Stop loss exit price (default: 0.90)
    MIN_HOLD_DAYS             Days before applying exit strategy (default: 7)
    WATCHLIST_RESCORE_INTERVAL_HOURS  Interval for watchlist rescoring (default: 1.0)

Live Mode Requirements:
    When DRY_RUN=false, the bot requires:
    - Valid polymarket_api_creds.json with all required fields
    - py-clob-client package installed
    - CLOB client must successfully initialize
    The bot will fail fast if any of these are missing.

Services:
    - ingestion: WebSocket connection, market data sync
    - engine: Trading logic, strategy evaluation
    - monitor: Health checks, dashboard, alerts
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import fcntl
import json
import logging
import os
import signal
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Generator

# Configure logging before imports
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default PID file location
DEFAULT_PID_FILE = "/tmp/polymarket-bot.pid"


class SingletonBotError(Exception):
    """Raised when another bot instance is already running."""
    pass


@contextmanager
def singleton_lock(pid_file: str = DEFAULT_PID_FILE) -> Generator[None, None, None]:
    """
    Context manager that ensures only one bot instance runs at a time.

    Uses file locking (fcntl.LOCK_EX | fcntl.LOCK_NB) to prevent multiple instances.
    The lock is automatically released when the process exits.

    Args:
        pid_file: Path to the PID file (default: /tmp/polymarket-bot.pid)

    Raises:
        SingletonBotError: If another instance is already running

    Usage:
        with singleton_lock():
            # Only one instance can run this code at a time
            run_bot()
    """
    pid_path = Path(pid_file)

    # Read existing PID before opening (which would truncate)
    existing_pid = None
    try:
        existing_pid = pid_path.read_text().strip()
    except FileNotFoundError:
        pass

    # Open/create the PID file (use "a" to avoid truncating before we have the lock)
    fp = open(pid_path, "a+")

    try:
        # Try to acquire exclusive lock (non-blocking)
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # Another instance has the lock
        fp.close()
        if existing_pid:
            raise SingletonBotError(
                f"Another bot instance is already running (PID: {existing_pid}). "
                f"Kill it with: kill {existing_pid}"
            )
        else:
            raise SingletonBotError(
                "Another bot instance is already running. "
                f"Check for existing processes: ps aux | grep polymarket"
            )

    # We have the lock - now truncate and write our PID
    fp.seek(0)
    fp.truncate()
    fp.write(str(os.getpid()))
    fp.flush()

    # Register cleanup on exit
    def cleanup():
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
            fp.close()
            pid_path.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(cleanup)

    try:
        logger.info(f"Acquired singleton lock (PID: {os.getpid()}, file: {pid_file})")
        yield
    finally:
        cleanup()
        atexit.unregister(cleanup)


@dataclass
class BotConfig:
    """Complete bot configuration."""

    # Database
    database_url: str = ""

    # Strategy (generic bot - configurable strategy)
    strategy_name: str = "high_prob_yes"  # Default strategy

    # Trading parameters
    dry_run: bool = True
    price_threshold: Decimal = Decimal("0.95")
    position_size: Decimal = Decimal("20")
    max_positions: int = 50
    max_price_deviation: Decimal = Decimal("0.10")

    # Execution
    min_balance_reserve: Decimal = Decimal("100")
    profit_target: Decimal = Decimal("0.99")
    stop_loss: Decimal = Decimal("0.90")
    min_hold_days: int = 7

    # Background tasks
    watchlist_rescore_interval_hours: float = 1.0

    # Ingestion
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    max_trade_age_seconds: int = 300  # G1 protection

    # Monitoring - See G11 in docs/reference/known_gotchas.md for Docker/Tailscale setup
    # Set DASHBOARD_HOST=0.0.0.0 to expose on network (required for Docker/Tailscale)
    dashboard_enabled: bool = True
    dashboard_host: str = "0.0.0.0"  # 0.0.0.0 for Docker/Tailscale, 127.0.0.1 for local only
    dashboard_port: int = 9050  # Use a port FREE on host (not 5050, often in use)

    # Alerts
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Position sync configuration
    sync_positions_on_startup: bool = True
    startup_sync_hold_policy: str = "new"  # "new", "mature", or "actual"

    # Background position sync (detects external trades)
    position_sync_enabled: bool = True
    position_sync_interval_seconds: float = 120  # Quick sync every 2 minutes
    full_position_sync_interval_seconds: float = 900  # Full sync every 15 minutes

    # Polymarket credentials
    clob_credentials: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables."""
        config = cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            strategy_name=os.environ.get("STRATEGY_NAME", "high_prob_yes"),
            dry_run=os.environ.get("DRY_RUN", "true").lower() == "true",
            price_threshold=Decimal(os.environ.get("PRICE_THRESHOLD", "0.95")),
            position_size=Decimal(os.environ.get("POSITION_SIZE", "20")),
            max_positions=int(os.environ.get("MAX_POSITIONS", "50")),
            max_price_deviation=Decimal(os.environ.get("MAX_PRICE_DEVIATION", "0.10")),
            min_balance_reserve=Decimal(os.environ.get("MIN_BALANCE_RESERVE", "100")),
            profit_target=Decimal(os.environ.get("PROFIT_TARGET", "0.99")),
            stop_loss=Decimal(os.environ.get("STOP_LOSS", "0.90")),
            min_hold_days=int(os.environ.get("MIN_HOLD_DAYS", "7")),
            watchlist_rescore_interval_hours=float(os.environ.get("WATCHLIST_RESCORE_INTERVAL_HOURS", "1.0")),
            max_trade_age_seconds=int(os.environ.get("MAX_TRADE_AGE_SECONDS", "300")),
            dashboard_enabled=os.environ.get("DASHBOARD_ENABLED", "true").lower() == "true",
            dashboard_host=os.environ.get("DASHBOARD_HOST", "0.0.0.0"),
            dashboard_port=int(os.environ.get("DASHBOARD_PORT", "9050")),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
            sync_positions_on_startup=os.environ.get("SYNC_POSITIONS_ON_STARTUP", "true").lower() == "true",
            startup_sync_hold_policy=os.environ.get("STARTUP_SYNC_HOLD_POLICY", "new"),
            position_sync_enabled=os.environ.get("POSITION_SYNC_ENABLED", "true").lower() == "true",
            position_sync_interval_seconds=float(os.environ.get("POSITION_SYNC_INTERVAL_SECONDS", "120")),
            full_position_sync_interval_seconds=float(os.environ.get("FULL_POSITION_SYNC_INTERVAL_SECONDS", "900")),
        )

        # Load CLOB credentials
        creds_path = Path(os.environ.get("POLYMARKET_CREDS_PATH", "polymarket_api_creds.json"))
        if creds_path.exists():
            try:
                with open(creds_path) as f:
                    config.clob_credentials = json.load(f)
                logger.info(f"Loaded Polymarket credentials from {creds_path}")
            except Exception as e:
                logger.warning(f"Failed to load credentials: {e}")

        return config


class TradingBot:
    """
    Main trading bot orchestrator.

    Manages the lifecycle of all components:
    - Database connection
    - Ingestion service (WebSocket, REST)
    - Trading engine (strategy evaluation)
    - Monitoring (health, alerts, dashboard)
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._started_at = None

        # Components (initialized on start)
        self._db = None
        self._ingestion = None
        self._engine = None
        self._strategy = None
        self._execution_service = None
        self._background_tasks = None
        self._health_checker = None
        self._alert_manager = None
        self._metrics_collector = None
        self._dashboard = None
        self._dashboard_thread = None
        self._flask_server = None
        self._clob_client = None
        # Tiered Data Architecture
        self._universe_updater = None

    async def start(self, mode: str = "all") -> None:
        """
        Start the trading bot.

        Args:
            mode: "all", "ingestion", "engine", or "monitor"
        """
        logger.info("=" * 60)
        logger.info("POLYMARKET TRADING BOT")
        logger.info("=" * 60)
        logger.info(f"Mode: {mode.upper()}")
        logger.info(f"Trading: {'DRY RUN' if self.config.dry_run else 'LIVE'}")
        logger.info("=" * 60)

        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._shutdown_event.clear()

        # Setup signal handlers FIRST to catch early signals
        self._setup_signal_handlers()

        try:
            # Always initialize database
            await self._init_database()

            # Check shutdown between init steps to abort early if signal received
            if self._shutdown_event.is_set():
                logger.info("Shutdown requested during startup")
                return

            # Initialize engine BEFORE ingestion so we don't lose early events
            if mode in ("all", "engine"):
                await self._init_engine()

            if self._shutdown_event.is_set():
                logger.info("Shutdown requested during startup")
                return

            # Initialize ingestion AFTER engine is ready
            if mode in ("all", "ingestion"):
                await self._init_ingestion()

            if self._shutdown_event.is_set():
                logger.info("Shutdown requested during startup")
                return

            # Initialize tiered data architecture (universe fetching)
            if mode in ("all", "ingestion"):
                await self._init_universe_updater()

            if self._shutdown_event.is_set():
                logger.info("Shutdown requested during startup")
                return

            if mode in ("all", "monitor"):
                await self._init_monitoring()

            if self._shutdown_event.is_set():
                logger.info("Shutdown requested during startup")
                return

            # Start background tasks for engine mode
            if mode in ("all", "engine"):
                await self._init_background_tasks()

            logger.info("=" * 60)
            logger.info("Bot started successfully")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 60)

            # Run until shutdown
            await self._run_loop(mode)

        except Exception as e:
            logger.exception(f"Fatal error: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the trading bot gracefully."""
        if not self._running:
            return

        logger.info("Shutting down...")
        self._running = False
        self._shutdown_event.set()

        # Stop components in reverse order
        if self._background_tasks:
            try:
                await self._background_tasks.stop()
            except Exception as e:
                logger.warning(f"Error stopping background tasks: {e}")

        if self._universe_updater:
            try:
                await self._universe_updater.stop()
            except Exception as e:
                logger.warning(f"Error stopping universe updater: {e}")

        if self._ingestion:
            try:
                await self._ingestion.stop()
            except Exception as e:
                logger.warning(f"Error stopping ingestion: {e}")

        if self._engine:
            try:
                await self._engine.stop()
            except Exception as e:
                logger.warning(f"Error stopping engine: {e}")

        # Stop dashboard before database (dashboard may need DB during shutdown)
        if self._dashboard:
            try:
                self._stop_dashboard()
            except Exception as e:
                logger.warning(f"Error stopping dashboard: {e}")

        if self._db:
            try:
                await self._db.close()
            except Exception as e:
                logger.warning(f"Error closing database: {e}")

        logger.info("Shutdown complete")

    async def request_shutdown(self, reason: str = "manual") -> None:
        """Request a graceful shutdown from another thread."""
        if not self._running:
            return
        logger.warning(f"Shutdown requested: {reason}")
        self._running = False
        self._shutdown_event.set()

    async def _init_database(self) -> None:
        """Initialize database connection."""
        from polymarket_bot.storage import Database, DatabaseConfig

        if not self.config.database_url:
            raise ValueError("DATABASE_URL environment variable is required")

        db_config = DatabaseConfig(url=self.config.database_url)
        self._db = Database(db_config)
        await self._db.initialize()

        # Verify connection
        if not await self._db.health_check():
            raise RuntimeError("Database health check failed")

        logger.info("Database: Connected")

    async def _init_ingestion(self) -> None:
        """Initialize ingestion service."""
        from polymarket_bot.ingestion import (
            IngestionService,
            IngestionConfig,
        )

        ingestion_config = IngestionConfig(
            websocket_url=self.config.websocket_url,
            max_trade_age_seconds=self.config.max_trade_age_seconds,
            dashboard_enabled=False,  # Dashboard runs separately
            subscribe_all_markets=True,
            backfill_missing_size=False,  # Disabled: /trades endpoint requires auth
        )

        self._ingestion = IngestionService(
            config=ingestion_config,
            on_price_update=self._handle_price_update,
            db=self._db,
        )

        await self._ingestion.start()
        logger.info("Ingestion: Started")

    async def _init_universe_updater(self) -> None:
        """Initialize the tiered data architecture universe updater.

        This background service:
        - Fetches all ~10k markets from Polymarket every 5 minutes
        - Computes interestingness scores for strategy-agnostic ranking
        - Manages tier promotion/demotion (Universe → History → Trades)
        - Provides market discovery for any strategy
        """
        from polymarket_bot.storage.repositories.universe_repo import MarketUniverseRepository
        from polymarket_bot.storage.repositories.position_repo import PositionRepository
        from polymarket_bot.storage.repositories.order_repo import LiveOrderRepository
        from polymarket_bot.ingestion.universe_fetcher import UniverseFetcher, UniverseUpdater
        from polymarket_bot.core.tier_manager import TierManager

        # Create repositories
        universe_repo = MarketUniverseRepository(self._db)
        position_repo = PositionRepository(self._db)
        order_repo = LiveOrderRepository(self._db)

        # Create tier manager
        tier_manager = TierManager(
            universe_repo=universe_repo,
            position_repo=position_repo,
            order_repo=order_repo,
        )

        # Create fetcher
        fetcher = UniverseFetcher(universe_repo=universe_repo)

        # Create and start updater
        self._universe_updater = UniverseUpdater(
            fetcher=fetcher,
            tier_manager=tier_manager,
            universe_repo=universe_repo,
            fetch_interval=300,  # 5 minutes
            tier_interval=900,   # 15 minutes
        )

        await self._universe_updater.start()
        logger.info("Universe Updater: Started (tiered data architecture)")

    async def _init_engine(self) -> None:
        """Initialize trading engine with strategy and execution service."""
        from polymarket_bot.core import TradingEngine, EngineConfig
        from polymarket_bot.execution import ExecutionService, ExecutionConfig
        from polymarket_bot.strategies import (
            get_default_registry,
            HighProbYesStrategy,
            StrategyNotFoundError,
        )

        # Load strategy from registry (generic bot - configurable strategy)
        registry = get_default_registry()

        # Register built-in strategies if not already registered
        if "high_prob_yes" not in registry:
            registry.register(HighProbYesStrategy())

        try:
            self._strategy = registry.get(self.config.strategy_name)
            logger.info(f"Strategy: Loaded '{self._strategy.name}'")
        except StrategyNotFoundError:
            available = registry.list_all()
            logger.error(
                f"Strategy '{self.config.strategy_name}' not found. "
                f"Available: {available or '(none registered)'}"
            )
            raise

        # Initialize CLOB client
        if not self.config.dry_run:
            # LIVE MODE: Require credentials
            if not self.config.clob_credentials:
                raise RuntimeError(
                    "Live trading requires Polymarket API credentials. "
                    "Set POLYMARKET_CREDS_PATH or create polymarket_api_creds.json"
                )

            self._clob_client = self._create_clob_client()

            # LIVE MODE: Verify CLOB client was created successfully
            if self._clob_client is None:
                raise RuntimeError(
                    "Live mode requires a working CLOB client. "
                    "Check your credentials in polymarket_api_creds.json"
                )

        # Create ExecutionService for order management
        # G12 FIX: Include wallet_address for position size sync before exits
        wallet_address = None
        if self.config.clob_credentials:
            wallet_address = self.config.clob_credentials.get("funder")
            if wallet_address:
                logger.info(f"G12: Position sync enabled for wallet {wallet_address[:10]}...")
            else:
                logger.warning("G12: No 'funder' in credentials, position sync disabled")

        # max_price allows for G5-approved deviation above trigger threshold
        # If we trigger at 0.95 and allow 0.10 deviation, max_price should be min(1.05, 1.0) = 1.0
        max_price = min(
            self.config.price_threshold + self.config.max_price_deviation,
            Decimal("1.0"),
        )
        exec_config = ExecutionConfig(
            max_price=max_price,
            default_position_size=self.config.position_size,
            min_balance_reserve=self.config.min_balance_reserve,
            profit_target=self.config.profit_target,
            stop_loss=self.config.stop_loss,
            min_hold_days=self.config.min_hold_days,
            wallet_address=wallet_address,
            sync_positions_on_startup=self.config.sync_positions_on_startup,
            startup_sync_hold_policy=self.config.startup_sync_hold_policy,
        )

        self._execution_service = ExecutionService(
            db=self._db,
            clob_client=self._clob_client,
            config=exec_config,
        )

        # Load existing positions on startup
        await self._execution_service.load_state()
        open_positions = self._execution_service.get_open_positions()
        logger.info(f"Execution: Loaded {len(open_positions)} open positions")

        # Create engine config
        engine_config = EngineConfig(
            price_threshold=self.config.price_threshold,
            position_size=self.config.position_size,
            max_positions=self.config.max_positions,
            dry_run=self.config.dry_run,
            max_price_deviation=self.config.max_price_deviation,
            max_trade_age_seconds=self.config.max_trade_age_seconds,
        )

        # Create TradingEngine with strategy and execution service
        self._engine = TradingEngine(
            config=engine_config,
            db=self._db,
            strategy=self._strategy,
            api_client=self._clob_client,
            execution_service=self._execution_service,
        )

        await self._engine.start()
        logger.info(f"Engine: Started (mode={'DRY RUN' if self.config.dry_run else 'LIVE'})")

    async def _init_monitoring(self) -> None:
        """Initialize monitoring components."""
        from polymarket_bot.monitoring import (
            HealthChecker,
            AlertManager,
            MetricsCollector,
            Dashboard,
        )

        # Health checker
        self._health_checker = HealthChecker(
            db=self._db,
            websocket_client=self._ingestion.websocket if self._ingestion else None,
            clob_client=self._clob_client,
        )

        # Alert manager
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            self._alert_manager = AlertManager(
                telegram_bot_token=self.config.telegram_bot_token,
                telegram_chat_id=self.config.telegram_chat_id,
            )
            logger.info("Alerts: Telegram configured")
        else:
            self._alert_manager = AlertManager()  # No-op alerts
            logger.info("Alerts: Disabled (no Telegram config)")

        # Metrics collector
        self._metrics_collector = MetricsCollector(
            db=self._db,
            clob_client=self._clob_client,
        )

        # Dashboard (Flask running in background thread)
        if self.config.dashboard_enabled:
            try:
                # Get current event loop for thread-safe async dispatch
                event_loop = asyncio.get_running_loop()

                self._dashboard = Dashboard(
                    db=self._db,
                    health_checker=self._health_checker,
                    metrics_collector=self._metrics_collector,
                    event_loop=event_loop,
                    engine=self._engine,
                    execution_service=self._execution_service,
                    bot_config=self.config,
                    shutdown_callback=self.request_shutdown,
                    started_at=self._started_at,
                )
                await self._dashboard.ensure_control_tables()
                await self._dashboard.load_blocklist()
                if self._execution_service:
                    self._execution_service.set_event_sink(self._dashboard.broadcast_event)
                self._start_dashboard()
            except ImportError as e:
                logger.warning(f"Dashboard disabled: {e}")
                self._dashboard = None
        else:
            self._dashboard = None
            logger.info("Dashboard: Disabled via config")

        logger.info("Monitoring: Initialized")

    def _start_dashboard(self) -> None:
        """Start the Flask dashboard in a background thread.

        Flask runs in a separate thread to avoid blocking the asyncio event loop.
        Uses werkzeug's threaded server with graceful shutdown support.
        """
        import threading
        from werkzeug.serving import make_server

        def run_flask():
            """Run Flask server in thread."""
            try:
                # Check shutdown flag before starting (race condition guard)
                if not self._running:
                    logger.info("Dashboard: Skipping start (shutdown in progress)")
                    return

                app = self._dashboard.create_app()

                # Create server with shutdown support
                self._flask_server = make_server(
                    host=self.config.dashboard_host,
                    port=self.config.dashboard_port,
                    app=app,
                    threaded=True,
                )

                # Double-check after server creation
                if not self._running:
                    self._flask_server.server_close()
                    logger.info("Dashboard: Skipping serve (shutdown in progress)")
                    return

                logger.info(
                    f"Dashboard: http://{self.config.dashboard_host}:{self.config.dashboard_port}"
                )

                # Serve until shutdown
                self._flask_server.serve_forever()

            except Exception as e:
                logger.error(f"Dashboard failed to start: {e}")

        self._dashboard_thread = threading.Thread(target=run_flask, daemon=True)
        self._dashboard_thread.start()

    def _stop_dashboard(self) -> None:
        """Stop the Flask dashboard gracefully."""
        if self._flask_server:
            logger.info("Dashboard: Shutting down...")
            # shutdown() stops serve_forever loop
            self._flask_server.shutdown()
            # server_close() releases the socket
            self._flask_server.server_close()
            self._flask_server = None

        if self._dashboard_thread:
            if self._dashboard_thread.is_alive():
                self._dashboard_thread.join(timeout=5)
                if self._dashboard_thread.is_alive():
                    logger.warning("Dashboard thread did not stop cleanly")
            self._dashboard_thread = None

    async def _init_background_tasks(self) -> None:
        """Initialize background task manager."""
        from polymarket_bot.core import BackgroundTasksManager, BackgroundTaskConfig
        from polymarket_bot.execution.position_sync import PositionSyncService

        config = BackgroundTaskConfig(
            watchlist_rescore_interval_seconds=self.config.watchlist_rescore_interval_hours * 3600,
            watchlist_enabled=True,
            order_sync_interval_seconds=30,
            order_sync_enabled=not self.config.dry_run,  # Only sync in live mode
            exit_eval_interval_seconds=60,
            exit_eval_enabled=not self.config.dry_run,  # Only eval exits in live mode
            # Position sync from Polymarket (detects external trades)
            position_sync_enabled=self.config.position_sync_enabled,
            position_sync_interval_seconds=self.config.position_sync_interval_seconds,
            full_position_sync_interval_seconds=self.config.full_position_sync_interval_seconds,
            full_position_sync_enabled=self.config.position_sync_enabled,
        )

        # Create price fetcher using ingestion layer if available
        price_fetcher = None
        if self._ingestion and hasattr(self._ingestion, 'rest_client'):
            price_fetcher = self._create_price_fetcher()

        # Create PositionSyncService for external trade detection
        position_sync_service = None
        wallet_address = None
        if self.config.position_sync_enabled and self.config.clob_credentials:
            wallet_address = self.config.clob_credentials.get("funder")
            if wallet_address:
                # Get position tracker from execution service
                position_tracker = None
                if self._execution_service:
                    position_tracker = self._execution_service._position_tracker

                position_sync_service = PositionSyncService(
                    db=self._db,
                    position_tracker=position_tracker,
                )
                logger.info(
                    f"Position sync: Enabled for wallet {wallet_address[:10]}... "
                    f"(quick={config.position_sync_interval_seconds}s, "
                    f"full={config.full_position_sync_interval_seconds}s)"
                )
            else:
                logger.warning(
                    "Position sync: No 'funder' in credentials. "
                    "External trades will not be detected."
                )

        self._background_tasks = BackgroundTasksManager(
            engine=self._engine,
            execution_service=self._execution_service,
            config=config,
            price_fetcher=price_fetcher,
            position_sync_service=position_sync_service,
            wallet_address=wallet_address,
        )

        await self._background_tasks.start()
        logger.info("Background tasks: Started")

    def _create_price_fetcher(self):
        """Create async price fetcher using ingestion REST client."""
        from decimal import Decimal

        async def fetch_prices(token_ids: list) -> dict:
            """Fetch current prices for given token IDs."""
            prices = {}
            if not self._ingestion or not hasattr(self._ingestion, 'rest_client'):
                return prices

            client = self._ingestion.rest_client
            for token_id in token_ids:
                try:
                    price = await client.get_price(token_id)
                    if price is not None:
                        prices[token_id] = price
                except Exception as e:
                    logger.debug(f"Could not fetch price for {token_id}: {e}")

            return prices

        return fetch_prices

    def _create_clob_client(self) -> Any:
        """
        Create Polymarket CLOB client.

        In live mode (dry_run=False), this method will raise an exception
        if the client cannot be created. In dry_run mode, failures are logged
        but return None.

        Raises:
            RuntimeError: In live mode, if py-clob-client is not installed
            RuntimeError: In live mode, if client initialization fails
        """
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            creds = self.config.clob_credentials
            api_creds = ApiCreds(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                api_passphrase=creds["api_passphrase"],
            )

            client = ClobClient(
                host=creds.get("host", "https://clob.polymarket.com"),
                chain_id=creds.get("chain_id", 137),
                key=creds.get("private_key"),
                creds=api_creds,
                signature_type=creds.get("signature_type", 2),
                funder=creds.get("funder"),
            )

            logger.info("CLOB Client: Connected")
            return client

        except ImportError as e:
            if not self.config.dry_run:
                # LIVE MODE: Fail fast - cannot trade without CLOB client
                raise RuntimeError(
                    "py-clob-client is required for live trading. "
                    "Install with: pip install py-clob-client"
                ) from e
            logger.warning("py-clob-client not installed, running in dry-run mode")
            return None

        except Exception as e:
            if not self.config.dry_run:
                # LIVE MODE: Fail fast - cannot trade without CLOB client
                raise RuntimeError(
                    f"Failed to create CLOB client for live trading: {e}"
                ) from e
            logger.error(f"Failed to create CLOB client: {e}")
            return None

    async def _handle_price_update(self, update) -> None:
        """Handle price update from ingestion."""
        if not self._running:
            return  # Shutdown in progress, don't process new events
        if not self._engine:
            logger.debug(f"Engine not ready, dropping update for {update.token_id}")
            return

        try:
            # Convert to engine event format
            event = {
                "type": "price_change",
                "token_id": update.token_id,
                "condition_id": getattr(update, "condition_id", ""),
                "price": str(update.price),
                "timestamp": update.timestamp.timestamp() if update.timestamp else None,
            }

            signal = await self._engine.process_event(event)

            if self._dashboard:
                self._dashboard.broadcast_event({
                    "type": "price",
                    "token_id": update.token_id,
                    "condition_id": getattr(update, "condition_id", ""),
                    "price": str(update.price),
                })

                if signal:
                    self._dashboard.broadcast_event({
                        "type": "signal",
                        "signal_type": signal.type.value,
                        "token_id": getattr(signal, "token_id", None),
                        "position_id": getattr(signal, "position_id", None),
                        "reason": getattr(signal, "reason", None),
                    })

            # Alert on significant signals
            if signal and self._alert_manager:
                if signal.type.value == "entry":
                    self._alert_manager.alert_trade_executed(
                        token_id=update.token_id,
                        side="BUY",
                        price=update.price,
                        size=self.config.position_size,
                    )

        except Exception as e:
            logger.error(f"Error processing price update: {e}")

    async def _run_loop(self, mode: str) -> None:
        """Main run loop."""
        health_check_interval = 30  # seconds
        last_health_check = 0

        while self._running:
            try:
                # Wait for shutdown or interval
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=health_check_interval,
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue with health checks

                # Periodic health check
                if self._health_checker:
                    from polymarket_bot.monitoring import HealthStatus
                    health = await self._health_checker.check_all()

                    # Only warn on UNHEALTHY (not DEGRADED/WARNING in DRY_RUN mode)
                    unhealthy_components = [
                        c for c in health.components
                        if c.status == HealthStatus.UNHEALTHY
                    ]

                    if unhealthy_components:
                        logger.warning(
                            f"Health check failed: {[c.component for c in unhealthy_components]}"
                        )

                        if self._alert_manager:
                            for component in unhealthy_components:
                                self._alert_manager.alert_health_issue(
                                    component=component.component,
                                    status=component.status,
                                    message=component.message,
                                )

                # Log stats periodically
                if self._engine:
                    stats = self._engine.stats
                    logger.info(
                        f"Stats: triggers={stats.triggers_evaluated}, "
                        f"executed={stats.entries_executed}, "
                        f"watchlist={stats.watchlist_additions}"
                    )

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def handle_signal(sig):
            logger.info(f"Received signal {sig}")
            self._running = False  # Stop processing new events immediately
            self._shutdown_event.set()

        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass


def load_env_file(path: str = ".env") -> None:
    """Load environment variables from .env file if it exists."""
    env_path = Path(path)
    if env_path.exists():
        logger.info(f"Loading environment from {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), value)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Polymarket Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in paper trading mode (no real orders)",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "ingestion", "engine", "monitor"],
        default="all",
        help="Which services to run (default: all)",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level",
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    """Async main function."""
    # Load configuration
    config = BotConfig.from_env()

    # Override with command line args
    if args.dry_run:
        config.dry_run = True

    # Validate configuration
    if not config.database_url:
        logger.error("DATABASE_URL environment variable is required")
        logger.error("See .env.example for configuration")
        return 1

    if not config.dry_run:
        if not config.clob_credentials:
            logger.error("Live trading requires Polymarket API credentials")
            logger.error("See polymarket_api_creds.json.example")
            return 1
        # Validate required credential fields
        required_fields = ["api_key", "api_secret", "api_passphrase", "private_key"]
        missing_fields = [f for f in required_fields if f not in config.clob_credentials]
        if missing_fields:
            logger.error(f"Missing required credential fields: {missing_fields}")
            return 1

    # Create and run bot
    bot = TradingBot(config)

    try:
        await bot.start(mode=args.mode)
        return 0
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    # Load .env file
    load_env_file()

    # Parse arguments
    args = parse_args()

    # Override log level if specified
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Ensure only one bot instance runs at a time
    try:
        with singleton_lock():
            # Run async main
            try:
                return asyncio.run(main_async(args))
            except KeyboardInterrupt:
                return 0
    except SingletonBotError as e:
        logger.error(str(e))
        print(f"\n❌ {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
