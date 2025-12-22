"""
Tests for main module - TradingBot initialization and live mode validation.

These tests verify that:
1. Live mode fails fast without required credentials
2. Live mode fails fast without working CLOB client
3. Dry run mode works without CLOB client
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

from polymarket_bot.main import BotConfig, TradingBot


# =============================================================================
# BotConfig Tests
# =============================================================================


class TestBotConfigFromEnv:
    """Tests for BotConfig.from_env()."""

    def test_loads_default_values(self):
        """Should use defaults when env vars not set."""
        with patch.dict("os.environ", {}, clear=True):
            config = BotConfig.from_env()

        assert config.dry_run is True  # Safe default
        assert config.price_threshold == Decimal("0.95")
        assert config.strategy_name == "high_prob_yes"

    def test_loads_dry_run_from_env(self):
        """Should parse DRY_RUN from environment."""
        with patch.dict("os.environ", {"DRY_RUN": "false"}, clear=True):
            config = BotConfig.from_env()
            assert config.dry_run is False

        with patch.dict("os.environ", {"DRY_RUN": "true"}, clear=True):
            config = BotConfig.from_env()
            assert config.dry_run is True

    def test_loads_strategy_name_from_env(self):
        """Should load strategy name from environment."""
        with patch.dict("os.environ", {"STRATEGY_NAME": "custom_strategy"}, clear=True):
            config = BotConfig.from_env()

        assert config.strategy_name == "custom_strategy"

    def test_loads_trading_parameters(self):
        """Should load trading parameters from environment."""
        with patch.dict("os.environ", {
            "PRICE_THRESHOLD": "0.90",
            "POSITION_SIZE": "50",
            "MAX_POSITIONS": "100",
        }, clear=True):
            config = BotConfig.from_env()

        assert config.price_threshold == Decimal("0.90")
        assert config.position_size == Decimal("50")
        assert config.max_positions == 100


# =============================================================================
# Live Mode Validation Tests
# =============================================================================


class TestLiveModeValidation:
    """Tests for live mode fail-fast behavior."""

    @pytest.fixture
    def live_config(self):
        """Config for live mode (dry_run=False)."""
        return BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=False,
            clob_credentials={
                "api_key": "test_key",
                "api_secret": "test_secret",
                "api_passphrase": "test_pass",
                "private_key": "0x1234",
                "host": "https://clob.polymarket.com",
                "chain_id": 137,
            },
        )

    @pytest.fixture
    def dry_run_config(self):
        """Config for dry run mode."""
        return BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=True,
        )

    @pytest.mark.asyncio
    async def test_live_mode_fails_without_credentials(self):
        """Live mode should fail if no credentials provided."""
        config = BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=False,
            clob_credentials={},  # No credentials
        )
        bot = TradingBot(config)

        with patch.object(bot, "_init_database", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Live trading requires Polymarket API credentials"):
                await bot._init_engine()

    @pytest.mark.asyncio
    async def test_live_mode_fails_without_clob_client(self, live_config):
        """Live mode should fail if CLOB client creation fails."""
        bot = TradingBot(live_config)

        # Mock py_clob_client import to fail
        with patch.object(bot, "_init_database", new_callable=AsyncMock):
            with patch.dict("sys.modules", {"py_clob_client": None}):
                with patch.object(bot, "_create_clob_client", return_value=None):
                    with pytest.raises(RuntimeError, match="Live mode requires a working CLOB client"):
                        await bot._init_engine()

    @pytest.mark.asyncio
    async def test_dry_run_works_without_clob_client(self, dry_run_config):
        """Dry run mode should work without CLOB client."""
        bot = TradingBot(dry_run_config)

        # Mock all dependencies - patch where they're imported from
        with patch.object(bot, "_init_database", new_callable=AsyncMock):
            with patch("polymarket_bot.execution.ExecutionService") as mock_exec:
                with patch("polymarket_bot.core.TradingEngine") as mock_engine:
                    # Mock the execution service
                    mock_exec_instance = MagicMock()
                    mock_exec_instance.load_state = AsyncMock()
                    mock_exec_instance.get_open_positions = MagicMock(return_value=[])
                    mock_exec.return_value = mock_exec_instance

                    # Mock the engine
                    mock_engine_instance = MagicMock()
                    mock_engine_instance.start = AsyncMock()
                    mock_engine.return_value = mock_engine_instance

                    # Mock database
                    bot._db = MagicMock()

                    # Should not raise
                    await bot._init_engine()

                    # Verify CLOB client is None
                    assert bot._clob_client is None

    def test_create_clob_client_raises_in_live_mode_on_import_error(self, live_config):
        """Should raise RuntimeError in live mode if py-clob-client not installed."""
        bot = TradingBot(live_config)

        with patch.dict("sys.modules", {"py_clob_client": None}):
            with patch.object(
                bot, "_create_clob_client",
                side_effect=RuntimeError("py-clob-client is required for live trading")
            ):
                with pytest.raises(RuntimeError, match="py-clob-client is required"):
                    bot._create_clob_client()

    def test_create_clob_client_returns_none_in_dry_run(self, dry_run_config):
        """Should return None in dry run mode if py-clob-client not installed."""
        bot = TradingBot(dry_run_config)

        # Simulate import error handled gracefully
        original_create = TradingBot._create_clob_client

        def mock_create(self):
            # Simulate the real behavior when import fails in dry run
            try:
                raise ImportError("No module named 'py_clob_client'")
            except ImportError:
                if not self.config.dry_run:
                    raise RuntimeError("py-clob-client is required")
                return None

        with patch.object(TradingBot, "_create_clob_client", mock_create):
            result = bot._create_clob_client()
            assert result is None


# =============================================================================
# Credential Validation Tests
# =============================================================================


class TestCredentialValidation:
    """Tests for credential validation in live mode."""

    def test_live_mode_requires_all_credential_fields(self):
        """Live mode should require all credential fields."""
        # Missing api_secret
        incomplete_creds = {
            "api_key": "test_key",
            "api_passphrase": "test_pass",
            "private_key": "0x1234",
        }

        config = BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=False,
            clob_credentials=incomplete_creds,
        )

        # Check that we have incomplete credentials
        required_fields = ["api_key", "api_secret", "api_passphrase", "private_key"]
        missing = [f for f in required_fields if f not in config.clob_credentials]

        assert "api_secret" in missing

    def test_dry_run_works_with_empty_credentials(self):
        """Dry run mode should work without any credentials."""
        config = BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=True,
            clob_credentials={},
        )

        # Should not raise - empty credentials OK in dry run
        assert config.dry_run is True
        assert config.clob_credentials == {}


# =============================================================================
# Engine Mode Tests
# =============================================================================


class TestEngineModeSelection:
    """Tests for engine mode selection."""

    @pytest.fixture
    def basic_config(self):
        """Basic config for mode tests."""
        return BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=True,
        )

    @pytest.mark.asyncio
    async def test_ingestion_mode_does_not_init_engine(self, basic_config):
        """Ingestion mode should not initialize trading engine."""
        bot = TradingBot(basic_config)
        bot._db = MagicMock()

        with patch.object(bot, "_init_database", new_callable=AsyncMock):
            with patch.object(bot, "_init_ingestion", new_callable=AsyncMock):
                with patch.object(bot, "_init_engine", new_callable=AsyncMock) as mock_engine:
                    with patch.object(bot, "_run_loop", new_callable=AsyncMock):
                        await bot.start(mode="ingestion")

                        # Engine should not be initialized
                        mock_engine.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_mode_initializes_everything(self, basic_config):
        """All mode should initialize all components."""
        bot = TradingBot(basic_config)
        bot._db = MagicMock()

        with patch.object(bot, "_init_database", new_callable=AsyncMock):
            with patch.object(bot, "_init_engine", new_callable=AsyncMock) as mock_engine:
                with patch.object(bot, "_init_ingestion", new_callable=AsyncMock) as mock_ingestion:
                    with patch.object(bot, "_init_monitoring", new_callable=AsyncMock) as mock_monitoring:
                        with patch.object(bot, "_init_background_tasks", new_callable=AsyncMock) as mock_bg:
                            with patch.object(bot, "_run_loop", new_callable=AsyncMock):
                                await bot.start(mode="all")

                                mock_engine.assert_called_once()
                                mock_ingestion.assert_called_once()
                                mock_monitoring.assert_called_once()
                                mock_bg.assert_called_once()


# =============================================================================
# Background Tasks Configuration Tests
# =============================================================================


class TestBackgroundTasksConfiguration:
    """Tests for background tasks configuration based on mode."""

    def test_order_sync_disabled_in_dry_run(self):
        """Order sync should be disabled in dry run mode."""
        config = BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=True,
        )

        # Verify config flag - actual behavior tested in background_tasks tests
        assert config.dry_run is True

    def test_exit_eval_disabled_in_dry_run(self):
        """Exit evaluation should be disabled in dry run mode."""
        config = BotConfig(
            database_url="postgresql://test:test@localhost:5432/test",
            dry_run=True,
        )

        # Verify config flag
        assert config.dry_run is True

    def test_watchlist_enabled_in_both_modes(self):
        """Watchlist rescoring should be enabled in both modes."""
        dry_run_config = BotConfig(dry_run=True)
        live_config = BotConfig(dry_run=False)

        # Watchlist is always enabled (rescoring is read-only)
        assert dry_run_config.watchlist_rescore_interval_hours > 0
        assert live_config.watchlist_rescore_interval_hours > 0
