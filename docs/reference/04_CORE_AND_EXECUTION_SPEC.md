# Core Engine & Execution Layer Specification

## Overview

The **Core Engine** orchestrates the trading flow:
- Receives market data from Ingestion
- Routes to strategies for signal generation
- Passes signals to Execution

The **Execution Layer** handles:
- Order submission to Polymarket CLOB
- Position tracking
- Exit strategy management
- Risk controls

---

## Part 1: Core Engine

### Directory Structure

```
src/polymarket_bot/core/
├── CLAUDE.md
├── __init__.py
├── engine.py              # Main orchestration engine
├── signal_router.py       # Routes signals to appropriate handlers
├── context_builder.py     # Builds StrategyContext from data
├── watchlist_manager.py   # Manages deferred trades
└── tests/
```

### `engine.py` - Main Orchestrator

```python
"""
Core trading engine.

Orchestrates the flow:
1. Receive market data
2. Build strategy context
3. Invoke strategies
4. Route signals to execution
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Set

from ..ingestion.types import PriceUpdate, TradeResponse
from ..ingestion.polymarket_client import PolymarketClient
from ..ingestion.websocket_client import WebSocketClient, parse_price_updates
from ..storage.database import Database
from ..storage.repositories.market_repo import MarketRepository, TokenRepository
from ..storage.repositories.trigger_repo import TriggerRepository
from ..strategies.base import Signal, SignalAction, Strategy, StrategyContext
from ..strategies.registry import StrategyRegistry
from .signal_router import SignalRouter
from .context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine that orchestrates all components.

    Usage:
        engine = TradingEngine(db, client, ws_client, strategies=["high_prob_yes"])
        await engine.run()
    """

    def __init__(
        self,
        db: Database,
        polymarket_client: PolymarketClient,
        websocket_client: WebSocketClient,
        strategies: Optional[List[str]] = None,
        signal_router: Optional[SignalRouter] = None,
    ) -> None:
        self.db = db
        self.polymarket_client = polymarket_client
        self.ws_client = websocket_client

        # Load requested strategies
        self.strategies: List[Strategy] = []
        strategy_names = strategies or StrategyRegistry.list_names()
        for name in strategy_names:
            strategy = StrategyRegistry.get(name)
            if strategy:
                self.strategies.append(strategy)
                logger.info(f"Loaded strategy: {name} v{strategy.version}")
            else:
                logger.warning(f"Strategy not found: {name}")

        # Initialize components
        self.context_builder = ContextBuilder(db, polymarket_client)
        self.signal_router = signal_router or SignalRouter(db, polymarket_client)

        # State
        self._running = False
        self._subscribed_tokens: Set[str] = set()

    async def run(self) -> None:
        """Main run loop."""
        self._running = True

        # Build initial watchlist
        await self._refresh_watchlist()

        # Start background tasks
        tasks = [
            asyncio.create_task(self._websocket_loop()),
            asyncio.create_task(self._watchlist_refresh_loop()),
            asyncio.create_task(self._watchlist_rescore_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Engine shutting down")
        finally:
            for task in tasks:
                task.cancel()

    async def stop(self) -> None:
        """Stop the engine."""
        self._running = False

    async def _websocket_loop(self) -> None:
        """Process WebSocket messages."""
        async for message in self.ws_client.run():
            if not self._running:
                break

            try:
                await self._handle_message(message)
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    async def _handle_message(self, message: Dict) -> None:
        """Handle a single WebSocket message."""
        # Parse price updates
        price_updates = parse_price_updates(message)

        for update in price_updates:
            await self._handle_price_update(update)

    async def _handle_price_update(self, update: PriceUpdate) -> None:
        """Handle price update from WebSocket."""
        token_id = update.asset_id

        # Build context
        context = await self.context_builder.build(
            token_id=token_id,
            current_price=float(update.price),
            current_timestamp=update.timestamp,
        )

        if context is None:
            return

        # Invoke each strategy
        for strategy in self.strategies:
            try:
                signal = strategy.on_price_update(update, context)
                if signal:
                    await self._handle_signal(signal, context)
            except Exception as e:
                logger.error(f"Strategy {strategy.name} error: {e}")

    async def _handle_signal(self, signal: Signal, context: StrategyContext) -> None:
        """Route signal to appropriate handler."""
        logger.info(
            f"Signal: {signal.action.value} {signal.token_id[:16]}... "
            f"reason={signal.reason}"
        )

        if signal.action == SignalAction.BUY:
            await self.signal_router.handle_buy(signal)

        elif signal.action == SignalAction.SELL:
            await self.signal_router.handle_sell(signal)

        elif signal.action == SignalAction.WATCH:
            # Price update triggered - need to fetch trade data
            if signal.reason == "price_trigger_needs_trade_data":
                await self._fetch_and_process_trade(signal, context)
            else:
                await self.signal_router.handle_watch(signal)

        elif signal.action == SignalAction.IGNORE:
            # Log but don't act
            logger.debug(f"Ignored: {signal.token_id[:16]}... {signal.reason}")

    async def _fetch_and_process_trade(
        self,
        signal: Signal,
        context: StrategyContext,
    ) -> None:
        """
        Fetch trade data and re-invoke strategy.

        WebSocket doesn't include trade size, so we need to fetch it.
        """
        try:
            # Fetch recent trades
            trades = await self.polymarket_client.get_recent_trades(
                signal.condition_id,
                max_age_seconds=300,  # CRITICAL: Avoid stale trades
            )

            if not trades:
                logger.debug(f"No fresh trades for {signal.token_id[:16]}")
                return

            # Find trade matching trigger price
            target_price = signal.metadata.get("trigger_price", signal.price)
            matching_trade = None

            for trade in trades:
                if abs(trade.price - target_price) <= 0.02:
                    matching_trade = trade
                    break

            if not matching_trade:
                # Use most recent high-price trade
                for trade in trades:
                    if trade.price >= 0.90:
                        matching_trade = trade
                        break

            if not matching_trade:
                logger.debug(f"No matching trade found for {signal.token_id[:16]}")
                return

            # Re-invoke strategy with full trade data
            for strategy in self.strategies:
                if strategy.name == signal.strategy_name:
                    new_signal = strategy.on_trade(matching_trade, context)
                    if new_signal:
                        await self._handle_signal(new_signal, context)
                    break

        except Exception as e:
            logger.error(f"Failed to fetch trade data: {e}")

    async def _refresh_watchlist(self) -> None:
        """Refresh WebSocket subscription list."""
        # Get markets to watch
        markets_to_watch: Set[str] = set()

        # Query database for active tokens
        market_repo = MarketRepository(self.db)
        token_repo = TokenRepository(self.db)

        # For each strategy, get markets it wants to watch
        # This is simplified - real impl would be more sophisticated
        for market in market_repo.get_unresolved(limit=5000):
            for strategy in self.strategies:
                # Would need to convert market to MarketResponse
                # Simplified here
                pass

        # For now, just get tokens we haven't triggered on
        trigger_repo = TriggerRepository(self.db)
        tokens = token_repo.get_all(limit=1000)

        for token in tokens:
            # Check if already triggered at any common threshold
            if not trigger_repo.has_condition_triggered(token.condition_id, 0.95):
                markets_to_watch.add(token.token_id)

        # Update subscriptions
        new_tokens = markets_to_watch - self._subscribed_tokens
        remove_tokens = self._subscribed_tokens - markets_to_watch

        if remove_tokens:
            await self.ws_client.unsubscribe(list(remove_tokens))
            self._subscribed_tokens -= remove_tokens

        if new_tokens:
            await self.ws_client.subscribe(list(new_tokens))
            self._subscribed_tokens |= new_tokens

        logger.info(f"Watchlist: {len(self._subscribed_tokens)} tokens")

    async def _watchlist_refresh_loop(self) -> None:
        """Periodically refresh watchlist."""
        while self._running:
            await asyncio.sleep(300)  # Every 5 minutes
            try:
                await self._refresh_watchlist()
            except Exception as e:
                logger.error(f"Watchlist refresh failed: {e}")

    async def _watchlist_rescore_loop(self) -> None:
        """Periodically re-score watchlist items."""
        while self._running:
            await asyncio.sleep(3600)  # Every hour
            try:
                await self._rescore_watchlist()
            except Exception as e:
                logger.error(f"Watchlist rescore failed: {e}")

    async def _rescore_watchlist(self) -> None:
        """Re-score items on the watchlist."""
        # Get watchlist items
        from ..storage.repositories.watchlist_repo import WatchlistRepository

        watchlist_repo = WatchlistRepository(self.db)
        items = watchlist_repo.get_watching()

        promoted = 0
        expired = 0

        for item in items:
            # Build context
            context = await self.context_builder.build(
                token_id=item.token_id,
                current_price=0,  # Would need to fetch
                current_timestamp=int(time.time()),
            )

            if context is None:
                continue

            # Find strategy and invoke
            strategy = StrategyRegistry.get(item.strategy_name)
            if not strategy:
                continue

            signal = strategy.on_watchlist_check(item.token_id, context)

            if signal and signal.action == SignalAction.BUY:
                await self.signal_router.handle_buy(signal)
                watchlist_repo.update_status(item.id, "promoted")
                promoted += 1

            elif signal and signal.action == SignalAction.IGNORE:
                watchlist_repo.update_status(item.id, "expired", signal.reason)
                expired += 1

        if promoted or expired:
            logger.info(f"Watchlist rescore: {promoted} promoted, {expired} expired")
```

