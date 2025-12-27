"""
Score Bridge - Fetches model scores from legacy SQLite database.

The legacy trading system calculated model scores using a logistic regression
model (logit-trained-20251125) and stored them in SQLite. This bridge allows
the new PostgreSQL-based bot to access those scores.

Usage:
    bridge = ScoreBridge("/data/guardrail.sqlite")
    score = bridge.get_score(token_id)
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class ScoreBridge:
    """
    Bridge to read model scores from legacy SQLite database.

    Thread-safe with connection pooling per thread.
    Uses an in-memory cache to minimize SQLite reads.
    """

    def __init__(
        self,
        sqlite_path: str = "/data/guardrail.sqlite",
        cache_size: int = 10000,
    ):
        """
        Initialize the score bridge.

        Args:
            sqlite_path: Path to the legacy SQLite database
            cache_size: Max entries to cache in memory
        """
        self._sqlite_path = sqlite_path
        self._cache_size = cache_size

        # Thread-local storage for SQLite connections
        self._local = threading.local()

        # In-memory cache: token_id -> (score, model_version)
        self._cache: dict[str, tuple[Optional[float], Optional[str]]] = {}
        self._cache_lock = threading.Lock()

        # Track if SQLite is available
        self._available = self._check_availability()

        if self._available:
            logger.info(f"ScoreBridge initialized with {sqlite_path}")
        else:
            logger.warning(f"ScoreBridge: SQLite not available at {sqlite_path}")

    def _check_availability(self) -> bool:
        """Check if SQLite database is accessible."""
        try:
            # Use immutable mode to avoid journal/WAL file creation
            # This is necessary because the database may be actively written by another process
            uri = f"file:{self._sqlite_path}?immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.execute("SELECT 1 FROM polymarket_first_triggers LIMIT 1")
            conn.close()
            return True
        except Exception as e:
            logger.debug(f"SQLite not available: {e}")
            return False

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        """Get thread-local SQLite connection."""
        if not self._available:
            return None

        if not hasattr(self._local, 'conn') or self._local.conn is None:
            try:
                # Use immutable mode to avoid journal/WAL file creation
                uri = f"file:{self._sqlite_path}?immutable=1"
                self._local.conn = sqlite3.connect(
                    uri,
                    uri=True,
                    timeout=5.0,
                    check_same_thread=False,
                )
                self._local.conn.row_factory = sqlite3.Row
            except Exception as e:
                logger.warning(f"Failed to connect to SQLite: {e}")
                return None

        return self._local.conn

    def get_score(self, token_id: str) -> tuple[Optional[float], Optional[str]]:
        """
        Get model score for a token.

        Args:
            token_id: The token ID to look up

        Returns:
            (model_score, model_version) tuple, or (None, None) if not found
        """
        if not token_id:
            return None, None

        # Check cache first
        with self._cache_lock:
            if token_id in self._cache:
                return self._cache[token_id]

        # Query SQLite
        conn = self._get_connection()
        if conn is None:
            return None, None

        try:
            cursor = conn.execute(
                """
                SELECT model_score, model_version
                FROM polymarket_first_triggers
                WHERE token_id = ?
                ORDER BY trigger_timestamp DESC
                LIMIT 1
                """,
                (token_id,)
            )
            row = cursor.fetchone()

            if row and row['model_score'] is not None:
                score = float(row['model_score'])
                version = row['model_version']
            else:
                score, version = None, None

            # Cache result
            with self._cache_lock:
                if len(self._cache) >= self._cache_size:
                    # Simple eviction: remove first entry
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]
                self._cache[token_id] = (score, version)

            return score, version

        except Exception as e:
            logger.debug(f"Error fetching score for {token_id}: {e}")
            return None, None

    def get_score_by_condition(self, condition_id: str) -> tuple[Optional[float], Optional[str]]:
        """
        Get model score by condition ID (market ID).

        Falls back to condition_id if token_id lookup fails.

        Args:
            condition_id: The market condition ID

        Returns:
            (model_score, model_version) tuple, or (None, None) if not found
        """
        if not condition_id:
            return None, None

        conn = self._get_connection()
        if conn is None:
            return None, None

        try:
            cursor = conn.execute(
                """
                SELECT model_score, model_version
                FROM polymarket_first_triggers
                WHERE condition_id = ?
                ORDER BY trigger_timestamp DESC
                LIMIT 1
                """,
                (condition_id,)
            )
            row = cursor.fetchone()

            if row and row['model_score'] is not None:
                return float(row['model_score']), row['model_version']

            return None, None

        except Exception as e:
            logger.debug(f"Error fetching score by condition {condition_id}: {e}")
            return None, None

    def is_available(self) -> bool:
        """Check if the bridge is operational."""
        return self._available

    def get_stats(self) -> dict:
        """Get bridge statistics."""
        with self._cache_lock:
            cache_size = len(self._cache)

        return {
            "available": self._available,
            "sqlite_path": self._sqlite_path,
            "cache_size": cache_size,
            "cache_max": self._cache_size,
        }


# Global instance for convenience
_default_bridge: Optional[ScoreBridge] = None


def get_score_bridge() -> ScoreBridge:
    """Get the default score bridge instance."""
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = ScoreBridge()
    return _default_bridge
