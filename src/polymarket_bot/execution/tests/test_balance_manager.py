"""
Tests for USDC balance management.

Balance tracking is critical for knowing when we can trade.
G4 Protection: Balance cache staleness handling.
"""
import pytest
from decimal import Decimal

from polymarket_bot.execution import (
    BalanceManager,
    BalanceConfig,
    InsufficientBalanceError,
)


class TestBalanceTracking:
    """Tests for balance queries."""

    def test_fetches_current_balance(self, mock_db, mock_clob_client):
        """Should fetch current USDC balance."""
        manager = BalanceManager(db=mock_db, clob_client=mock_clob_client)

        balance = manager.get_available_balance()

        assert balance == Decimal("1000.00")

    def test_returns_zero_without_client(self, mock_db):
        """Should return zero if no CLOB client."""
        manager = BalanceManager(db=mock_db, clob_client=None)

        balance = manager.get_available_balance()

        assert balance == Decimal("0")

    def test_caches_balance(self, mock_db, mock_clob_client):
        """Should cache balance between calls."""
        manager = BalanceManager(db=mock_db, clob_client=mock_clob_client)

        # First call
        balance1 = manager.get_available_balance()

        # Second call (should use cache)
        balance2 = manager.get_available_balance()

        assert balance1 == balance2
        # Should only call CLOB once
        assert mock_clob_client.get_balance_allowance.call_count == 1


class TestReservations:
    """Tests for balance reservations."""

    def test_tracks_reserved_balance(self, balance_manager):
        """Should track balance reserved for pending orders."""
        # Reserve for pending order
        balance_manager.reserve(amount=Decimal("19.00"), order_id="order_pending")

        available = balance_manager.get_available_balance()

        # $1000 - $19 reserved = $981
        assert available == Decimal("981.00")

    def test_releases_reservation(self, balance_manager):
        """Should release reservation when requested."""
        balance_manager.reserve(amount=Decimal("19.00"), order_id="order_123")
        balance_manager.release_reservation(order_id="order_123")

        available = balance_manager.get_available_balance()

        assert available == Decimal("1000.00")

    def test_has_reservation(self, balance_manager):
        """Should check if reservation exists."""
        balance_manager.reserve(amount=Decimal("19.00"), order_id="order_123")

        assert balance_manager.has_reservation("order_123") is True
        assert balance_manager.has_reservation("order_nonexistent") is False

    def test_get_reservation(self, balance_manager):
        """Should get reservation details."""
        balance_manager.reserve(amount=Decimal("19.00"), order_id="order_123")

        reservation = balance_manager.get_reservation("order_123")

        assert reservation is not None
        assert reservation.order_id == "order_123"
        assert reservation.amount == Decimal("19.00")

    def test_multiple_reservations(self, balance_manager):
        """Should handle multiple reservations."""
        balance_manager.reserve(Decimal("100"), "order_1")
        balance_manager.reserve(Decimal("200"), "order_2")
        balance_manager.reserve(Decimal("50"), "order_3")

        available = balance_manager.get_available_balance()

        # $1000 - $350 = $650
        assert available == Decimal("650.00")


class TestBalanceSafety:
    """Tests for balance safety checks."""

    def test_prevents_over_allocation(self, balance_manager):
        """Should prevent allocating more than available."""
        with pytest.raises(InsufficientBalanceError) as exc_info:
            balance_manager.reserve(amount=Decimal("2000.00"), order_id="big_order")

        assert exc_info.value.required == Decimal("2000.00")

    def test_respects_minimum_reserve(self, mock_db, mock_clob_client):
        """Should maintain minimum reserve balance."""
        manager = BalanceManager(
            db=mock_db,
            clob_client=mock_clob_client,
            min_reserve=Decimal("100.00"),
        )

        # Available for trading: $1000 - $100 reserve = $900
        available = manager.get_tradeable_balance()

        assert available == Decimal("900.00")

    def test_tradeable_includes_reservations(self, mock_db, mock_clob_client):
        """Tradeable balance should account for reservations."""
        manager = BalanceManager(
            db=mock_db,
            clob_client=mock_clob_client,
            min_reserve=Decimal("100.00"),
        )

        manager.reserve(Decimal("200"), "order_1")

        # $1000 - $100 reserve - $200 reserved = $700
        tradeable = manager.get_tradeable_balance()

        assert tradeable == Decimal("700.00")


