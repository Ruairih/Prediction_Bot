"""
Hard filters for pre-strategy rejection.

These filters run BEFORE strategy evaluation. If any filter rejects,
the strategy is never called and an IgnoreSignal is returned.

Critical Gotcha:
    G6 (Rainbow Bug): Use word boundaries in weather regex!
    "Rainbow Six Siege" was incorrectly blocked because it contained "rain".
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..protocol import StrategyContext

# =============================================================================
# WEATHER FILTER (G6 FIX)
# =============================================================================

# Weather-related words that should block a market
# CRITICAL: Use word boundaries (\b) to avoid false positives like "Rainbow"
WEATHER_PATTERN = re.compile(
    r"\b(rain|raining|rainy|rainfall|"
    r"snow|snowing|snowy|snowfall|"
    r"hurricane|hurricanes|"
    r"tornado|tornadoes|"
    r"storm|storms|stormy|thunderstorm|"
    r"flood|floods|flooding|"
    r"weather|forecast|"
    r"temperature|celsius|fahrenheit|"
    r"heatwave|heat wave|cold wave|"
    r"drought|droughts)\b",
    re.IGNORECASE,
)


def is_weather_market(question: str) -> bool:
    """
    Check if a market question is weather-related.

    Uses word boundary matching to avoid false positives.

    Args:
        question: The market question text

    Returns:
        True if the question appears to be about weather

    Examples:
        >>> is_weather_market("Will it rain in NYC tomorrow?")
        True
        >>> is_weather_market("Will Team A win Rainbow Six Siege?")  # G6 fix
        False
        >>> is_weather_market("Hurricane makes landfall in Florida?")
        True
    """
    if not question:
        return False
    return bool(WEATHER_PATTERN.search(question))


# =============================================================================
# TIME FILTER
# =============================================================================


def check_time_filter(
    time_to_end_hours: float, min_hours: float = 6.0
) -> tuple[bool, str]:
    """
    Check if market has enough time remaining before resolution.

    Markets expiring too soon don't have enough time for proper resolution.

    Args:
        time_to_end_hours: Hours until market resolves
        min_hours: Minimum required hours (default 6)

    Returns:
        (passes, reason) tuple
    """
    if time_to_end_hours < min_hours:
        return False, f"Expires in {time_to_end_hours:.1f}h (min {min_hours}h)"
    return True, ""


# =============================================================================
# TRADE AGE FILTER (G1 PROTECTION)
# =============================================================================


def check_trade_age_filter(
    trade_age_seconds: float, max_age_seconds: float = 300.0
) -> tuple[bool, str]:
    """
    Check if the triggering trade is recent enough.

    G1 (Belichick Bug): Polymarket returns "recent" trades that can be
    months old for low-volume markets. We must filter by timestamp.

    Args:
        trade_age_seconds: Age of the trade in seconds
        max_age_seconds: Maximum allowed age (default 300 = 5 minutes)

    Returns:
        (passes, reason) tuple
    """
    if trade_age_seconds > max_age_seconds:
        return False, f"Trade too old ({trade_age_seconds:.0f}s > {max_age_seconds:.0f}s)"
    return True, ""


# =============================================================================
# CATEGORY FILTER
# =============================================================================

# Categories that are blocked from trading
BLOCKED_CATEGORIES = frozenset(
    [
        "Weather",  # High uncertainty, no edge
        "Adult",  # Avoid controversial content
    ]
)


def check_category_filter(
    category: Optional[str], blocked: frozenset[str] = BLOCKED_CATEGORIES
) -> tuple[bool, str]:
    """
    Check if market category is allowed.

    Args:
        category: Market category (may be None)
        blocked: Set of blocked category names

    Returns:
        (passes, reason) tuple
    """
    if category and category in blocked:
        return False, f"Blocked category: {category}"
    return True, ""


# =============================================================================
# COMBINED HARD FILTERS
# =============================================================================


def apply_hard_filters(context: "StrategyContext") -> tuple[bool, str]:
    """
    Apply all hard filters to a context.

    Hard filters run BEFORE strategy evaluation. If any filter
    rejects, the strategy is never called.

    Filter order (most common rejections first for efficiency):
    1. Trade age (G1 - Belichick Bug)
    2. Weather market (G6 - Rainbow Bug)
    3. Time to end
    4. Category blocklist

    Args:
        context: Strategy context with market data

    Returns:
        (should_reject, reason) tuple
        If should_reject is True, reason explains why.
    """
    # 1. Trade age (G1 - Belichick Bug)
    passes, reason = check_trade_age_filter(context.trade_age_seconds)
    if not passes:
        return True, f"G1: {reason}"

    # 2. Weather filter (G6 - Rainbow Bug)
    if is_weather_market(context.question):
        return True, "G6: Weather market"

    # 3. Time to end
    passes, reason = check_time_filter(context.time_to_end_hours)
    if not passes:
        return True, reason

    # 4. Category blocklist
    passes, reason = check_category_filter(context.category)
    if not passes:
        return True, reason

    return False, ""