---

## Part 2: Execution Layer

### Directory Structure

```
src/polymarket_bot/execution/
├── CLAUDE.md
├── __init__.py
├── order_manager.py       # CLOB order submission
├── position_tracker.py    # Position tracking
├── exit_manager.py        # Exit strategy (profit target, stop loss)
├── risk_manager.py        # Risk controls and limits
├── wallet.py              # Balance and signing
└── tests/
```

### `order_manager.py` - CLOB Order Submission

```python
"""
Order manager for Polymarket CLOB.

Handles:
- Order creation and submission
- Order status tracking
- Fill detection
- Balance cache management
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
    OrderArgs,
    OrderType,
)
from pydantic import BaseModel

from ..storage.database import Database
from ..storage.repositories.order_repo import Order, OrderRepository
from ..strategies.base import Signal

logger = logging.getLogger(__name__)

POLYGON_CHAIN_ID = 137
CLOB_HOST = "https://clob.polymarket.com"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass
class OrderResult:
    """Result of order submission."""
    success: bool
    order_id: Optional[str]
    status: OrderStatus
    message: Optional[str] = None
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None


class OrderManagerConfig(BaseModel):
    """Order manager configuration."""
    # Credentials
    api_key: str
    api_secret: str
    api_passphrase: str
    private_key: str
    funder: str = ""
    signature_type: int = 2  # Gnosis proxy

    # Order defaults
    default_size: float = 25.0
    slippage_bps: float = 50.0  # 0.5%
    max_price: float = 0.98
    min_price: float = 0.90

    # Retry
    max_retries: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_file(cls, path: Path) -> "OrderManagerConfig":
        """Load from credentials JSON file."""
        import json
        import os

        with open(path) as f:
            creds = json.load(f)

        return cls(
            api_key=creds.get("api_key", ""),
            api_secret=creds.get("api_secret", ""),
            api_passphrase=creds.get("api_passphrase", ""),
            private_key=creds.get("private_key", os.environ.get("POLYMARKET_PRIVATE_KEY", "")),
            funder=creds.get("funder", ""),
            signature_type=creds.get("signature_type", 2),
        )


class OrderManager:
    """
    Manages order submission to Polymarket CLOB.

    CRITICAL GOTCHAS:
    1. Always verify orderbook price before submitting
    2. Refresh balance cache on startup and after errors
    3. Round prices to valid tick size
    """

    def __init__(
        self,
        config: OrderManagerConfig,
        db: Database,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.db = db
        self.dry_run = dry_run

        self.order_repo = OrderRepository(db)
        self._client: Optional[ClobClient] = None

    @property
    def client(self) -> ClobClient:
        """Lazy-load CLOB client."""
        if self._client is None:
            creds = ApiCreds(
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                api_passphrase=self.config.api_passphrase,
            )
            self._client = ClobClient(
                host=CLOB_HOST,
                chain_id=POLYGON_CHAIN_ID,
                key=self.config.private_key,
                creds=creds,
                funder=self.config.funder or None,
                signature_type=self.config.signature_type,
            )
        return self._client

    def refresh_balance_cache(self) -> bool:
        """
        Refresh CLOB server-side balance cache.

        CRITICAL: Call this on startup and after balance errors.
        The CLOB API caches balance info which can become stale.
        """
        try:
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self.config.signature_type,
            )
            self.client.update_balance_allowance(params)

            # Log current balance
            balance_info = self.client.get_balance_allowance(params)
            balance_usd = int(balance_info.get("balance", 0)) / 1e6
            logger.info(f"Balance cache refreshed. Available: ${balance_usd:.2f}")

            return True
        except Exception as e:
            logger.warning(f"Failed to refresh balance cache: {e}")
            return False

    async def submit_from_signal(self, signal: Signal) -> OrderResult:
        """
        Submit order from a trading signal.

        Validates signal, creates order, submits to CLOB.
        """
        # Validate signal
        if not signal.price or not signal.size:
            return OrderResult(
                success=False,
                order_id=None,
                status=OrderStatus.REJECTED,
                message="missing_price_or_size",
            )

        if signal.price > self.config.max_price:
            return OrderResult(
                success=False,
                order_id=None,
                status=OrderStatus.REJECTED,
                message=f"price_too_high:{signal.price:.4f}",
            )

        # Verify orderbook price (CRITICAL - Belichick bug protection)
        is_valid, actual_price, reason = await self._verify_orderbook(
            signal.token_id,
            signal.price,
        )
        if not is_valid:
            return OrderResult(
                success=False,
                order_id=None,
                status=OrderStatus.REJECTED,
                message=f"orderbook_mismatch:{reason}",
            )

        # Calculate order price with slippage
        order_price = self._calculate_order_price(signal.price)

        # Submit order
        if self.dry_run:
            logger.info(
                f"[DRY RUN] Would submit: BUY {signal.size} @ {order_price:.4f} "
                f"token={signal.token_id[:16]}"
            )
            return OrderResult(
                success=True,
                order_id="dry_run",
                status=OrderStatus.SUBMITTED,
                message="dry_run",
            )

        return await self._submit_order(signal.token_id, order_price, signal.size)

    async def _verify_orderbook(
        self,
        token_id: str,
        expected_price: float,
        max_deviation: float = 0.10,
    ) -> tuple[bool, float, str]:
        """Verify orderbook matches expected price."""
        try:
            book = self.client.get_order_book(token_id)

            bids = book.get("bids", [])
            asks = book.get("asks", [])

            best_bid = float(bids[0]["price"]) if bids else 0
            best_ask = float(asks[0]["price"]) if asks else 1.0

            # Use midpoint as actual price
            if best_bid > 0 and best_ask < 1.0:
                actual_price = (best_bid + best_ask) / 2
            else:
                actual_price = best_bid or best_ask

            deviation = abs(actual_price - expected_price)

            if deviation > max_deviation:
                return (
                    False,
                    actual_price,
                    f"expected={expected_price:.2f},actual={actual_price:.2f}",
                )

            return True, actual_price, "ok"

        except Exception as e:
            logger.warning(f"Orderbook verification failed: {e}")
            return False, 0, f"verification_error:{e}"

    def _calculate_order_price(self, base_price: float) -> float:
        """Add slippage buffer to price."""
        slippage = base_price * (self.config.slippage_bps / 10000)
        order_price = base_price + slippage
        order_price = min(order_price, self.config.max_price)
        return round(order_price, 2)

    async def _submit_order(
        self,
        token_id: str,
        price: float,
        size: float,
    ) -> OrderResult:
        """Submit order to CLOB with retry logic."""
        last_error = None
        balance_refreshed = False

        for attempt in range(self.config.max_retries):
            try:
                # Get market parameters
                tick_size = self.client.get_tick_size(token_id)
                fee_rate = self.client.get_fee_rate_bps(token_id)

                # Round to tick
                price = self._round_to_tick(price, tick_size)

                # Create order
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=size,
                    side="BUY",
                    fee_rate_bps=fee_rate,
                )

                order = self.client.create_order(order_args)
                response = self.client.post_order(order, OrderType.GTC)

                order_id = response.get("orderID") or response.get("order_id")
                status = response.get("status", "submitted").lower()

                # Determine fill status
                if status in ("matched", "filled"):
                    fill_price = price
                    fill_size = size
                    order_status = OrderStatus.FILLED
                else:
                    fill_price = None
                    fill_size = None
                    order_status = OrderStatus.SUBMITTED

                logger.info(f"Order submitted: {order_id} status={order_status.value}")

                # Record order
                self._record_order(token_id, order_id, price, size, order_status)

                return OrderResult(
                    success=True,
                    order_id=order_id,
                    status=order_status,
                    fill_price=fill_price,
                    fill_size=fill_size,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Order attempt {attempt + 1} failed: {e}")

                # Check for balance error
                if "balance" in str(e).lower() and not balance_refreshed:
                    logger.info("Refreshing balance cache...")
                    self.refresh_balance_cache()
                    balance_refreshed = True

                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)

        logger.error(f"Order failed after {self.config.max_retries} attempts")
        return OrderResult(
            success=False,
            order_id=None,
            status=OrderStatus.ERROR,
            message=f"max_retries:{last_error}",
        )

    def _round_to_tick(self, price: float, tick_size: str) -> float:
        """Round price to valid tick."""
        tick = float(tick_size)
        return round(price / tick) * tick

    def _record_order(
        self,
        token_id: str,
        order_id: str,
        price: float,
        size: float,
        status: OrderStatus,
    ) -> None:
        """Record order in database."""
        order = Order(
            order_id=order_id,
            token_id=token_id,
            side="buy",
            order_price=price,
            order_size=size,
            status=status.value,
        )
        self.order_repo.create(order)
```