class TestCacheRefresh:
    """Tests for balance cache refresh (G4 protection)."""

    def test_refresh_fetches_new_balance(self, mock_db, mock_clob_client):
        """Refresh should fetch new balance from CLOB."""
        manager = BalanceManager(db=mock_db, clob_client=mock_clob_client)

        # First call
        manager.get_available_balance()

        # Update mock balance
        mock_clob_client.get_balance_allowance.return_value = {"balance": "500000000"}

        # Regular call uses cache
        cached = manager.get_available_balance()
        assert cached == Decimal("1000.00")

        # Force refresh
        refreshed = manager.refresh_balance()

        assert refreshed == Decimal("500.00")

    def test_refresh_clears_cache(self, mock_db, mock_clob_client):
        """Refresh should clear the cache."""
        manager = BalanceManager(db=mock_db, clob_client=mock_clob_client)

        # Populate cache
        manager.get_available_balance()

        # Update and refresh
        mock_clob_client.get_balance_allowance.return_value = {"balance": "750000000"}
        manager.refresh_balance()

        # Next call should use new value
        balance = manager.get_available_balance()

        assert balance == Decimal("750.00")


class TestStaleReservationCleanup:
    """Tests for cleaning up stale reservations."""

    def test_clears_stale_reservations(self, balance_manager):
        """Should clear old reservations."""
        # Add a reservation
        balance_manager.reserve(Decimal("100"), "old_order")

        # Clear with very short max age (0 seconds = all are stale)
        cleared = balance_manager.clear_stale_reservations(max_age_seconds=0)

        assert cleared == 1
        assert not balance_manager.has_reservation("old_order")

    def test_keeps_recent_reservations(self, balance_manager):
        """Should keep recent reservations."""
        balance_manager.reserve(Decimal("100"), "recent_order")

        # Clear with 1 hour max age
        cleared = balance_manager.clear_stale_reservations(max_age_seconds=3600)

        assert cleared == 0
        assert balance_manager.has_reservation("recent_order")


class TestPartialFillHandling:
    """
    Tests for partial fill reservation adjustment.

    FIX: Partial fills must reduce reservation proportionally.
    The filled portion is now a position, not a pending order.
    """

    def test_adjusts_reservation_for_partial_fill(self, balance_manager):
        """
        Should reduce reservation by filled amount.

        When order is 50% filled, reservation should decrease by 50%.
        """
        # Reserve $100 for an order
        balance_manager.reserve(Decimal("100.00"), "order_partial")

        # Partial fill of $40
        balance_manager.adjust_reservation_for_partial_fill(
            order_id="order_partial",
            filled_amount=Decimal("40.00"),
        )

        # Reservation should now be $60
        reservation = balance_manager.get_reservation("order_partial")
        assert reservation is not None
        assert reservation.amount == Decimal("60.00")

    def test_releases_fully_when_filled_amount_exceeds(self, balance_manager):
        """
        Should release reservation entirely when fill >= reservation.

        Edge case: overfill or exact fill.
        """
        balance_manager.reserve(Decimal("100.00"), "order_full")

        # Full fill (or more)
        balance_manager.adjust_reservation_for_partial_fill(
            order_id="order_full",
            filled_amount=Decimal("100.00"),
        )

        # Reservation should be released
        assert not balance_manager.has_reservation("order_full")

    def test_handles_nonexistent_order_gracefully(self, balance_manager):
        """
        Should not error on adjustment for unknown order.

        Defensive: order might have been released already.
        """
        # Should not raise
        balance_manager.adjust_reservation_for_partial_fill(
            order_id="nonexistent_order",
            filled_amount=Decimal("50.00"),
        )

    def test_multiple_partial_fills(self, balance_manager):
        """
        Should handle multiple partial fills correctly.

        Order filled in 3 tranches: $30, $40, $30 = $100 total.
        """
        balance_manager.reserve(Decimal("100.00"), "order_multi")

        # First partial fill
        balance_manager.adjust_reservation_for_partial_fill(
            "order_multi", Decimal("30.00")
        )
        assert balance_manager.get_reservation("order_multi").amount == Decimal("70.00")

        # Second partial fill
        balance_manager.adjust_reservation_for_partial_fill(
            "order_multi", Decimal("40.00")
        )
        assert balance_manager.get_reservation("order_multi").amount == Decimal("30.00")

        # Final fill completes order
        balance_manager.adjust_reservation_for_partial_fill(
            "order_multi", Decimal("30.00")
        )
        assert not balance_manager.has_reservation("order_multi")

    def test_partial_fill_updates_available_balance(self, balance_manager):
        """
        Partial fill should increase available balance.

        The filled portion is no longer reserved.
        """
        balance_manager.reserve(Decimal("100.00"), "order_pf")

        # Before partial fill
        available_before = balance_manager.get_available_balance()

        # Partial fill of $40
        balance_manager.adjust_reservation_for_partial_fill(
            "order_pf", Decimal("40.00")
        )

        # After partial fill
        available_after = balance_manager.get_available_balance()

        # Available should increase by $40
        assert available_after == available_before + Decimal("40.00")
