"""
Repository exports.

All repositories for the Polymarket trading bot.
"""
from polymarket_bot.storage.repositories.approval_repo import (
    ApprovalAlertRepository,
    TradeApprovalRepository,
)
from polymarket_bot.storage.repositories.candidate_repo import (
    CandidateRepository,
    CandidateWatermarkRepository,
)
from polymarket_bot.storage.repositories.market_repo import (
    ResolutionRepository,
    StreamWatchlistRepository,
    TokenMetaRepository,
)
from polymarket_bot.storage.repositories.order_repo import (
    LiveOrderRepository,
    PaperTradeRepository,
)
from polymarket_bot.storage.repositories.position_repo import (
    DailyPnlRepository,
    ExitEventRepository,
    PositionRepository,
)
from polymarket_bot.storage.repositories.trade_repo import (
    TradeRepository,
    TradeWatermarkRepository,
)
from polymarket_bot.storage.repositories.trigger_repo import (
    TriggerRepository,
    TriggerWatermarkRepository,
)
from polymarket_bot.storage.repositories.watchlist_repo import (
    MarketScoresCacheRepository,
    ScoreHistoryRepository,
    TradeWatchlistRepository,
)
# Tiered Data Architecture
from polymarket_bot.storage.repositories.universe_repo import (
    MarketQuery,
    MarketUniverseRepository,
)
from polymarket_bot.storage.repositories.candle_repo import (
    CandleRepository,
    OrderbookRepository,
)

__all__ = [
    # Trades
    "TradeRepository",
    "TradeWatermarkRepository",
    # Triggers
    "TriggerRepository",
    "TriggerWatermarkRepository",
    # Candidates
    "CandidateRepository",
    "CandidateWatermarkRepository",
    # Orders
    "LiveOrderRepository",
    "PaperTradeRepository",
    # Positions
    "PositionRepository",
    "ExitEventRepository",
    "DailyPnlRepository",
    # Approvals
    "TradeApprovalRepository",
    "ApprovalAlertRepository",
    # Markets
    "StreamWatchlistRepository",
    "ResolutionRepository",
    "TokenMetaRepository",
    # Watchlist & Scoring
    "TradeWatchlistRepository",
    "MarketScoresCacheRepository",
    "ScoreHistoryRepository",
    # Tiered Data Architecture
    "MarketUniverseRepository",
    "MarketQuery",
    "CandleRepository",
    "OrderbookRepository",
]