### `exit_manager.py` - Exit Strategy

```python
"""
Exit manager for position exits.

Implements exit strategies:
- Resolution: Hold to market resolution
- Profit target: Exit at 99c for quick profit
- Stop loss: Exit at 90c to limit losses

Strategy (from Dec 2025 research):
- Short positions (<7 days): Hold to resolution
- Long positions (>7 days): Apply conditional exits
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..storage.database import Database
from ..storage.repositories.position_repo import Position, PositionRepository

logger = logging.getLogger(__name__)


class ExitType(str, Enum):
    RESOLUTION = "resolution"
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    MANUAL = "manual"


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    position_id: str  # Stored as text for UUID/string compatibility
    exit_type: ExitType
    trigger_price: float
    reason: str


@dataclass
class ExitConfig:
    """Exit strategy configuration."""
    # Conditional exit thresholds
    profit_target_price: float = 0.99  # Exit if price hits 99c
    stop_loss_price: float = 0.90      # Exit if price drops to 90c

    # When to apply conditional exits
    min_days_for_exit: float = 7.0     # Only apply to positions > 7 days old

    # Capital efficiency
    max_position_age_days: float = 90.0  # Force review after 90 days


class ExitManager:
    """
    Manages position exit strategies.

    Key insight from research:
    - Short positions (<7d): High win rate, quick turnover → hold to resolution
    - Long positions (>7d): Risk of capital being tied up → use exits

    Conditional exits improve capital efficiency ~3.2x for long positions.
    """

    def __init__(
        self,
        db: Database,
        config: Optional[ExitConfig] = None,
        get_current_price: Optional[callable] = None,
    ) -> None:
        self.db = db
        self.config = config or ExitConfig()
        self.position_repo = PositionRepository(db)
        self._get_price = get_current_price

    async def check_exits(self) -> List[ExitSignal]:
        """
        Check all open positions for exit conditions.

        Returns list of exit signals.
        """
        signals = []
        positions = self.position_repo.get_open()

        for position in positions:
            signal = await self._check_position(position)
            if signal:
                signals.append(signal)

        return signals

    async def _check_position(self, position: Position) -> Optional[ExitSignal]:
        """Check single position for exit conditions."""
        import time
        from datetime import datetime

        # Calculate position age
        entry_time = datetime.fromisoformat(position.entry_time)
        now = datetime.utcnow()
        days_held = (now - entry_time).total_seconds() / 86400

        # Short positions: no conditional exits
        if days_held < self.config.min_days_for_exit:
            return None

        # Get current price
        if not self._get_price:
            return None

        current_price = await self._get_price(position.token_id)
        if current_price is None:
            return None

        # Check profit target
        if current_price >= self.config.profit_target_price:
            return ExitSignal(
                position_id=str(position.id),
                exit_type=ExitType.PROFIT_TARGET,
                trigger_price=current_price,
                reason=f"price={current_price:.4f}>={self.config.profit_target_price}",
            )

        # Check stop loss
        if current_price <= self.config.stop_loss_price:
            return ExitSignal(
                position_id=str(position.id),
                exit_type=ExitType.STOP_LOSS,
                trigger_price=current_price,
                reason=f"price={current_price:.4f}<={self.config.stop_loss_price}",
            )

        # Check if position is too old (capital efficiency)
        if days_held > self.config.max_position_age_days:
            logger.warning(
                f"Position {position.id} is {days_held:.0f} days old. "
                f"Consider manual review."
            )

        return None

    async def execute_exit(
        self,
        signal: ExitSignal,
        order_manager: "OrderManager",
    ) -> bool:
        """Execute an exit signal."""
        position = self.position_repo.get_by_id(int(signal.position_id))
        if not position:
            logger.warning(f"Position {signal.position_id} not found")
            return False

        logger.info(
            f"Executing {signal.exit_type.value} exit for position {position.id}: "
            f"{signal.reason}"
        )

        # Create sell signal
        from ..strategies.base import Signal, SignalAction

        sell_signal = Signal(
            action=SignalAction.SELL,
            token_id=position.token_id,
            condition_id=position.condition_id,
            price=signal.trigger_price,
            size=position.shares,
            strategy_name="exit_manager",
            reason=signal.reason,
        )

        # Would call order_manager to submit sell order
        # Simplified here
        return True
```

