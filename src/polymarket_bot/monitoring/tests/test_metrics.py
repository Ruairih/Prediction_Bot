"""
Tests for metrics collection.

Metrics track trading performance over time.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from polymarket_bot.monitoring.metrics import MetricsCollector, TradingMetrics


class TestWinRateCalculation:
    """Tests for win rate calculation."""

    @pytest.mark.asyncio
    async def test_calculates_win_rate(self, mock_db):
        """Should calculate win rate from closed positions."""
        mock_db.fetchrow = AsyncMock(return_value={"wins": 2, "total": 3})
        collector = MetricsCollector(db=mock_db)

        win_rate = await collector.get_win_rate()

        # 2 wins out of 3
        assert win_rate == pytest.approx(0.667, rel=0.01)

    @pytest.mark.asyncio
    async def test_win_rate_zero_when_no_trades(self, mock_db):
        """Should return 0 when no trades."""
        mock_db.fetchrow = AsyncMock(return_value={"wins": 0, "total": 0})
        collector = MetricsCollector(db=mock_db)

        win_rate = await collector.get_win_rate()

        assert win_rate == 0.0

    @pytest.mark.asyncio
    async def test_win_rate_without_db(self):
        """Should return 0 without database."""
        collector = MetricsCollector(db=None)

        win_rate = await collector.get_win_rate()

        assert win_rate == 0.0


class TestPnLCalculation:
    """Tests for P&L calculation."""

    @pytest.mark.asyncio
    async def test_calculates_total_pnl(self, mock_db):
        """Should calculate total realized P&L."""
        mock_db.fetchrow = AsyncMock(return_value={"total": -17.20})
        collector = MetricsCollector(db=mock_db)

        total_pnl = await collector.get_total_pnl()

        assert total_pnl == Decimal("-17.20")

    @pytest.mark.asyncio
    async def test_total_pnl_zero_when_no_exits(self, mock_db):
        """Should return 0 when no exits."""
        mock_db.fetchrow = AsyncMock(return_value={"total": 0})
        collector = MetricsCollector(db=mock_db)

        total_pnl = await collector.get_total_pnl()

        assert total_pnl == Decimal("0")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_without_prices(self, mock_db):
        """Should return 0 without current prices."""
        collector = MetricsCollector(db=mock_db)

        unrealized = await collector.get_unrealized_pnl(current_prices=None)

        assert unrealized == Decimal("0")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_with_prices(self, mock_db):
        """Should calculate unrealized P&L with current prices."""
        mock_db.fetch = AsyncMock(return_value=[
            {"token_id": "tok_1", "size": 20, "entry_price": 0.95},
            {"token_id": "tok_2", "size": 10, "entry_price": 0.90},
        ])
        collector = MetricsCollector(db=mock_db)

        current_prices = {
            "tok_1": Decimal("0.99"),  # +$0.80 (20 * 0.04)
            "tok_2": Decimal("0.85"),  # -$0.50 (10 * -0.05)
        }

        unrealized = await collector.get_unrealized_pnl(current_prices)

        # 0.80 - 0.50 = 0.30
        assert unrealized == Decimal("0.30")


class TestPositionMetrics:
    """Tests for position-related metrics."""

    @pytest.mark.asyncio
    async def test_counts_active_positions(self, mock_db):
        """Should count current open positions."""
        mock_db.fetchrow = AsyncMock(return_value={"count": 5})
        collector = MetricsCollector(db=mock_db)

        count = await collector.get_position_count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_calculates_capital_deployed(self, mock_db):
        """Should calculate total capital in positions."""
        mock_db.fetchrow = AsyncMock(return_value={"total": 37.80})
        collector = MetricsCollector(db=mock_db)

        deployed = await collector.get_capital_deployed()

        assert deployed == Decimal("37.80")


class TestTradeMetrics:
    """Tests for trade count metrics."""

    @pytest.mark.asyncio
    async def test_counts_total_trades(self, mock_db):
        """Should count total completed trades."""
        mock_db.fetchrow = AsyncMock(return_value={"count": 10})
        collector = MetricsCollector(db=mock_db)

        count = await collector.get_trade_count()

        assert count == 10

    @pytest.mark.asyncio
    async def test_counts_winning_trades(self, mock_db):
        """Should count trades with positive P&L."""
        mock_db.fetchrow = AsyncMock(return_value={"count": 7})
        collector = MetricsCollector(db=mock_db)

        count = await collector.get_winning_trades()

        assert count == 7

    @pytest.mark.asyncio
    async def test_counts_losing_trades(self, mock_db):
        """Should count trades with negative P&L."""
        mock_db.fetchrow = AsyncMock(return_value={"count": 3})
        collector = MetricsCollector(db=mock_db)

        count = await collector.get_losing_trades()

        assert count == 3


class TestBalanceMetrics:
    """Tests for balance queries."""

    def test_gets_available_balance(self, mock_clob_client):
        """Should get balance from CLOB client."""
        collector = MetricsCollector(clob_client=mock_clob_client)

        balance = collector.get_available_balance()

        assert balance == Decimal("500.00")

    def test_balance_zero_without_client(self):
        """Should return 0 without CLOB client."""
        collector = MetricsCollector(clob_client=None)

        balance = collector.get_available_balance()

        assert balance == Decimal("0")

    def test_balance_handles_error(self):
        """Should return 0 on error."""
        failing_client = MagicMock()
        failing_client.get_balance.side_effect = Exception("API error")
        collector = MetricsCollector(clob_client=failing_client)

        balance = collector.get_available_balance()

        assert balance == Decimal("0")


class TestAggregateMetrics:
    """Tests for collecting all metrics."""

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, mock_db, mock_clob_client):
        """Should return complete TradingMetrics."""
        # Setup mocks for all queries
        async def mock_fetchrow(query, *args):
            if "wins" in query:
                return {"wins": 7, "total": 10}
            elif "SUM(realized_pnl)" in query:
                return {"total": 25.50}
            elif "COUNT" in query and "positions" in query:
                return {"count": 3}
            elif "SUM(entry_cost)" in query:
                return {"total": 57.00}
            elif "exit_events" in query:
                return {"count": 10}
            elif "realized_pnl > 0" in query:
                return {"count": 7}
            elif "realized_pnl < 0" in query:
                return {"count": 3}
            return {"count": 0, "total": 0}

        mock_db.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        mock_db.fetch = AsyncMock(return_value=[])

        collector = MetricsCollector(db=mock_db, clob_client=mock_clob_client)

        metrics = await collector.get_all_metrics()

        assert isinstance(metrics, TradingMetrics)
        assert metrics.win_rate == pytest.approx(0.7, rel=0.01)
        assert metrics.realized_pnl == Decimal("25.50")
        assert metrics.available_balance == Decimal("500.00")
        assert metrics.calculated_at is not None

    @pytest.mark.asyncio
    async def test_all_metrics_without_db(self, mock_clob_client):
        """Should return empty metrics without database."""
        collector = MetricsCollector(db=None, clob_client=mock_clob_client)

        metrics = await collector.get_all_metrics()

        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.available_balance == Decimal("500.00")


class TestPeriodMetrics:
    """Tests for time-period metrics."""

    @pytest.mark.asyncio
    async def test_metrics_by_period(self, mock_db):
        """Should calculate metrics for specified period."""
        mock_db.fetchrow = AsyncMock(return_value={
            "period_pnl": 15.00,
            "period_trades": 5,
            "period_wins": 4,
        })
        collector = MetricsCollector(db=mock_db)

        period_metrics = await collector.get_metrics_by_period(days=7)

        assert period_metrics["period_pnl"] == Decimal("15.00")
        assert period_metrics["period_trades"] == 5
        assert period_metrics["period_win_rate"] == 0.8

    @pytest.mark.asyncio
    async def test_period_metrics_no_trades(self, mock_db):
        """Should handle period with no trades."""
        mock_db.fetchrow = AsyncMock(return_value={
            "period_pnl": 0,
            "period_trades": 0,
            "period_wins": 0,
        })
        collector = MetricsCollector(db=mock_db)

        period_metrics = await collector.get_metrics_by_period(days=7)

        assert period_metrics["period_trades"] == 0
        assert period_metrics["period_win_rate"] == 0.0
