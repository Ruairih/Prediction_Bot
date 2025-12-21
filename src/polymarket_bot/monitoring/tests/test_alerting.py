"""
Tests for alerting and notifications.

Alerts notify operators of important events.
"""
import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock

from polymarket_bot.monitoring.alerting import AlertManager


class TestTelegramAlerts:
    """Tests for Telegram notification sending."""

    def test_sends_alert_message(self, alert_manager, mock_telegram_api):
        """Should send message via Telegram API."""
        result = alert_manager.send_alert(
            title="Trade Executed",
            message="Bought 20 shares at $0.95",
        )

        assert result is True
        mock_telegram_api.send_message.assert_called_once()

    def test_formats_message_correctly(self, alert_manager, mock_telegram_api):
        """Should format message with title and content."""
        alert_manager.send_alert(
            title="Test Alert",
            message="Test message content",
        )

        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "Test Alert" in text
        assert "Test message content" in text

    def test_handles_api_error_gracefully(self, alert_manager, mock_telegram_api):
        """Should not crash on Telegram API errors."""
        mock_telegram_api.send_message.side_effect = Exception("API error")

        # Should not raise
        result = alert_manager.send_alert(title="Test", message="Test")

        assert result is False

    def test_returns_false_without_credentials(self):
        """Should return false when credentials not configured."""
        manager = AlertManager(
            telegram_bot_token=None,
            telegram_chat_id=None,
        )

        result = manager.send_alert(title="Test", message="Test")

        assert result is False


class TestAlertDeduplication:
    """Tests for alert deduplication."""

    def test_deduplicates_repeated_alerts(self, alert_manager, mock_telegram_api):
        """
        GOTCHA: Same alert can fire repeatedly during issues.

        Must deduplicate to avoid notification spam.
        """
        # Send same alert twice
        alert_manager.send_alert(
            title="Duplicate Alert",
            message="Same message",
            dedup_key="test_key",
        )
        alert_manager.send_alert(
            title="Duplicate Alert",
            message="Same message",
            dedup_key="test_key",
        )

        # Should only send once
        assert mock_telegram_api.send_message.call_count == 1

    def test_allows_different_alerts(self, alert_manager, mock_telegram_api):
        """Should send different alerts."""
        alert_manager.send_alert(
            title="Alert 1",
            message="Message 1",
            dedup_key="key_1",
        )
        alert_manager.send_alert(
            title="Alert 2",
            message="Message 2",
            dedup_key="key_2",
        )

        assert mock_telegram_api.send_message.call_count == 2

    def test_allows_same_alert_without_dedup_key(self, alert_manager, mock_telegram_api):
        """Should send alerts without dedup key every time."""
        for _ in range(3):
            alert_manager.send_alert(
                title="No Dedup",
                message="Repeated message",
            )

        assert mock_telegram_api.send_message.call_count == 3

    def test_deduplicates_with_cooldown(self, alert_manager, mock_telegram_api):
        """Should use custom cooldown when specified."""
        alert_manager.send_alert(
            title="Cooldown Test",
            message="Test",
            dedup_key="cooldown_key",
            cooldown_seconds=1,  # 1 second
        )

        # Immediate second attempt should be blocked
        alert_manager.send_alert(
            title="Cooldown Test",
            message="Test",
            dedup_key="cooldown_key",
            cooldown_seconds=1,
        )

        assert mock_telegram_api.send_message.call_count == 1

        # Wait for cooldown to expire
        time.sleep(1.1)

        # Now should send
        alert_manager.send_alert(
            title="Cooldown Test",
            message="Test",
            dedup_key="cooldown_key",
            cooldown_seconds=1,
        )

        assert mock_telegram_api.send_message.call_count == 2

    def test_spam_prevention(self, alert_manager, mock_telegram_api):
        """Should not spam alerts during issues."""
        for _ in range(10):
            alert_manager.send_alert(
                title="Same Error",
                message="Same message",
                dedup_key="spam_prevention",
            )

        # Should only send once
        assert mock_telegram_api.send_message.call_count == 1

    def test_clear_dedup_cache(self, alert_manager, mock_telegram_api):
        """Should allow resending after clearing cache."""
        alert_manager.send_alert(
            title="Test",
            message="Test",
            dedup_key="clear_test",
        )

        assert mock_telegram_api.send_message.call_count == 1

        # Clear cache
        alert_manager.clear_dedup_cache()

        # Now should send again
        alert_manager.send_alert(
            title="Test",
            message="Test",
            dedup_key="clear_test",
        )

        assert mock_telegram_api.send_message.call_count == 2