---

## Part 3: CLAUDE.md Files

### Core Engine CLAUDE.md

```markdown
# Core Engine

## Purpose
Orchestrate the trading flow from data → strategy → execution.

## Responsibilities
- Receive market data from Ingestion
- Build StrategyContext for strategies
- Invoke strategies and collect signals
- Route signals to Execution
- Manage WebSocket subscriptions
- Run watchlist re-scoring

## NOT Responsibilities
- Fetching data (Ingestion Layer)
- Strategy logic (Strategies Layer)
- Executing orders (Execution Layer)
- Storing data (Storage Layer)

## Key Files

| File | Purpose |
|------|---------|
| `engine.py` | Main TradingEngine orchestrator |
| `signal_router.py` | Routes signals to handlers |
| `context_builder.py` | Builds StrategyContext |
| `watchlist_manager.py` | Deferred trade management |

## Data Flow

```
WebSocket → parse_price_updates → TradingEngine._handle_price_update
    → ContextBuilder.build (token_id + price → StrategyContext)
    → Strategy.on_price_update (returns Signal)
    → SignalRouter.handle_* (routes to Execution)
```

## Critical Gotchas

### 1. WebSocket Has No Trade Size
When strategy returns WATCH signal with reason="price_trigger_needs_trade_data",
engine must fetch trade from REST API before re-invoking strategy.

### 2. Dual-Key Deduplication
Both TriggerRepository.has_triggered() AND has_condition_triggered() must be
checked to prevent duplicate trades from multiple token_ids.

### 3. Balance Cache on Startup
Call OrderManager.refresh_balance_cache() on engine startup.
```

