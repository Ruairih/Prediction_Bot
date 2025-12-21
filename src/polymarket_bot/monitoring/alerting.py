"""
Alert Manager for Telegram notifications.

Sends alerts with deduplication to prevent spam.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AlertRecord:
    """Tracks when an alert was last sent."""

    key: str
    last_sent: float  # Unix timestamp
    count: int = 1


class AlertManager:
    """
    Manages alerts with deduplication.

    Sends alerts via Telegram and prevents duplicate alerts
    within a cooldown window.

    Usage:
        manager = AlertManager(
            telegram_bot_token="...",
            telegram_chat_id="...",
        )

        # Send alert
        manager.send_alert(
            title="Trade Executed",
            message="Bought 20 shares",
            dedup_key="trade_123",
        )

        # Specialized alerts
        manager.alert_trade_executed(token_id, "BUY", price, size)
        manager.alert_health_issue("websocket", "UNHEALTHY", "Connection lost")
    """

    DEFAULT_COOLDOWN = 300  # 5 minutes

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        default_cooldown: int = DEFAULT_COOLDOWN,
        _telegram_api: Optional[Any] = None,  # For testing
    ) -> None:
        """
        Initialize the alert manager.

        Args:
            telegram_bot_token: Bot token from @BotFather
            telegram_chat_id: Chat ID to send messages to
            default_cooldown: Default cooldown between duplicate alerts
            _telegram_api: Injected API client for testing
        """
        self._bot_token = telegram_bot_token
        self._chat_id = telegram_chat_id
        self._default_cooldown = default_cooldown
        self._telegram_api = _telegram_api

        # Alert deduplication tracking
        self._sent_alerts: Dict[str, AlertRecord] = {}

    def send_alert(
        self,
        title: str,
        message: str,
        dedup_key: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
        priority: str = "normal",
    ) -> bool:
        """
        Send an alert via Telegram.

        Args:
            title: Alert title
            message: Alert message body
            dedup_key: Key for deduplication (None to skip dedup)
            cooldown_seconds: Cooldown for this specific alert
            priority: Priority level ("low", "normal", "high", "critical")

        Returns:
            True if alert was sent, False if deduplicated
        """
        # Check deduplication
        if dedup_key:
            cooldown = cooldown_seconds or self._default_cooldown
            if not self._should_send(dedup_key, cooldown):
                logger.debug(f"Deduplicated alert: {dedup_key}")
                return False

        # Format message
        formatted = self._format_message(title, message, priority)

        # Send via Telegram
        success = self._send_telegram(formatted)

        # Record for deduplication
        if dedup_key and success:
            self._record_sent(dedup_key)

        return success

    def alert_trade_executed(
        self,
        token_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        order_id: Optional[str] = None,
    ) -> bool:
        """
        Send a trade execution alert.

        Args:
            token_id: Token that was traded
            side: BUY or SELL
            price: Execution price
            size: Number of shares
            order_id: Optional order ID

        Returns:
            True if sent
        """
        emoji = "🟢" if side == "BUY" else "🔴"
        title = f"{emoji} Trade Executed"

        message = f"""
Side: {side}
Token: {token_id[:20]}...
Price: ${float(price):.4f}
Size: {size} shares
Cost: ${float(price * size):.2f}
"""
        if order_id:
            message += f"Order ID: {order_id}"

        return self.send_alert(
            title=title,
            message=message,
            dedup_key=f"trade_{order_id or token_id}",
            cooldown_seconds=60,  # 1 minute cooldown for same trade
            priority="normal",
        )

    def alert_health_issue(
        self,
        component: str,
        status: str,
        message: str,
    ) -> bool:
        """
        Send a health issue alert.

        Args:
            component: Component name (database, websocket, etc.)
            status: Health status (UNHEALTHY, DEGRADED, etc.)
            message: Description of the issue

        Returns:
            True if sent
        """
        emoji = "🔴" if status.upper() == "UNHEALTHY" else "🟡"
        title = f"{emoji} Health Issue: {component}"

        formatted_message = f"""
Component: {component}
Status: {status}
Details: {message}
Time: {datetime.now(timezone.utc).isoformat()}
"""

        return self.send_alert(
            title=title,
            message=formatted_message,
            dedup_key=f"health_{component}_{status}",
            cooldown_seconds=300,  # 5 minute cooldown
            priority="high" if status.upper() == "UNHEALTHY" else "normal",
        )

    def alert_low_balance(
        self,
        current_balance: Decimal,
        threshold: Decimal,
    ) -> bool:
        """
        Send a low balance alert.

        Args:
            current_balance: Current USDC balance
            threshold: Minimum threshold

        Returns:
            True if sent
        """
        title = "💰 Low Balance Warning"

        message = f"""
