"""
Trade size filter.

The size >= 50 filter is CRITICAL for win rate.
Production data showed +3.5 percentage points improvement (95.7% → 99%+).

This filter ensures we only trade on significant volume, avoiding
thin markets where prices may not be reliable.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional


def passes_size_filter(
    trade_size: Optional[Decimal], min_size: int = 50
) -> bool:
    """
    Check if trade size meets minimum threshold.

    This is one of the most important filters for win rate.
    Small trades may indicate thin markets or price anomalies.

    Args:
        trade_size: Size of the trade (may be None if from WebSocket - G3)
        min_size: Minimum required size (default 50)

    Returns:
        True if trade_size >= min_size, False otherwise

    Note:
        Returns False if trade_size is None. Callers should either:
        1. Backfill size from REST API (G3 workaround)
        2. Skip the size filter for WebSocket-only events
    """
    if trade_size is None:
        return False

    # Handle both Decimal and numeric types
    try:
        return trade_size >= min_size
    except TypeError:
        return False


def size_filter_result(
    trade_size: Optional[Decimal], min_size: int = 50
) -> tuple[bool, str]:
    """
    Check size filter and return result with reason.

    Args:
        trade_size: Size of the trade
        min_size: Minimum required size

    Returns:
        (passes, reason) tuple
    """
    if trade_size is None:
        return False, "Trade size unknown (G3 - WebSocket limitation)"

    if trade_size < min_size:
        return False, f"Trade size {trade_size} < {min_size}"

    return True, ""
