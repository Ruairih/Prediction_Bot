"""
Pydantic models matching the production PostgreSQL schema.

These models mirror seed/01_schema.sql exactly.
Table names and field names match the production database.

IMPORTANT: All monetary fields (prices, sizes, PnL) use Decimal for precision.
Non-monetary fields (thresholds, scores, hours) use float.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# MARKET DATA
# =============================================================================


class StreamWatchlistItem(BaseModel):
    """Market from the streaming watchlist."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    market_id: str
    question: str
    slug: str
    category: Optional[str] = None
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    liquidity: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    end_date: Optional[str] = None
    generated_at: str
    condition_id: Optional[str] = None


class PolymarketTrade(BaseModel):
    """Raw trade from Polymarket."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    condition_id: str
    trade_id: str
    token_id: Optional[str] = None
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    side: Optional[str] = None
    timestamp: Optional[int] = None
    raw_json: Optional[str] = None
    outcome: Optional[str] = None
    outcome_index: Optional[int] = None


class PolymarketResolution(BaseModel):
    """Market resolution data."""

    condition_id: str
    winning_outcome_index: Optional[int] = None
    winning_outcome: Optional[str] = None
    resolved_at: Optional[str] = None


class PolymarketTokenMeta(BaseModel):
    """Token metadata cache."""

    token_id: str
    condition_id: Optional[str] = None
    market_id: Optional[str] = None
    outcome_index: Optional[int] = None
    outcome: Optional[str] = None
    question: Optional[str] = None
    fetched_at: Optional[str] = None


# =============================================================================
# WATERMARKS (for idempotent processing)
# =============================================================================


class TradeWatermark(BaseModel):
    """Tracks last processed trade per condition."""

    condition_id: str
    last_timestamp: int
    updated_at: str


class TriggerWatermark(BaseModel):
    """Tracks last processed trigger per threshold."""

    threshold: float  # Probability threshold, not monetary
    last_timestamp: int
    updated_at: str


class CandidateWatermark(BaseModel):
    """Tracks last processed candidate per threshold."""

    threshold: float  # Probability threshold, not monetary
    last_created_at: str
    updated_at: str


# =============================================================================
# TRIGGER & CANDIDATE PIPELINE
# =============================================================================


class PolymarketFirstTrigger(BaseModel):
    """First time a token hit a threshold - the key dedup table."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    token_id: str
    condition_id: Optional[str] = None
    threshold: float  # Probability threshold, not monetary
    trigger_timestamp: int
    price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    created_at: str
    model_score: Optional[float] = None  # ML score, not monetary
    model_version: Optional[str] = None
    outcome: Optional[str] = None
    outcome_index: Optional[int] = None


class PolymarketCandidate(BaseModel):
    """Candidate awaiting decision (paper or live trade)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    token_id: str
    condition_id: Optional[str] = None
    threshold: float  # Probability threshold, not monetary
    trigger_timestamp: int
    price: Optional[Decimal] = None
    status: str  # 'pending', 'approved', 'rejected', 'executed'
    score: Optional[float] = None  # ML score, not monetary
    created_at: str
    model_score: Optional[float] = None  # ML score, not monetary
    model_version: Optional[str] = None
    outcome: Optional[str] = None
    outcome_index: Optional[int] = None
    updated_at: Optional[str] = None


# =============================================================================
# TRADING
# =============================================================================


class PaperTrade(BaseModel):
    """Paper (simulated) trade record."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    candidate_id: int
    token_id: str
    condition_id: Optional[str] = None
    threshold: float  # Probability threshold, not monetary
    trigger_timestamp: Optional[int] = None
    candidate_price: Optional[Decimal] = None
    fill_price: Optional[Decimal] = None
    size: Optional[Decimal] = None
    model_score: Optional[float] = None  # ML score, not monetary
    model_version: Optional[str] = None
    decision: str  # 'buy', 'skip', etc.
    reason: Optional[str] = None
    created_at: str
    description: Optional[str] = None
    outcome: Optional[str] = None
    outcome_index: Optional[int] = None