Current Balance: ${float(current_balance):.2f}
Threshold: ${float(threshold):.2f}
Action Required: Add funds to continue trading
"""

        return self.send_alert(
            title=title,
            message=message,
            dedup_key="low_balance",
            cooldown_seconds=3600,  # 1 hour cooldown
            priority="high",
        )

    def alert_position_opened(
        self,
        position_id: str,
        token_id: str,
        size: Decimal,
        entry_price: Decimal,
    ) -> bool:
        """
        Send position opened alert.

        Args:
            position_id: New position ID
            token_id: Token ID
            size: Position size
            entry_price: Entry price

        Returns:
            True if sent
        """
        title = "📈 Position Opened"

        message = f"""
Position: {position_id}
Token: {token_id[:20]}...
Size: {size} shares
Entry: ${float(entry_price):.4f}
Cost: ${float(size * entry_price):.2f}
"""

        return self.send_alert(
            title=title,
            message=message,
            dedup_key=f"position_{position_id}",
            cooldown_seconds=60,
            priority="normal",
        )

    def alert_position_closed(
        self,
        position_id: str,
        exit_price: Decimal,
        realized_pnl: Decimal,
        reason: str,
    ) -> bool:
        """
        Send position closed alert.

        Args:
            position_id: Position ID
            exit_price: Exit price
            realized_pnl: Realized P&L
            reason: Exit reason

        Returns:
            True if sent
        """
        emoji = "🟢" if realized_pnl > 0 else "🔴"
        pnl_sign = "+" if realized_pnl > 0 else ""
        title = f"{emoji} Position Closed"

        message = f"""
Position: {position_id}
Exit Price: ${float(exit_price):.4f}
P&L: {pnl_sign}${float(realized_pnl):.2f}
Reason: {reason}
"""

        return self.send_alert(
            title=title,
            message=message,
            dedup_key=f"close_{position_id}",
            cooldown_seconds=60,
            priority="normal",
        )

    def _should_send(self, key: str, cooldown: int) -> bool:
        """Check if alert should be sent based on cooldown."""
        if key not in self._sent_alerts:
            return True

        record = self._sent_alerts[key]
        now = time.time()

        return (now - record.last_sent) >= cooldown

    def _record_sent(self, key: str) -> None:
        """Record that an alert was sent."""
        now = time.time()

        if key in self._sent_alerts:
            self._sent_alerts[key].last_sent = now
            self._sent_alerts[key].count += 1
        else:
            self._sent_alerts[key] = AlertRecord(key=key, last_sent=now)

    def _format_message(
        self,
        title: str,
        message: str,
        priority: str,
    ) -> str:
        """Format alert message for Telegram."""
        priority_markers = {
            "critical": "🚨🚨🚨",
            "high": "⚠️",
            "normal": "",
            "low": "ℹ️",
        }

        marker = priority_markers.get(priority, "")
        header = f"{marker} *{title}*" if marker else f"*{title}*"

        return f"{header}\n\n{message.strip()}"

    def _send_telegram(self, text: str) -> bool:
        """Send message via Telegram API."""
        # Use injected API for testing
        if self._telegram_api:
            try:
                self._telegram_api.send_message(
                    chat_id=self._chat_id,
                    text=text,
                    parse_mode="Markdown",
                )
                return True
            except Exception as e:
                logger.error(f"Telegram API error: {e}")
                return False

        # Real Telegram sending
        if not self._bot_token or not self._chat_id:
            logger.warning("Telegram credentials not configured")
            return False

        try:
            import requests

            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"Sent Telegram alert: {text[:50]}...")
            return True

        except ImportError:
            logger.warning("requests library not available for Telegram")
            return False
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

    def clear_dedup_cache(self) -> None:
        """Clear the deduplication cache."""
        self._sent_alerts.clear()

    def get_alert_stats(self) -> Dict[str, int]:
        """Get statistics about sent alerts."""
        return {
            "unique_alerts": len(self._sent_alerts),
            "total_sent": sum(r.count for r in self._sent_alerts.values()),
        }
