"""
Polymarket Trading Bot - Main Entry Point

This is the main entry point for running the trading bot.

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
    DATABASE_URL          PostgreSQL connection string
    POLYMARKET_CREDS_PATH Path to polymarket_api_creds.json
    TELEGRAM_BOT_TOKEN    Telegram bot token for alerts
    TELEGRAM_CHAT_ID      Telegram chat ID for alerts
    LOG_LEVEL             Logging level (DEBUG/INFO/WARNING/ERROR)
    DRY_RUN               Set to "true" to enable paper trading mode
    PRICE_THRESHOLD       Price threshold for triggers (default: 0.95)
    POSITION_SIZE         Position size in dollars (default: 20)
    MAX_POSITIONS         Maximum concurrent positions (default: 50)

Services:
    - ingestion: WebSocket connection, market data sync
    - engine: Trading logic, strategy evaluation
    - monitor: Health checks, dashboard, alerts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

# Configure logging before imports
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Complete bot configuration."""

    # Database
    database_url: str = ""

    # Trading parameters
    dry_run: bool = True
    price_threshold: Decimal = Decimal("0.95")
    position_size: Decimal = Decimal("20")
    max_positions: int = 50
    max_price_deviation: Decimal = Decimal("0.10")

    # Ingestion
    websocket_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    max_trade_age_seconds: int = 300  # G1 protection

    # Monitoring
    dashboard_enabled: bool = True
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 5050

    # Alerts
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Polymarket credentials
    clob_credentials: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load configuration from environment variables."""
        config = cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            dry_run=os.environ.get("DRY_RUN", "true").lower() == "true",
            price_threshold=Decimal(os.environ.get("PRICE_THRESHOLD", "0.95")),
            position_size=Decimal(os.environ.get("POSITION_SIZE", "20")),
            max_positions=int(os.environ.get("MAX_POSITIONS", "50")),
            max_price_deviation=Decimal(os.environ.get("MAX_PRICE_DEVIATION", "0.10")),
            max_trade_age_seconds=int(os.environ.get("MAX_TRADE_AGE_SECONDS", "300")),
            dashboard_enabled=os.environ.get("DASHBOARD_ENABLED", "true").lower() == "true",
            dashboard_host=os.environ.get("DASHBOARD_HOST", "0.0.0.0"),
            dashboard_port=int(os.environ.get("DASHBOARD_PORT", "5050")),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
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

        # Components (initialized on start)
        self._db = None
        self._ingestion = None
        self._engine = None
        self._health_checker = None
        self._alert_manager = None
        self._clob_client = None

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
        self._shutdown_event.clear()

        # Setup signal handlers FIRST to catch early signals
        self._setup_signal_handlers()

        try:
            # Always initialize database
            await self._init_database()

            # Initialize engine BEFORE ingestion so we don't lose early events
            if mode in ("all", "engine"):
                await self._init_engine()

            # Initialize ingestion AFTER engine is ready
            if mode in ("all", "ingestion"):
                await self._init_ingestion()

            if mode in ("all", "monitor"):
                await self._init_monitoring()

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

        if self._db:
            try:
                await self._db.close()
            except Exception as e:
                logger.warning(f"Error closing database: {e}")

        logger.info("Shutdown complete")

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
        )

        self._ingestion = IngestionService(
            config=ingestion_config,
            on_price_update=self._handle_price_update,
        )

        await self._ingestion.start()
        logger.info("Ingestion: Started")

    async def _init_engine(self) -> None:
        """Initialize trading engine."""
        from polymarket_bot.core import TradingEngine, EngineConfig

        # Initialize CLOB client if credentials available
        if self.config.clob_credentials and not self.config.dry_run:
            self._clob_client = self._create_clob_client()

        engine_config = EngineConfig(
            price_threshold=self.config.price_threshold,
            position_size=self.config.position_size,
            max_positions=self.config.max_positions,
            dry_run=self.config.dry_run,
            max_price_deviation=self.config.max_price_deviation,
        )

        self._engine = TradingEngine(
            config=engine_config,
            db=self._db,
            clob_client=self._clob_client,
        )

        await self._engine.start()
        logger.info("Engine: Started")

    async def _init_monitoring(self) -> None:
        """Initialize monitoring components."""
        from polymarket_bot.monitoring import (
            HealthChecker,
            AlertManager,
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

        logger.info("Monitoring: Initialized")

    def _create_clob_client(self) -> Any:
        """Create Polymarket CLOB client."""
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

        except ImportError:
            logger.warning("py-clob-client not installed, running in dry-run mode")
            return None
        except Exception as e:
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
                    health = await self._health_checker.check_all()

                    if not health.is_healthy:
                        logger.warning(f"Health degraded: {health.summary}")

                        if self._alert_manager:
                            for component in health.components:
                                if component.status.value == "unhealthy":
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
                        f"executed={stats.orders_executed}, "
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

    # Run async main
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
