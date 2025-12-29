"""
Core Layer - Trading engine and orchestration.

This module provides:
    - TradingEngine: Main orchestrator (events -> strategy -> execution)
    - EngineConfig: Configuration for the trading engine
    - EngineStats: Runtime statistics
    - EventProcessor: Event parsing, filtering, context building
    - TriggerTracker: First-trigger deduplication with dual-key support (G2 fix)
    - TriggerInfo: Information about a recorded trigger
    - WatchlistService: Watchlist re-scoring and promotion
    - WatchlistEntry: A token being watched
    - Promotion: A watchlist entry promoted to execution
    - BackgroundTasksManager: Manages async background loops
    - BackgroundTaskConfig: Configuration for background tasks

Critical Gotchas Handled:
    - G1: Stale trade filtering (via EventProcessor)
    - G2: Duplicate Token IDs - Use (token_id, condition_id) for deduplication
    - G5: Orderbook Verification - Always verify before execution

Data Flow:
    1. WebSocket receives price update
    2. EventProcessor builds StrategyContext
    3. TriggerTracker checks if first trigger
    4. Strategy evaluates and returns Signal
    5. Core routes signal to Execution or Watchlist
"""

# Engine
from .engine import TradingEngine, EngineConfig, EngineStats

# Event processing
from .event_processor import EventProcessor, TriggerData

# Trigger tracking (G2 protection)
from .trigger_tracker import TriggerTracker, TriggerInfo

# Watchlist management
from .watchlist_service import WatchlistService, WatchlistEntry, Promotion

# Background tasks
from .background_tasks import BackgroundTasksManager, BackgroundTaskConfig

# Pipeline visibility
from .pipeline_tracker import PipelineTracker, RejectionStage, RejectionEvent, CandidateMarket

# Scoring service (unified model_score)
from .score_service import ScoreService, ScoreResult, MarketData, BackgroundScorer, get_score_service

# Legacy score bridge (for backward compatibility)
from .score_bridge import ScoreBridge, get_score_bridge

__all__ = [
    # Main engine
    "TradingEngine",
    "EngineConfig",
    "EngineStats",
    # Event processing
    "EventProcessor",
    "TriggerData",
    # Trigger tracking (G2 protection)
    "TriggerTracker",
    "TriggerInfo",
    # Watchlist management
    "WatchlistService",
    "WatchlistEntry",
    "Promotion",
    # Background tasks
    "BackgroundTasksManager",
    "BackgroundTaskConfig",
    # Pipeline visibility
    "PipelineTracker",
    "RejectionStage",
    "RejectionEvent",
    "CandidateMarket",
    # Scoring service
    "ScoreService",
    "ScoreResult",
    "MarketData",
    "BackgroundScorer",
    "get_score_service",
    # Legacy score bridge
    "ScoreBridge",
    "get_score_bridge",
]