class LiveOrder(BaseModel):
    """Real order submitted to Polymarket."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    order_id: Optional[str] = None
    candidate_id: int
    token_id: str
    condition_id: Optional[str] = None
    threshold: float  # Probability threshold, not monetary
    order_price: Optional[Decimal] = None
    order_size: Optional[Decimal] = None
    fill_price: Optional[Decimal] = None
    fill_size: Optional[Decimal] = None
    status: str  # 'submitted', 'filled', 'partial', 'cancelled', 'rejected'
    reason: Optional[str] = None
    submitted_at: str
    filled_at: Optional[str] = None
    updated_at: Optional[str] = None


class Position(BaseModel):
    """Trading position (open or closed)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    token_id: str
    condition_id: Optional[str] = None
    market_id: Optional[str] = None
    outcome: Optional[str] = None
    outcome_index: Optional[int] = None
    side: str = "BUY"
    size: Decimal
    entry_price: Decimal
    entry_cost: Decimal
    current_price: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Decimal = Decimal("0")
    status: str = "open"  # 'open', 'closed', 'resolved'
    resolution: Optional[str] = None
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    entry_timestamp: str
    exit_timestamp: Optional[str] = None
    resolved_at: Optional[str] = None
    description: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class ExitEvent(BaseModel):
    """Record of a position exit."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    position_id: int
    token_id: str
    condition_id: Optional[str] = None
    exit_type: str  # 'stop_loss', 'take_profit', 'manual', 'resolution'
    entry_price: Decimal
    exit_price: Decimal
    size: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    hours_held: float  # Time duration, not monetary
    exit_order_id: Optional[str] = None
    status: str = "pending"  # 'pending', 'executed', 'failed'
    reason: Optional[str] = None
    created_at: str
    executed_at: Optional[str] = None


class DailyPnl(BaseModel):
    """Daily P&L summary."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: str
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    num_trades: int = 0
    num_wins: int = 0
    num_losses: int = 0
    updated_at: Optional[str] = None


# =============================================================================
# APPROVAL WORKFLOW
# =============================================================================


class TradeApproval(BaseModel):
    """Human approval for a trade."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    token_id: str
    condition_id: Optional[str] = None
    approved_at: str
    approved_by: str = "telegram"
    max_price: Decimal = Decimal("0.98")
    expires_at: Optional[str] = None
    status: str = "pending"  # 'pending', 'executed', 'expired'
    executed_at: Optional[str] = None


class ApprovalAlert(BaseModel):
    """Alert pending human approval."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    token_id: str
    condition_id: Optional[str] = None
    question: Optional[str] = None
    price: Optional[Decimal] = None
    model_score: Optional[float] = None  # ML score, not monetary
    alerted_at: str
    approved: bool = False


# =============================================================================
# SCORING & WATCHLIST
# =============================================================================


class MarketScoresCache(BaseModel):
    """Cached model scores for markets."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    condition_id: str
    market_id: Optional[str] = None
    question: Optional[str] = None
    category: Optional[str] = None
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    spread_pct: Optional[float] = None  # Percentage, not monetary
    liquidity: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    end_date: Optional[str] = None
    time_to_end_hours: Optional[float] = None  # Time duration, not monetary
    model_score: Optional[float] = None  # ML score, not monetary
    passes_filters: Optional[int] = None
    filter_rejections: Optional[str] = None
    is_weather: Optional[int] = None
    is_crypto: Optional[int] = None
    is_politics: Optional[int] = None
    is_sports: Optional[int] = None
    updated_at: Optional[str] = None


class ScoreHistory(BaseModel):
    """Historical score tracking."""

    id: Optional[int] = None
    token_id: Optional[str] = None
    score: Optional[float] = None  # ML score, not monetary
    time_to_end_hours: Optional[float] = None  # Time duration, not monetary
    scored_at: Optional[int] = None


class TradeWatchlistItem(BaseModel):
    """Token being watched for trading."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    token_id: str
    market_id: Optional[str] = None
    condition_id: Optional[str] = None
    question: Optional[str] = None
    trigger_price: Optional[Decimal] = None
    trigger_size: Optional[Decimal] = None
    trigger_timestamp: Optional[int] = None
    initial_score: Optional[float] = None  # ML score, not monetary
    current_score: Optional[float] = None  # ML score, not monetary
    time_to_end_hours: Optional[float] = None  # Time duration, not monetary
    last_scored_at: Optional[int] = None
    status: str = "watching"  # 'watching', 'promoted', 'expired', 'traded'
    created_at: Optional[int] = None
    updated_at: Optional[int] = None
