"""
Event processor for ingestion pipeline.

Processes incoming events (price updates, trades) with gotcha protections:
    - G1: Filter stale trades (> max_age_seconds old)
    - G3: Backfill missing size via REST API
    - G5: Flag price divergences for verification

Routes valid events to storage and collects metrics.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .client import PolymarketRestClient
from .metrics import MetricsCollector
from .models import Market, PriceUpdate, ProcessedEvent, Trade

logger = logging.getLogger(__name__)


@dataclass
class ProcessorConfig:
    """Configuration for the event processor."""

    # G1: Maximum trade age in seconds
    max_trade_age_seconds: int = 300  # 5 minutes

    # G3: Whether to backfill missing sizes
    backfill_missing_size: bool = True
    size_backfill_timeout: float = 5.0  # seconds

    # G5: Price divergence detection
    check_price_divergence: bool = True
    max_price_deviation: Decimal = Decimal("0.10")

    # Event buffer
    max_recent_events: int = 1000


@dataclass
class ProcessorStats:
    """Statistics from event processing."""
    total_processed: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    g1_filtered: int = 0
    g3_backfilled: int = 0
    g3_failed: int = 0
    g5_flagged: int = 0


class EventProcessor:
    """
    Processes incoming events with gotcha protections.

    This processor:
    1. Receives raw events (PriceUpdate, Trade)
    2. Applies G1/G3/G5 protections
    3. Records metrics
    4. Stores recent events for dashboard display

    Usage:
        processor = EventProcessor(
            rest_client=client,
            metrics=metrics_collector,
        )

        # Process a price update (from WebSocket)
        result = await processor.process_price_update(update)
        if result.accepted:
            # Event passed all checks
            pass

        # Process a trade (from REST API)
        result = await processor.process_trade(trade)
    """

    def __init__(
        self,
        rest_client: PolymarketRestClient,
        metrics: MetricsCollector,
        config: Optional[ProcessorConfig] = None,
        market_lookup: Optional[dict[str, Market]] = None,
        token_to_market: Optional[dict[str, str]] = None,
    ):
        """
        Initialize the event processor.

        Args:
            rest_client: REST client for G3 backfill and G5 verification
            metrics: Metrics collector for recording stats
            config: Optional processor configuration
            market_lookup: Dict mapping condition_id to Market objects
            token_to_market: Dict mapping token_id to condition_id
        """
        self._client = rest_client
        self._metrics = metrics
        self._config = config or ProcessorConfig()
        self._market_lookup = market_lookup or {}
        self._token_to_market = token_to_market or {}

        # Stats
        self._stats = ProcessorStats()

        # Recent events buffer (for dashboard)
        self._recent_events: deque[ProcessedEvent] = deque(
            maxlen=self._config.max_recent_events
        )

        # Lock for thread safety
        self._lock = asyncio.Lock()

    def set_market_lookup(
        self,
        market_lookup: dict[str, Market],
        token_to_market: dict[str, str],
    ) -> None:
        """Update the market lookup dictionaries (called after markets are fetched)."""
        self._market_lookup = market_lookup
        self._token_to_market = token_to_market

    def _get_question(self, token_id: str) -> Optional[str]:
        """Look up the market question for a token."""
        condition_id = self._token_to_market.get(token_id)
        if condition_id:
            market = self._market_lookup.get(condition_id)
            if market:
                return market.question
        return None

    @property
    def stats(self) -> ProcessorStats:
        """Get current processing statistics."""
        return self._stats

    @property
    def recent_events(self) -> list[ProcessedEvent]:
        """Get recent processed events (most recent first)."""
        return list(reversed(self._recent_events))

    def get_recent_events(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProcessedEvent]:
        """
        Get paginated recent events.

        Args:
            limit: Maximum events to return
            offset: Number of events to skip

        Returns:
            List of recent events (most recent first)
        """
        events = self.recent_events
        return events[offset:offset + limit]

    async def process_price_update(
        self,
        update: PriceUpdate,
    ) -> ProcessedEvent:
        """
        Process a price update from WebSocket.

        G3 Note: WebSocket updates don't include size.
        If backfill_missing_size is enabled, we'll try to fetch
        the size from REST API.

        Args:
            update: The price update to process

        Returns:
            ProcessedEvent with processing results
        """
        # FIX: Only hold lock for shared state updates, not during I/O
        # This allows concurrent event processing while I/O is in progress

        # Phase 1: Record receipt (minimal lock)
        async with self._lock:
            self._stats.total_processed += 1
            self._metrics.record_price_update()

        # Build initial result (no lock needed - local variable)
        result = ProcessedEvent(
            event_type="price_update",
            token_id=update.token_id,
            timestamp=update.timestamp,
            accepted=True,
            stored=False,
            price=update.price,
            condition_id=update.condition_id,
            question=self._get_question(update.token_id),
        )

        # Phase 2: Perform I/O operations WITHOUT holding lock
        # G3: Backfill missing size if configured
        if self._config.backfill_missing_size:
            size = await self._backfill_size(update)
            if size is not None:
                result.size = size
                result.g3_backfilled = True

        # G5: Check price divergence if configured
        if self._config.check_price_divergence:
            is_divergent = await self._check_divergence(
                update.token_id,
                update.price,
            )
            if is_divergent:
                result.g5_flagged = True
                # Note: We still accept the event but flag it
                # Core layer should verify before executing trades

        # Phase 3: Update stats based on I/O results (lock needed)
        async with self._lock:
            if result.g3_backfilled:
                self._stats.g3_backfilled += 1
                self._metrics.record_g3_backfill()
            elif self._config.backfill_missing_size:
                self._metrics.record_g3_missing_size()
                self._stats.g3_failed += 1

            if result.g5_flagged:
                self._stats.g5_flagged += 1
                self._metrics.record_g5_divergence()

            self._stats.total_accepted += 1
            self._recent_events.append(result)

        return result

    async def process_trade(
        self,
        trade: Trade,
    ) -> ProcessedEvent:
        """
        Process a trade from REST API.

        G1: Trades older than max_trade_age_seconds are rejected.

        Args:
            trade: The trade to process

        Returns:
            ProcessedEvent with processing results
        """
        # FIX: Only hold lock for shared state updates, not during I/O
        # This allows concurrent event processing while I/O is in progress

        # Phase 1: Record receipt (minimal lock)
        async with self._lock:
            self._stats.total_processed += 1

        # Build initial result (no lock needed - local variable)
        result = ProcessedEvent(
            event_type="trade",
            token_id=trade.token_id,
            timestamp=trade.timestamp,
            accepted=True,
            stored=False,
            price=trade.price,
            size=trade.size,
            condition_id=trade.condition_id,
            question=self._get_question(trade.token_id),
        )

        # G1: Check trade staleness (no lock needed - pure computation)
        is_stale = not trade.is_fresh(self._config.max_trade_age_seconds)
        if is_stale:
            result.accepted = False
            result.g1_filtered = True
            result.reason = (
                f"Trade too old: {trade.age_seconds:.0f}s "
                f"(max: {self._config.max_trade_age_seconds}s)"
            )
            logger.debug(
                f"G1: Filtered stale trade {trade.id} "
                f"({trade.age_seconds:.0f}s old)"
            )

        # Phase 2: Perform I/O operations WITHOUT holding lock
        # G5: Check price divergence if configured
        if result.accepted and self._config.check_price_divergence:
            is_divergent = await self._check_divergence(
                trade.token_id,
                trade.price,
            )
            if is_divergent:
                result.g5_flagged = True

        # Phase 3: Update stats based on results (lock needed)
        async with self._lock:
            if is_stale:
                self._stats.g1_filtered += 1
                self._stats.total_rejected += 1
                self._metrics.record_g1_filter()
            else:
                self._stats.total_accepted += 1
                self._metrics.record_trade_stored(trade.age_seconds)

            if result.g5_flagged:
                self._stats.g5_flagged += 1
                self._metrics.record_g5_divergence()

            self._recent_events.append(result)

        return result

    async def _backfill_size(
        self,
        update: PriceUpdate,
    ) -> Optional[Decimal]:
        """
        G3: Attempt to backfill missing size from REST API.

        Args:
            update: The price update missing size

        Returns:
            Trade size if found, None otherwise
        """
        try:
            size = await asyncio.wait_for(
                self._client.get_trade_size_at_price(
                    update.token_id,
                    update.price,
                    tolerance=Decimal("0.01"),
                    max_age_seconds=60,
                ),
                timeout=self._config.size_backfill_timeout,
            )

            if size is not None:
                logger.debug(
                    f"G3: Backfilled size {size} for "
                    f"{update.token_id} @ {update.price}"
                )

            return size

        except asyncio.TimeoutError:
            logger.warning(
                f"G3: Timeout backfilling size for {update.token_id}"
            )
            return None

        except Exception as e:
            logger.warning(
                f"G3: Failed to backfill size for {update.token_id}: {e}"
            )
            return None

    async def _check_divergence(
        self,
        token_id: str,
        price: Decimal,
    ) -> bool:
        """
        G5: Check if price diverges from orderbook.

        Args:
            token_id: Token to check
            price: Expected price

        Returns:
            True if divergence detected, False otherwise
        """
        try:
            is_valid, best_bid, reason = await asyncio.wait_for(
                self._client.verify_price(
                    token_id,
                    price,
                    self._config.max_price_deviation,
                ),
                timeout=5.0,
            )

            if not is_valid:
                logger.warning(f"G5: Price divergence detected - {reason}")
                return True

            return False

        except asyncio.TimeoutError:
            logger.warning(f"G5: Timeout checking orderbook for {token_id}")
            return False  # Don't flag on timeout

        except Exception as e:
            logger.warning(f"G5: Failed to check orderbook for {token_id}: {e}")
            return False  # Don't flag on error

    def is_stale(self, timestamp: datetime) -> bool:
        """
        G1: Check if a timestamp is too old.

        Args:
            timestamp: The timestamp to check

        Returns:
            True if older than max_trade_age_seconds
        """
        now = datetime.now(timezone.utc)
        age = (now - timestamp).total_seconds()
        return age > self._config.max_trade_age_seconds

    def reset_stats(self) -> None:
        """Reset processing statistics (for testing)."""
        self._stats = ProcessorStats()
        self._recent_events.clear()


class EventBuffer:
    """
    Thread-safe buffer for events awaiting processing.

    Provides backpressure handling when processing can't keep up
    with incoming events.
    """

    def __init__(self, max_size: int = 10000):
        """
        Initialize the event buffer.

        Args:
            max_size: Maximum events to buffer before dropping
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._dropped_count = 0

    @property
    def size(self) -> int:
        """Current number of buffered events."""
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to full buffer."""
        return self._dropped_count

    async def put(self, event: PriceUpdate | Trade) -> bool:
        """
        Add an event to the buffer.

        Args:
            event: Event to buffer

        Returns:
            True if buffered, False if dropped due to full buffer
        """
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped_count += 1
            logger.warning(
                f"Event buffer full, dropped event "
                f"(total dropped: {self._dropped_count})"
            )
            return False

    async def get(self) -> PriceUpdate | Trade:
        """
        Get the next event from the buffer.

        Blocks until an event is available.
        """
        return await self._queue.get()

    def get_nowait(self) -> Optional[PriceUpdate | Trade]:
        """
        Get the next event without blocking.

        Returns:
            Event if available, None otherwise
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def clear(self) -> int:
        """
        Clear all buffered events.

        Returns:
            Number of events cleared
        """
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        return count
