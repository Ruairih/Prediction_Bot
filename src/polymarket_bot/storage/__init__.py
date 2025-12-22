"""
Storage Layer - Async PostgreSQL database and repositories.

This is the foundation layer that all other components depend on.
Built on asyncpg for high-performance async database access.

Public API:
    Database, DatabaseConfig - Connection pool management

    Models (matching production schema seed/01_schema.sql and seed/02_tiered_data.sql):
        PolymarketTrade, TradeWatermark
        PolymarketFirstTrigger, TriggerWatermark
        PolymarketCandidate, CandidateWatermark
        LiveOrder, PaperTrade
        Position, ExitEvent, DailyPnl
        TradeApproval, ApprovalAlert
        StreamWatchlistItem, PolymarketResolution, PolymarketTokenMeta
        TradeWatchlistItem, MarketScoresCache, ScoreHistory

    Tiered Data Architecture Models:
        MarketUniverse, OutcomeToken - Full market record with multi-outcome support
        PriceSnapshot - Price history for change calculation
        PriceCandle - OHLCV candles for Tier 2 markets
        OrderbookSnapshot - Orderbook depth for Tier 3 markets
        StrategyTierRequest - Strategy requests for tier promotion

    Repositories:
        TradeRepository, TradeWatermarkRepository
        TriggerRepository, TriggerWatermarkRepository
        CandidateRepository, CandidateWatermarkRepository
        LiveOrderRepository, PaperTradeRepository
        PositionRepository, ExitEventRepository, DailyPnlRepository
        TradeApprovalRepository, ApprovalAlertRepository
        StreamWatchlistRepository, ResolutionRepository, TokenMetaRepository
        TradeWatchlistRepository, MarketScoresCacheRepository, ScoreHistoryRepository
        MarketUniverseRepository, CandleRepository, OrderbookRepository
"""
from polymarket_bot.storage.database import Database, DatabaseConfig
from polymarket_bot.storage.models import (
    ApprovalAlert,
    CandidateWatermark,
    DailyPnl,
    ExitEvent,
    LiveOrder,
    MarketScoresCache,
    PaperTrade,
    PolymarketCandidate,
    PolymarketFirstTrigger,
    PolymarketResolution,
    PolymarketTokenMeta,
    PolymarketTrade,
    Position,
    ScoreHistory,
    StreamWatchlistItem,
    TradeApproval,
    TradeWatchlistItem,
    TradeWatermark,
    TriggerWatermark,
    # Tiered Data Architecture Models
    MarketUniverse,
    OutcomeToken,
    PriceSnapshot,
    PriceCandle,
    OrderbookSnapshot,
    StrategyTierRequest,
)
from polymarket_bot.storage.repositories import (
    ApprovalAlertRepository,
    CandidateRepository,
    CandidateWatermarkRepository,
    DailyPnlRepository,
    ExitEventRepository,
    LiveOrderRepository,
    MarketScoresCacheRepository,
    PaperTradeRepository,
    PositionRepository,
    ResolutionRepository,
    ScoreHistoryRepository,
    StreamWatchlistRepository,
    TokenMetaRepository,
    TradeApprovalRepository,
    TradeRepository,
    TradeWatchlistRepository,
    TradeWatermarkRepository,
    TriggerRepository,
    TriggerWatermarkRepository,
    # Tiered Data Architecture Repositories
    MarketUniverseRepository,
    MarketQuery,
    CandleRepository,
    OrderbookRepository,
)

__all__ = [
    # Database
    "Database",
    "DatabaseConfig",
    # Trade models & repos
    "PolymarketTrade",
    "TradeWatermark",
    "TradeRepository",
    "TradeWatermarkRepository",
    # Trigger models & repos
    "PolymarketFirstTrigger",
    "TriggerWatermark",
    "TriggerRepository",
    "TriggerWatermarkRepository",
    # Candidate models & repos
    "PolymarketCandidate",
    "CandidateWatermark",
    "CandidateRepository",
    "CandidateWatermarkRepository",
    # Order models & repos
    "LiveOrder",
    "PaperTrade",
    "LiveOrderRepository",
    "PaperTradeRepository",
    # Position models & repos
    "Position",
    "ExitEvent",
    "DailyPnl",
    "PositionRepository",
    "ExitEventRepository",
    "DailyPnlRepository",
    # Approval models & repos
    "TradeApproval",
    "ApprovalAlert",
    "TradeApprovalRepository",
    "ApprovalAlertRepository",
    # Market models & repos
    "StreamWatchlistItem",
    "PolymarketResolution",
    "PolymarketTokenMeta",
    "StreamWatchlistRepository",
    "ResolutionRepository",
    "TokenMetaRepository",
    # Watchlist & scoring models & repos
    "TradeWatchlistItem",
    "MarketScoresCache",
    "ScoreHistory",
    "TradeWatchlistRepository",
    "MarketScoresCacheRepository",
    "ScoreHistoryRepository",
    # Tiered Data Architecture models & repos
    "MarketUniverse",
    "OutcomeToken",
    "PriceSnapshot",
    "PriceCandle",
    "OrderbookSnapshot",
    "StrategyTierRequest",
    "MarketUniverseRepository",
    "MarketQuery",
    "CandleRepository",
    "OrderbookRepository",
]
