"""
Pipeline Tracker - Visibility into why markets are rejected.

Tracks rejections at each stage of the pipeline:
1. Threshold (price below trigger threshold)
2. Duplicate (G2 - already triggered this token/condition)
3. G1 Trade Age (trade data too old)
4. G5 Orderbook (orderbook price doesn't match trigger)
5. G6 Weather (weather market filtered)
6. Time to End (market expiring too soon)
7. Trade Size (trade too small)
8. Category (blocked category)
9. Max Positions (position limit reached)
10. Strategy Hold/Ignore (strategy decided not to trade)

Design:
- In-memory counters for high-frequency tracking (no DB bloat)
- Sampled recent rejections for drill-down (ring buffer)
- Candidate tracking for near-miss markets
- Periodic aggregation to DB for historical analysis
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional


class RejectionStage(Enum):
    """Stage in pipeline where rejection occurred."""

    # Pre-strategy filters
    THRESHOLD = "threshold"           # Price below threshold
    DUPLICATE = "duplicate"           # G2: Already triggered
    G1_TRADE_AGE = "g1_trade_age"     # Trade data too old
    G5_ORDERBOOK = "g5_orderbook"     # Orderbook price mismatch
    G6_WEATHER = "g6_weather"         # Weather market
    TIME_TO_END = "time_to_end"       # Expiring too soon
    TRADE_SIZE = "trade_size"         # Trade too small
    CATEGORY = "category"             # Blocked category
    MANUAL_BLOCK = "manual_block"     # Manually blocked market
    MAX_POSITIONS = "max_positions"   # Position limit reached

    # Strategy decisions
    STRATEGY_HOLD = "strategy_hold"       # Strategy returned HOLD
    STRATEGY_IGNORE = "strategy_ignore"   # Strategy returned IGNORE


@dataclass
class RejectionEvent:
    """A single rejection event with details."""

    token_id: str
    condition_id: str
    stage: RejectionStage
    timestamp: datetime
    price: Decimal
    question: str = ""
    trade_size: Optional[Decimal] = None
    trade_age_seconds: Optional[float] = None
    rejection_values: dict = field(default_factory=dict)
    outcome: Optional[str] = None  # "Yes" or "No" - the direction of the trade

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "token_id": self.token_id,
            "condition_id": self.condition_id,
            "stage": self.stage.value,
            "timestamp": self.timestamp.isoformat(),
            "price": float(self.price),
            "question": self.question,
            "trade_size": float(self.trade_size) if self.trade_size else None,
            "trade_age_seconds": self.trade_age_seconds,
            "rejection_values": self.rejection_values,
            "outcome": self.outcome,
            "rejection_reason": self._format_rejection_reason(),
        }

    def _format_rejection_reason(self) -> str:
        """Format human-readable rejection reason based on stage and values."""
        stage_reasons = {
            RejectionStage.THRESHOLD: lambda v: f"Price {v.get('price', '?')} below threshold {v.get('threshold', '0.95')}",
            RejectionStage.DUPLICATE: lambda v: f"Already triggered at {v.get('first_trigger_time', 'earlier')}",
            RejectionStage.G1_TRADE_AGE: lambda v: f"Trade data {v.get('age_seconds', '?')}s old (max {v.get('max_age', 300)}s)",
            RejectionStage.G5_ORDERBOOK: lambda v: f"Orderbook price {v.get('orderbook_price', '?')} differs from trigger {v.get('trigger_price', '?')} by {v.get('deviation_pct', '?')}%",
            RejectionStage.G6_WEATHER: lambda v: "Weather-related market (filtered)",
            RejectionStage.TIME_TO_END: lambda v: f"Only {v.get('hours_remaining', '?')} hours until expiry (min {v.get('min_hours', 6)}h)",
            RejectionStage.TRADE_SIZE: lambda v: f"Trade size {v.get('size', '?')} below minimum {v.get('min_size', 50)}",
            RejectionStage.CATEGORY: lambda v: f"Category '{v.get('category', '?')}' is blocked",
            RejectionStage.MANUAL_BLOCK: lambda v: f"Manually blocked: {v.get('reason', 'no reason given')}",
            RejectionStage.MAX_POSITIONS: lambda v: f"At position limit ({v.get('current', '?')}/{v.get('max', '?')})",
            RejectionStage.STRATEGY_HOLD: lambda v: f"Strategy holding: {v.get('reason', 'conditions not met')}",
            RejectionStage.STRATEGY_IGNORE: lambda v: f"Strategy ignored: {v.get('reason', 'not a target')}",
        }
        formatter = stage_reasons.get(self.stage, lambda v: str(v))
        try:
            return formatter(self.rejection_values)
        except Exception:
            return f"Rejected at {self.stage.value}"


@dataclass
class CandidateMarket:
    """A market that passed filters but didn't trigger entry.

    Candidates are markets that:
    - Met all filter criteria (G1, G5, G6, category, etc.)
    - Have a price approaching but not yet reaching the entry threshold
    - Are being actively monitored for potential entry

    These are "watching" markets that may trigger a trade soon.
    """

    token_id: str
    condition_id: str
    question: str
    current_price: Decimal
    threshold: Decimal
    last_updated: datetime
    last_signal: str  # HOLD, WATCH, etc.
    last_signal_reason: str
    model_score: Optional[float] = None
    time_to_end_hours: float = 0
    trade_size: Optional[Decimal] = None
    trade_age_seconds: float = 0
    highest_price_seen: Decimal = Decimal("0")
    times_evaluated: int = 0
    outcome: Optional[str] = None  # "Yes" or "No" - which outcome token this is

    @property
    def distance_to_threshold(self) -> Decimal:
        """How far from threshold (0 = at threshold, negative = above)."""
        return self.threshold - self.current_price

    @property
    def is_above_threshold(self) -> bool:
        """Whether price is at or above threshold (triggered)."""
        return self.current_price >= self.threshold

    @property
    def is_near_miss(self) -> bool:
        """
        Whether this is a near miss - triggered but strategy didn't trade.

        A 'near miss' means the price hit threshold but the strategy chose
        not to enter (returned HOLD/WATCHLIST instead of ENTRY).
        """
        return self.is_above_threshold

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        # Determine status label based on price vs threshold
        if self.is_above_threshold:
            status_label = "Triggered (Held)"  # Hit threshold, strategy held
        elif abs(self.distance_to_threshold) <= Decimal("0.02"):
            status_label = "Very Close"  # Within 2% of threshold
        else:
            status_label = "Watching"  # Further from threshold

        return {
            "token_id": self.token_id,
            "condition_id": self.condition_id,
            "question": self.question,
            "current_price": float(self.current_price),
            "threshold": float(self.threshold),
            "distance_to_threshold": float(self.distance_to_threshold),
            "last_updated": self.last_updated.isoformat(),
            "last_signal": self.last_signal,
            "last_signal_reason": self.last_signal_reason,
            "model_score": self.model_score,
            "time_to_end_hours": self.time_to_end_hours,
            "trade_size": float(self.trade_size) if self.trade_size else None,
            "trade_age_seconds": self.trade_age_seconds,
            "highest_price_seen": float(self.highest_price_seen),
            "times_evaluated": self.times_evaluated,
            "outcome": self.outcome,
            "is_near_miss": self.is_near_miss,
            "is_above_threshold": self.is_above_threshold,
            "status_label": status_label,
        }


class PipelineTracker:
    """
    Tracks pipeline rejections and candidates in-memory.

    Thread-safe for concurrent access from event processing.

    Usage:
        tracker = PipelineTracker()

        # Record a rejection
        tracker.record_rejection(
            token_id="tok_abc",
            condition_id="0x123",
            stage=RejectionStage.G5_ORDERBOOK,
            price=Decimal("0.95"),
            question="Will X happen?",
            rejection_values={"orderbook_price": 0.85, "trigger_price": 0.95},
        )

        # Get stats
        stats = tracker.get_stats()
        # {'totals': {'g5_orderbook': 150, 'duplicate': 5000, ...}, 'total': 5150}

        # Get recent rejections for a stage
        rejections = tracker.get_recent_rejections(
            stage=RejectionStage.G5_ORDERBOOK,
            limit=50
        )
    """

    def __init__(
        self,
        max_recent_rejections: int = 1000,
        max_candidates: int = 200,
        sample_rate: int = 50,  # Store 1 in N detailed rejections
    ):
        """
        Initialize pipeline tracker.

        Args:
            max_recent_rejections: Max detailed rejections to keep in memory
            max_candidates: Max candidate markets to track
            sample_rate: Store 1 in N rejections for detail view (reduces memory)
        """
        self._max_recent = max_recent_rejections
        self._max_candidates = max_candidates
        self._sample_rate = sample_rate

        # Counters by stage (thread-safe via lock)
        self._counters: dict[RejectionStage, int] = {stage: 0 for stage in RejectionStage}
        self._counter_lock = threading.Lock()

        # Time-bucketed counters for trends (minute buckets)
        self._minute_buckets: dict[str, dict[RejectionStage, int]] = {}
        self._bucket_lock = threading.Lock()

        # Recent detailed rejections (sampled)
        self._recent_rejections: deque[RejectionEvent] = deque(maxlen=max_recent_rejections)
        self._recent_lock = threading.Lock()
        self._sample_counter = 0

        # Candidate markets
        self._candidates: dict[str, CandidateMarket] = {}  # keyed by condition_id
        self._candidate_lock = threading.Lock()

        # Tracking start time
        self._started_at = datetime.now(timezone.utc)

    def record_rejection(
        self,
        token_id: str,
        condition_id: str,
        stage: RejectionStage,
        price: Decimal,
        question: str = "",
        trade_size: Optional[Decimal] = None,
        trade_age_seconds: Optional[float] = None,
        rejection_values: Optional[dict] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """
        Record a pipeline rejection.

        Args:
            token_id: Token that was rejected
            condition_id: Market condition ID
            stage: Pipeline stage where rejection occurred
            price: Price at rejection time
            question: Market question (optional)
            trade_size: Trade size if available
            trade_age_seconds: Age of trade data if relevant (G1)
            rejection_values: Extra details about why rejected
            outcome: "Yes" or "No" - which outcome token this is
        """
        now = datetime.now(timezone.utc)
        minute_bucket = now.strftime("%Y-%m-%d %H:%M")

        # Always increment counters (fast, always)
        with self._counter_lock:
            self._counters[stage] += 1

        with self._bucket_lock:
            if minute_bucket not in self._minute_buckets:
                self._minute_buckets[minute_bucket] = {s: 0 for s in RejectionStage}
            self._minute_buckets[minute_bucket][stage] += 1

        # Sample detailed rejections to avoid memory bloat
        # Use counter lock for thread safety
        with self._counter_lock:
            self._sample_counter += 1
            should_sample = self._sample_counter % self._sample_rate == 0

        if should_sample:
            event = RejectionEvent(
                token_id=token_id,
                condition_id=condition_id,
                stage=stage,
                timestamp=now,
                price=price,
                question=question,
                trade_size=trade_size,
                trade_age_seconds=trade_age_seconds,
                rejection_values=rejection_values or {},
                outcome=outcome,
            )
            with self._recent_lock:
                self._recent_rejections.append(event)

    def update_candidate(
        self,
        token_id: str,
        condition_id: str,
        question: str,
        price: Decimal,
        threshold: Decimal,
        signal: str,
        signal_reason: str,
        model_score: Optional[float] = None,
        time_to_end_hours: float = 0,
        trade_size: Optional[Decimal] = None,
        trade_age_seconds: float = 0,
        outcome: Optional[str] = None,
    ) -> None:
        """
        Update or create a candidate market entry.

        Called when a market passes filters but strategy returns HOLD/WATCH.

        Args:
            token_id: Token ID
            condition_id: Market condition ID
            question: Market question
            price: Current price
            threshold: Price threshold for entry
            signal: Strategy signal (HOLD, WATCH, etc.)
            signal_reason: Why strategy returned this signal
            model_score: Model confidence score if available
            time_to_end_hours: Hours until market ends
            trade_size: Recent trade size
            trade_age_seconds: Age of trade data
            outcome: "Yes" or "No" - which outcome token this is
        """
        now = datetime.now(timezone.utc)

        with self._candidate_lock:
            if condition_id in self._candidates:
                # Update existing
                candidate = self._candidates[condition_id]
                candidate.current_price = price
                candidate.last_updated = now
                candidate.last_signal = signal
                candidate.last_signal_reason = signal_reason
                candidate.model_score = model_score
                candidate.time_to_end_hours = time_to_end_hours
                candidate.trade_size = trade_size
                candidate.trade_age_seconds = trade_age_seconds
                candidate.times_evaluated += 1
                if outcome:
                    candidate.outcome = outcome
                if price > candidate.highest_price_seen:
                    candidate.highest_price_seen = price
            else:
                # Evict oldest if at capacity
                if len(self._candidates) >= self._max_candidates:
                    oldest_key = min(
                        self._candidates.keys(),
                        key=lambda k: self._candidates[k].last_updated
                    )
                    del self._candidates[oldest_key]

                # Create new
                self._candidates[condition_id] = CandidateMarket(
                    token_id=token_id,
                    condition_id=condition_id,
                    question=question,
                    current_price=price,
                    threshold=threshold,
                    last_updated=now,
                    last_signal=signal,
                    last_signal_reason=signal_reason,
                    model_score=model_score,
                    time_to_end_hours=time_to_end_hours,
                    trade_size=trade_size,
                    trade_age_seconds=trade_age_seconds,
                    highest_price_seen=price,
                    times_evaluated=1,
                    outcome=outcome,
                )

    def remove_candidate(self, condition_id: str) -> None:
        """Remove a candidate (e.g., after it triggers entry)."""
        with self._candidate_lock:
            self._candidates.pop(condition_id, None)

    def get_stats(self, minutes: Optional[int] = None) -> dict:
        """
        Get rejection statistics.

        Args:
            minutes: If provided, only count last N minutes. Otherwise all-time.

        Returns:
            Dict with totals by stage and grand total
        """
        if minutes is None:
            # All-time totals
            with self._counter_lock:
                totals = {stage.value: count for stage, count in self._counters.items()}
            return {
                "totals": totals,
                "total": sum(totals.values()),
                "since": self._started_at.isoformat(),
            }

        # Time-windowed totals
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        cutoff_bucket = cutoff.strftime("%Y-%m-%d %H:%M")

        totals = {stage.value: 0 for stage in RejectionStage}

        with self._bucket_lock:
            for bucket, stages in self._minute_buckets.items():
                if bucket >= cutoff_bucket:
                    for stage, count in stages.items():
                        totals[stage.value] += count

        return {
            "totals": totals,
            "total": sum(totals.values()),
            "minutes": minutes,
        }

    def get_recent_rejections(
        self,
        stage: Optional[RejectionStage] = None,
        limit: int = 100,
    ) -> list[RejectionEvent]:
        """
        Get recent detailed rejections.

        Args:
            stage: Filter by stage (optional)
            limit: Max results to return

        Returns:
            List of recent rejections (most recent first)
        """
        with self._recent_lock:
            rejections = list(self._recent_rejections)

        if stage:
            rejections = [r for r in rejections if r.stage == stage]

        # Most recent first
        return list(reversed(rejections))[:limit]

    def get_candidates(
        self,
        sort_by: str = "distance",
        limit: int = 50,
    ) -> list[CandidateMarket]:
        """
        Get candidate markets.

        Args:
            sort_by: "distance" (closest to threshold), "score", or "recent"
            limit: Max results

        Returns:
            List of candidate markets
        """
        with self._candidate_lock:
            candidates = list(self._candidates.values())

        if sort_by == "distance":
            candidates.sort(key=lambda c: c.distance_to_threshold)
        elif sort_by == "score":
            candidates.sort(key=lambda c: c.model_score or 0, reverse=True)
        elif sort_by == "recent":
            candidates.sort(key=lambda c: c.last_updated, reverse=True)

        return candidates[:limit]

    def get_near_misses(self, max_distance: Decimal = Decimal("0.02")) -> list[CandidateMarket]:
        """
        Get markets that triggered but strategy held (near misses).

        A near miss is a market where:
        - Price reached or exceeded threshold (distance_to_threshold <= 0)
        - Strategy chose not to enter (returned HOLD/WATCHLIST)

        Args:
            max_distance: Ignored (kept for API compatibility)

        Returns:
            Candidates that triggered but were held
        """
        with self._candidate_lock:
            return [
                c for c in self._candidates.values()
                if c.is_above_threshold  # Price >= threshold
            ]

    def get_funnel_summary(self, minutes: int = 60) -> dict:
        """
        Get a funnel summary for dashboard display.

        Returns breakdown of rejections suitable for funnel visualization.
        """
        stats = self.get_stats(minutes)
        totals = stats["totals"]
        grand_total = stats["total"]

        # Order stages in pipeline order
        pipeline_order = [
            RejectionStage.THRESHOLD,
            RejectionStage.DUPLICATE,
            RejectionStage.G1_TRADE_AGE,
            RejectionStage.G5_ORDERBOOK,
            RejectionStage.G6_WEATHER,
            RejectionStage.TIME_TO_END,
            RejectionStage.TRADE_SIZE,
            RejectionStage.CATEGORY,
            RejectionStage.MANUAL_BLOCK,
            RejectionStage.MAX_POSITIONS,
            RejectionStage.STRATEGY_HOLD,
            RejectionStage.STRATEGY_IGNORE,
        ]

        funnel = []
        for stage in pipeline_order:
            count = totals.get(stage.value, 0)
            percentage = (count / grand_total * 100) if grand_total > 0 else 0
            funnel.append({
                "stage": stage.value,
                "label": self._stage_label(stage),
                "count": count,
                "percentage": round(percentage, 2),
            })

        # Get sample rejections for top stages
        top_stages = sorted(
            [(s, totals.get(s.value, 0)) for s in pipeline_order],
            key=lambda x: x[1],
            reverse=True
        )[:3]

        samples = {}
        for stage, _ in top_stages:
            recent = self.get_recent_rejections(stage=stage, limit=3)
            samples[stage.value] = [r.to_dict() for r in recent]

        return {
            "funnel": funnel,
            "total_rejections": grand_total,
            "minutes": minutes,
            "samples": samples,
            "near_miss_count": len(self.get_near_misses()),
            "candidate_count": len(self._candidates),
        }

    def cleanup_old_buckets(self, max_age_minutes: int = 120) -> int:
        """
        Remove old minute buckets to prevent memory growth.

        Args:
            max_age_minutes: Remove buckets older than this

        Returns:
            Number of buckets removed
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        cutoff_bucket = cutoff.strftime("%Y-%m-%d %H:%M")

        removed = 0
        with self._bucket_lock:
            old_keys = [k for k in self._minute_buckets.keys() if k < cutoff_bucket]
            for key in old_keys:
                del self._minute_buckets[key]
                removed += 1

        return removed

    def _stage_label(self, stage: RejectionStage) -> str:
        """Human-readable label for stage."""
        labels = {
            RejectionStage.THRESHOLD: "Below Threshold",
            RejectionStage.DUPLICATE: "Already Triggered (G2)",
            RejectionStage.G1_TRADE_AGE: "Stale Trade (G1)",
            RejectionStage.G5_ORDERBOOK: "Orderbook Mismatch (G5)",
            RejectionStage.G6_WEATHER: "Weather Market (G6)",
            RejectionStage.TIME_TO_END: "Expiring Soon",
            RejectionStage.TRADE_SIZE: "Trade Too Small",
            RejectionStage.CATEGORY: "Blocked Category",
            RejectionStage.MANUAL_BLOCK: "Manually Blocked",
            RejectionStage.MAX_POSITIONS: "Max Positions",
            RejectionStage.STRATEGY_HOLD: "Strategy: Hold",
            RejectionStage.STRATEGY_IGNORE: "Strategy: Ignore",
        }
        return labels.get(stage, stage.value)

    def reset(self) -> None:
        """Reset all counters and buffers (for testing)."""
        with self._counter_lock:
            self._counters = {stage: 0 for stage in RejectionStage}
        with self._bucket_lock:
            self._minute_buckets = {}
        with self._recent_lock:
            self._recent_rejections.clear()
        with self._candidate_lock:
            self._candidates = {}
        self._sample_counter = 0
        self._started_at = datetime.now(timezone.utc)