class TestAlertTypes:
    """Tests for different alert types."""

    def test_trade_execution_alert(self, alert_manager, mock_telegram_api):
        """Should send trade execution alert."""
        result = alert_manager.alert_trade_executed(
            token_id="tok_abc123456789",
            side="BUY",
            price=Decimal("0.95"),
            size=Decimal("20"),
        )

        assert result is True
        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "BUY" in text
        assert "0.95" in text

    def test_health_alert(self, alert_manager, mock_telegram_api):
        """Should send health degradation alert."""
        result = alert_manager.alert_health_issue(
            component="websocket",
            status="UNHEALTHY",
            message="Connection lost",
        )

        assert result is True
        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "websocket" in text.lower()
        assert "Connection lost" in text

    def test_low_balance_alert(self, alert_manager, mock_telegram_api):
        """Should send low balance alert."""
        result = alert_manager.alert_low_balance(
            current_balance=Decimal("50.00"),
            threshold=Decimal("100.00"),
        )

        assert result is True
        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "50.00" in text
        assert "100.00" in text

    def test_position_opened_alert(self, alert_manager, mock_telegram_api):
        """Should send position opened alert."""
        result = alert_manager.alert_position_opened(
            position_id="pos_123",
            token_id="tok_abc123456789",
            size=Decimal("20"),
            entry_price=Decimal("0.95"),
        )

        assert result is True
        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "Position" in text
        assert "0.95" in text

    def test_position_closed_alert(self, alert_manager, mock_telegram_api):
        """Should send position closed alert."""
        result = alert_manager.alert_position_closed(
            position_id="pos_123",
            exit_price=Decimal("0.99"),
            realized_pnl=Decimal("0.80"),
            reason="profit_target",
        )

        assert result is True
        call_args = mock_telegram_api.send_message.call_args
        text = call_args[1]["text"]

        assert "Closed" in text
        assert "0.80" in text
        assert "profit_target" in text


class TestAlertPriority:
    """Tests for alert priority formatting."""

    def test_critical_priority_formatting(self, alert_manager):
        """Critical alerts should have special formatting."""
        formatted = alert_manager._format_message(
            title="Critical Alert",
            message="System down",
            priority="critical",
        )

        assert "🚨" in formatted

    def test_high_priority_formatting(self, alert_manager):
        """High priority alerts should have warning markers."""
        formatted = alert_manager._format_message(
            title="High Priority",
            message="Issue detected",
            priority="high",
        )

        assert "⚠️" in formatted

    def test_low_priority_formatting(self, alert_manager):
        """Low priority alerts should have info markers."""
        formatted = alert_manager._format_message(
            title="Low Priority",
            message="FYI message",
            priority="low",
        )

        assert "ℹ️" in formatted


class TestAlertStats:
    """Tests for alert statistics tracking."""

    def test_get_alert_stats(self, alert_manager, mock_telegram_api):
        """Should track alert statistics."""
        alert_manager.send_alert(title="Test 1", message="Test", dedup_key="key1")
        alert_manager.send_alert(title="Test 2", message="Test", dedup_key="key2")
        alert_manager.send_alert(title="Test 2", message="Test", dedup_key="key2")  # Dup

        stats = alert_manager.get_alert_stats()

        assert stats["unique_alerts"] == 2
        assert stats["total_sent"] == 2  # One was deduplicated