### Execution Layer CLAUDE.md

```markdown
# Execution Layer

## Purpose
Handle order submission, position tracking, and exits.

## Responsibilities
- Submit orders to Polymarket CLOB
- Track order status (submitted → filled)
- Track positions (entry → exit)
- Manage exit strategies (profit target, stop loss)
- Enforce risk limits

## NOT Responsibilities
- Making trading decisions (Strategies)
- Fetching market data (Ingestion)
- Data storage logic (Storage - uses repositories)

## Key Files

| File | Purpose |
|------|---------|
| `order_manager.py` | CLOB order submission |
| `position_tracker.py` | Position lifecycle |
| `exit_manager.py` | Exit strategies |
| `risk_manager.py` | Risk controls |
| `wallet.py` | Balance checking |

## Critical Gotchas

### 1. Orderbook Verification (BELICHICK BUG)
ALWAYS verify orderbook price matches trigger price before submitting.
Reject if deviation > 10 cents.

### 2. Balance Cache Staleness
CLOB API caches balance server-side. Call `refresh_balance_cache()`:
- On startup
- After balance-related errors
- Periodically (every few hours)

### 3. Tick Size Rounding
Prices must be rounded to valid tick size (usually 0.01).

### 4. Exit Strategy Timing
- Short positions (<7d): Hold to resolution
- Long positions (>7d): Apply profit target (99c) + stop loss (90c)
```

---

This completes the Core Engine and Execution Layer specs. Ready for the Health Check and Services spec?
