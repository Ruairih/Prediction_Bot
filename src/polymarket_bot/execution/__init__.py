"""
Execution Layer - Order management and position tracking.

This module provides:
    - ExecutionService: Main facade for trade execution (use this!)
    - ExecutionConfig: Configuration for execution service
    - ExecutionResult: Result of execution attempts
    - OrderManager: Submit orders to Polymarket CLOB, track status
    - OrderConfig: Configuration for order submission
    - Order: Order data class
    - OrderStatus: Order status enum
    - PositionTracker: Aggregate fills, track positions, calculate P&L
    - Position: Position data class
    - ExitEvent: Exit event record
    - ExitManager: Exit strategy execution (short vs long positions)
    - ExitConfig: Configuration for exit strategies
    - BalanceManager: USDC balance tracking with cache refresh (G4 fix)
    - BalanceConfig: Configuration for balance management
    - Exceptions: PriceTooHighError, InsufficientBalanceError

Critical Gotchas Handled:
    - G4: CLOB Balance Cache Staleness - Refresh after every fill
    - G5: Orderbook Verification - Called before submitting orders
    - G13: Exit Slippage Protection - Verify liquidity before exits (Gold Cards bug)
    - G14: Entry Liquidity Verification - Check spread before orders (Dead Orders bug)

Exit Strategy Logic:
    - Short positions (<7 days): Hold to resolution (99%+ win rate)
    - Long positions (>7 days): Apply profit target (99c) and stop-loss (90c)

Usage:
    # The ExecutionService is the primary interface for the engine
    from polymarket_bot.execution import ExecutionService, ExecutionConfig

    service = ExecutionService(db, clob_client, ExecutionConfig())
    await service.load_state()

    result = await service.execute_entry(signal, context)
"""

# Execution service (main facade - use this!)
from .service import (
    ExecutionService,
    ExecutionConfig,
    ExecutionResult,
)

# Balance management (G4 protection)
from .balance_manager import (
    BalanceManager,
    BalanceConfig,
    InsufficientBalanceError,
    PreSubmitValidationError,
    Reservation,
)

# Order management
from .order_manager import (
    OrderManager,
    OrderConfig,
    Order,
    OrderStatus,
    PriceTooHighError,
)

# Position tracking
from .position_tracker import (
    PositionTracker,
    Position,
    ExitEvent,
)

# Exit strategies
from .exit_manager import (
    ExitManager,
    ExitConfig,
)

__all__ = [
    # Execution service (main facade)
    "ExecutionService",
    "ExecutionConfig",
    "ExecutionResult",
    # Balance management (G4 protection)
    "BalanceManager",
    "BalanceConfig",
    "InsufficientBalanceError",
    "PreSubmitValidationError",
    "Reservation",
    # Order management
    "OrderManager",
    "OrderConfig",
    "Order",
    "OrderStatus",
    "PriceTooHighError",
    # Position tracking
    "PositionTracker",
    "Position",
    "ExitEvent",
    # Exit strategies
    "ExitManager",
    "ExitConfig",
]
