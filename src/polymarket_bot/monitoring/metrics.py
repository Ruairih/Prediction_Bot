"""
Metrics Collector for trading performance tracking.

Collects and calculates key trading metrics like win rate, P&L, and positions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


@dataclass
class TradingMetrics:
    """Summary of trading performance."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    position_count: int = 0
    capital_deployed: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsCollector:
    """
    Collects and calculates trading metrics.

    Queries the database to compute performance statistics.

    Usage:
        collector = MetricsCollector(db)

        # Get win rate
        win_rate = await collector.get_win_rate()

        # Get total P&L
        pnl = await collector.get_total_pnl()

        # Get all metrics
        metrics = await collector.get_all_metrics()
    """

    def __init__(
        self,
        db: Optional["Database"] = None,
        clob_client: Optional[object] = None,
    ) -> None:
        """
        Initialize the metrics collector.

        Args:
            db: Database connection
            clob_client: CLOB client for balance queries
        """
        self._db = db
        self._clob_client = clob_client

    async def get_win_rate(self) -> float:
        """
        Calculate win rate from closed positions.

        A win is a position with realized_pnl > 0.

        Returns:
            Win rate as a decimal (0.0 to 1.0)
        """
        if not self._db:
            return 0.0

        # Use net_pnl (schema column) instead of realized_pnl
        query = """
            SELECT
                COUNT(*) FILTER (WHERE net_pnl > 0) as wins,
                COUNT(*) as total
            FROM exit_events
        """
        result = await self._db.fetchrow(query)

        if not result or result["total"] == 0:
            return 0.0

        return float(result["wins"]) / float(result["total"])

    async def get_total_pnl(self) -> Decimal:
        """
        Calculate total realized P&L.

        Returns:
            Sum of all realized P&L from exit events
        """
        if not self._db:
            return Decimal("0")

        # Use net_pnl (schema column) instead of realized_pnl
        query = "SELECT COALESCE(SUM(net_pnl), 0) as total FROM exit_events"
        result = await self._db.fetchrow(query)

        if not result:
            return Decimal("0")

        return Decimal(str(result["total"]))

    async def get_unrealized_pnl(
        self,
        current_prices: Optional[Dict[str, Decimal]] = None,
    ) -> Decimal:
        """
        Calculate unrealized P&L from open positions.

        Args:
            current_prices: Dict of token_id -> current price (optional, uses stored values if None)

        Returns:
            Sum of unrealized P&L
        """
        if not self._db:
            return Decimal("0")

        # First, try to sum the stored unrealized_pnl from positions
        # This is more reliable as it's updated by the ingestion layer
        query_stored = """
            SELECT COALESCE(SUM(unrealized_pnl), 0) as total
            FROM positions
            WHERE status = 'open' AND unrealized_pnl IS NOT NULL
        """
        result = await self._db.fetchrow(query_stored)
        if result and result["total"] is not None and result["total"] != 0:
            return Decimal(str(result["total"]))

        # Fallback: calculate from current prices if provided
        if current_prices is None:
            return Decimal("0")

        query = """
            SELECT token_id, size, entry_price
            FROM positions
            WHERE status = 'open'
        """
        records = await self._db.fetch(query)

        total = Decimal("0")
        for r in records:
            token_id = r["token_id"]
            size = Decimal(str(r["size"]))
            entry_price = Decimal(str(r["entry_price"]))

            current = current_prices.get(token_id)
            if current is not None:
                total += size * (current - entry_price)

        return total

    async def get_position_count(self) -> int:
        """
        Count current open positions.

        Returns:
            Number of open positions
        """
        if not self._db:
            return 0

        query = "SELECT COUNT(*) as count FROM positions WHERE status = 'open'"
        result = await self._db.fetchrow(query)

        if not result:
            return 0

        return int(result["count"])

    async def get_capital_deployed(self) -> Decimal:
        """
        Calculate total capital in open positions.

        Returns:
            Sum of entry_cost for all open positions
        """
        if not self._db:
            return Decimal("0")

        query = """
            SELECT COALESCE(SUM(entry_cost), 0) as total
            FROM positions
            WHERE status = 'open'
        """
        result = await self._db.fetchrow(query)

        if not result:
            return Decimal("0")

        return Decimal(str(result["total"]))

    async def get_trade_count(self) -> int:
        """
        Count total trades (completed exit events).

        Returns:
            Number of exit events
        """
        if not self._db:
            return 0

        query = "SELECT COUNT(*) as count FROM exit_events"
        result = await self._db.fetchrow(query)

        if not result:
            return 0

        return int(result["count"])

    async def get_winning_trades(self) -> int:
        """
        Count winning trades.

        Returns:
            Number of trades with positive P&L
        """
        if not self._db:
            return 0

        query = "SELECT COUNT(*) as count FROM exit_events WHERE net_pnl > 0"
        result = await self._db.fetchrow(query)

        if not result:
            return 0

        return int(result["count"])

    async def get_losing_trades(self) -> int:
        """
        Count losing trades.

        Returns:
            Number of trades with negative P&L
        """
        if not self._db:
            return 0

        query = "SELECT COUNT(*) as count FROM exit_events WHERE net_pnl < 0"
        result = await self._db.fetchrow(query)

        if not result:
            return 0

        return int(result["count"])

    def get_available_balance(self) -> Decimal:
        """
        Get available USDC balance.

        Returns:
            Available balance
        """
        if not self._clob_client:
            return Decimal("0")

        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            result = self._clob_client.get_balance_allowance(params)
            balance_raw = Decimal(str(result.get("balance", "0")))
            return balance_raw / Decimal("1000000")  # Convert from micro-units
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Decimal("0")

    async def get_all_metrics(
        self,
        current_prices: Optional[Dict[str, Decimal]] = None,
    ) -> TradingMetrics:
        """
        Get all trading metrics.

        Args:
            current_prices: Dict of token_id -> current price for unrealized P&L

        Returns:
            TradingMetrics with all calculated values
        """
        total_trades = await self.get_trade_count()
        winning_trades = await self.get_winning_trades()
        losing_trades = await self.get_losing_trades()
        win_rate = await self.get_win_rate()
        realized_pnl = await self.get_total_pnl()
        unrealized_pnl = await self.get_unrealized_pnl(current_prices)
        position_count = await self.get_position_count()
        capital_deployed = await self.get_capital_deployed()
        available_balance = self.get_available_balance()

        return TradingMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=realized_pnl + unrealized_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            position_count=position_count,
            capital_deployed=capital_deployed,
            available_balance=available_balance,
        )

    async def get_metrics_by_period(
        self,
        days: int = 7,
    ) -> Dict[str, Decimal]:
        """
        Get metrics for a specific time period.

        Args:
            days: Number of days to look back

        Returns:
            Dict with period-specific metrics
        """
        if not self._db:
            return {
                "period_pnl": Decimal("0"),
                "period_trades": 0,
                "period_win_rate": 0.0,
            }

        # Calculate timestamp for period start
        now = datetime.now(timezone.utc)
        period_start = int((now.timestamp()) - (days * 24 * 60 * 60))

        query = """
            SELECT
                COALESCE(SUM(realized_pnl), 0) as period_pnl,
                COUNT(*) as period_trades,
                COUNT(*) FILTER (WHERE realized_pnl > 0) as period_wins
            FROM exit_events
            WHERE exit_time > $1
        """
        result = await self._db.fetchrow(query, period_start)

        if not result or result["period_trades"] == 0:
            return {
                "period_pnl": Decimal("0"),
                "period_trades": 0,
                "period_win_rate": 0.0,
            }

        win_rate = float(result["period_wins"]) / float(result["period_trades"])

        return {
            "period_pnl": Decimal(str(result["period_pnl"])),
            "period_trades": int(result["period_trades"]),
            "period_win_rate": win_rate,
        }
