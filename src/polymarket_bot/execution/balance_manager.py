"""
Balance Manager for USDC tracking.

Handles balance tracking with cache refresh to avoid G4 staleness issues.

Critical Gotcha (G4):
    Polymarket's balance API caches aggressively. Must refresh after every
    order fill to avoid showing stale balances.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)


class PreSubmitValidationError(Exception):
    """
    Base class for errors that occur BEFORE order submission.

    These errors are safe to retry - the trigger can be removed
    because no order was placed.
    """

    pass


class InsufficientBalanceError(PreSubmitValidationError):
    """Raised when balance is too low for an operation."""

    def __init__(self, required: Decimal, available: Decimal):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient balance: required {required}, available {available}"
        )


@dataclass
class BalanceConfig:
    """Configuration for balance management."""

    min_reserve: Decimal = Decimal("100")  # Minimum to keep unreserved
    cache_ttl_seconds: float = 60.0  # How long to cache balance


@dataclass
class Reservation:
    """A balance reservation for a pending order."""

    order_id: str
    amount: Decimal
    created_at: datetime


class BalanceManager:
    """
    Manages USDC balance with reservation tracking.

    G4 Protection: Always refresh balance after fills to avoid stale cache.

    Usage:
        manager = BalanceManager(db, clob_client)

        # Check available balance
        available = manager.get_available_balance()

        # Reserve for pending order
        manager.reserve(Decimal("19.00"), "order_123")

        # After fill, release and refresh
        manager.release_reservation("order_123")
        manager.refresh_balance()  # CRITICAL: G4 protection
    """

    def __init__(
        self,
        db: "Database",
        clob_client: Optional[Any] = None,
        config: Optional[BalanceConfig] = None,
        min_reserve: Optional[Decimal] = None,  # Convenience parameter
    ) -> None:
        """
        Initialize the balance manager.

        Args:
            db: Database connection
            clob_client: Polymarket CLOB client for balance queries
            config: Balance configuration
            min_reserve: Convenience override for minimum reserve
        """
        self._db = db
        self._clob_client = clob_client
        self._config = config or BalanceConfig()

        if min_reserve is not None:
            self._config.min_reserve = min_reserve

        # Cached balance
        self._cached_balance: Optional[Decimal] = None
        self._cache_time: Optional[datetime] = None

        # Active reservations
        self._reservations: Dict[str, Reservation] = {}

    def get_available_balance(self) -> Decimal:
        """
        Get available USDC balance (total - reserved).

        Returns:
            Available balance for trading
        """
        total = self._get_cached_or_fetch_balance()
        reserved = self._total_reserved()
        return total - reserved

    def get_tradeable_balance(self) -> Decimal:
        """
        Get balance available for trading (available - min reserve).

        Returns:
            Balance that can be used for new trades
        """
        available = self.get_available_balance()
        return max(Decimal("0"), available - self._config.min_reserve)

    def get_total_balance(self) -> Decimal:
        """
        Get total USDC balance (not accounting for reservations).

        Returns:
            Total balance from CLOB
        """
        return self._get_cached_or_fetch_balance()

    def reserve(self, amount: Decimal, order_id: str) -> None:
        """
        Reserve balance for a pending order.

        Args:
            amount: Amount to reserve
            order_id: Order ID for the reservation

        Raises:
            InsufficientBalanceError: If not enough balance available
        """
        available = self.get_tradeable_balance()

        if amount > available:
            raise InsufficientBalanceError(required=amount, available=available)

        self._reservations[order_id] = Reservation(
            order_id=order_id,
            amount=amount,
            created_at=datetime.now(timezone.utc),
        )
        logger.debug(f"Reserved {amount} for order {order_id}")

    def release_reservation(self, order_id: str) -> None:
        """
        Release a reservation (after fill or cancel).

        Args:
            order_id: Order ID to release
        """
        if order_id in self._reservations:
            reservation = self._reservations.pop(order_id)
            logger.debug(f"Released reservation of {reservation.amount} for {order_id}")

    def adjust_reservation_for_partial_fill(
        self,
        order_id: str,
        filled_amount: Decimal,
    ) -> None:
        """
        Adjust reservation after a partial fill.

        FIX: Partial fills should reduce the reserved amount proportionally.
        The filled portion no longer needs to be reserved (it's now a position).

        Args:
            order_id: Order ID
            filled_amount: Amount that was filled (cost basis, not size)
        """
        if order_id not in self._reservations:
            return

        reservation = self._reservations[order_id]
        new_amount = reservation.amount - filled_amount

        if new_amount <= Decimal("0"):
            # Fully filled - release entirely
            self.release_reservation(order_id)
        else:
            # Partial fill - update reservation with remaining amount
            self._reservations[order_id] = Reservation(
                order_id=order_id,
                amount=new_amount,
                created_at=reservation.created_at,
            )
            logger.debug(
                f"Adjusted reservation for {order_id}: "
                f"{reservation.amount} -> {new_amount} (filled {filled_amount})"
            )

    def has_reservation(self, order_id: str) -> bool:
        """
        Check if an order has an active reservation.

        Args:
            order_id: Order ID to check

        Returns:
            True if reservation exists
        """
        return order_id in self._reservations

    def get_reservation(self, order_id: str) -> Optional[Reservation]:
        """
        Get reservation details.

        Args:
            order_id: Order ID

        Returns:
            Reservation if exists, None otherwise
        """
        return self._reservations.get(order_id)

    def refresh_balance(self) -> Decimal:
        """
        Force refresh balance from CLOB (G4 protection).

        CRITICAL: Call this after every order fill to avoid stale cache.

        Returns:
            Fresh balance from CLOB
        """
        self._cached_balance = None
        self._cache_time = None
        return self._fetch_balance()

    def _get_cached_or_fetch_balance(self) -> Decimal:
        """Get balance from cache or fetch if stale."""
        now = datetime.now(timezone.utc)

        # Check if cache is valid
        if (
            self._cached_balance is not None
            and self._cache_time is not None
        ):
            age = (now - self._cache_time).total_seconds()
            if age < self._config.cache_ttl_seconds:
                return self._cached_balance

        # Fetch fresh balance
        return self._fetch_balance()

    def _fetch_balance(self) -> Decimal:
        """Fetch balance from CLOB client."""
        if self._clob_client is None:
            # No client - return zero for testing
            return Decimal("0")

        try:
            # py-clob-client uses get_balance_allowance for USDC balance
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            result = self._clob_client.get_balance_allowance(params)

            # Result contains 'balance' field (in USDC units with 6 decimals)
            balance_str = result.get("balance", "0")
            # Convert from micro-units (6 decimals) to USDC
            balance = Decimal(str(balance_str)) / Decimal("1000000")

            # Cache the result
            self._cached_balance = balance
            self._cache_time = datetime.now(timezone.utc)

            return balance

        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            # Return cached if available, else zero
            return self._cached_balance or Decimal("0")

    def _total_reserved(self) -> Decimal:
        """Calculate total reserved balance."""
        return sum(
            r.amount for r in self._reservations.values()
        ) if self._reservations else Decimal("0")

    def get_active_reservations(self) -> list[Reservation]:
        """
        Get all active reservations.

        Returns:
            List of active reservations
        """
        return list(self._reservations.values())

    def clear_stale_reservations(self, max_age_seconds: float = 3600) -> int:
        """
        Clear reservations older than max_age.

        This is a safety mechanism for orphaned reservations.

        Args:
            max_age_seconds: Maximum age for reservations

        Returns:
            Number of reservations cleared
        """
        now = datetime.now(timezone.utc)
        stale_ids = [
            r.order_id for r in self._reservations.values()
            if (now - r.created_at).total_seconds() > max_age_seconds
        ]

        for order_id in stale_ids:
            self.release_reservation(order_id)

        return len(stale_ids)
