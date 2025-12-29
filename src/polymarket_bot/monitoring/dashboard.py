"""
Dashboard for web-based monitoring.

Provides a Flask application with REST endpoints and SSE streaming.

SECURITY:
- Optional API key authentication via DASHBOARD_API_KEY env var
- HTML output is escaped to prevent XSS
- Bind to localhost by default for security
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
import queue
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, List, Optional

try:
    from flask import Flask, Response, jsonify, request, abort
except ImportError:
    Flask = None  # type: ignore
    Response = None  # type: ignore
    jsonify = None  # type: ignore
    request = None  # type: ignore
    abort = None  # type: ignore

if TYPE_CHECKING:
    from polymarket_bot.storage import Database

logger = logging.getLogger(__name__)

# API key from environment (optional)
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY")


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def require_api_key(f: Callable) -> Callable:
    """
    Decorator to require API key authentication.

    If DASHBOARD_API_KEY is set in environment, requests must include
    either:
    - X-API-Key header
    - api_key query parameter

    If DASHBOARD_API_KEY is not set, authentication is disabled.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_API_KEY:
            # No API key configured - allow access
            return f(*args, **kwargs)

        # Check header first, then query param
        provided_key = request.headers.get("X-API-Key") or request.args.get("api_key")

        if not provided_key or provided_key != DASHBOARD_API_KEY:
            logger.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            abort(401)

        return f(*args, **kwargs)

    return decorated


def escape_for_html(value: Any) -> str:
    """Safely escape a value for HTML output to prevent XSS."""
    if value is None:
        return ""
    return html.escape(str(value))


class Dashboard:
    """
    Dashboard web application.

    Provides REST API endpoints and SSE streaming for real-time updates.

    Endpoints:
        GET /health - System health status
        GET /api/positions - Current open positions
        GET /api/watchlist - Watchlist entries
        GET /api/metrics - Trading metrics
        GET /api/stream - SSE event stream

    Usage:
        dashboard = Dashboard(db)
        app = dashboard.create_app()
        app.run(port=5050)
    """

    def __init__(
        self,
        db: Optional["Database"] = None,
        health_checker: Optional[Any] = None,
        metrics_collector: Optional[Any] = None,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
        engine: Optional[Any] = None,
        execution_service: Optional[Any] = None,
        bot_config: Optional[Any] = None,
        shutdown_callback: Optional[Callable[[str], Any]] = None,
        started_at: Optional[datetime] = None,
    ) -> None:
        """
        Initialize the dashboard.

        Args:
            db: Database connection
            health_checker: HealthChecker instance
            metrics_collector: MetricsCollector instance
            event_loop: Main asyncio event loop for dispatching async calls.
                       CRITICAL: Flask runs in a separate thread, so we must
                       use run_coroutine_threadsafe() to execute async DB calls
                       on the main loop where asyncpg pool was created.
        """
        self._db = db
        self._health_checker = health_checker
        self._metrics_collector = metrics_collector
        self._event_loop = event_loop
        self._engine = engine
        self._execution_service = execution_service
        self._bot_config = bot_config
        self._shutdown_callback = shutdown_callback
        self._started_at = started_at or datetime.now(timezone.utc)
        self._max_total_exposure_override: Optional[Decimal] = None

        # SSE subscribers
        self._sse_queues: List[queue.Queue] = []
        self._sse_lock = threading.Lock()

    def _run_async(self, coro, timeout: float = 10.0) -> Any:
        """
        Run an async coroutine from the Flask thread safely.

        Uses run_coroutine_threadsafe to dispatch to the main event loop
        where the asyncpg pool was created. This avoids "attached to a
        different loop" errors.

        Args:
            coro: Coroutine to execute
            timeout: Timeout in seconds

        Returns:
            Result of the coroutine

        Raises:
            RuntimeError: If event loop is not running (shutdown in progress)
            TimeoutError: If operation times out
        """
        import concurrent.futures

        if self._event_loop is None:
            # Fallback: create new loop (only for testing without main loop)
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        # Check if loop is still running (prevents hangs during shutdown)
        if self._event_loop.is_closed() or not self._event_loop.is_running():
            raise RuntimeError("Event loop is not running (shutdown in progress)")

        # Dispatch to main event loop from Flask thread
        future = asyncio.run_coroutine_threadsafe(coro, self._event_loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            # Cancel the task to avoid piling up stale coroutines
            future.cancel()
            logger.error(f"Async operation timed out after {timeout}s")
            raise TimeoutError(f"Operation timed out after {timeout}s")

    async def ensure_control_tables(self) -> None:
        """Ensure control/audit tables exist."""
        if not self._db:
            return

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_actions (
                id SERIAL PRIMARY KEY,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                actor TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS market_blocks (
                condition_id TEXT PRIMARY KEY,
                token_id TEXT,
                reason TEXT,
                actor TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

    async def load_blocklist(self) -> None:
        """Load persisted market blocks into the engine."""
        if not self._db or not self._engine:
            return

        await self.ensure_control_tables()
        records = await self._db.fetch(
            "SELECT condition_id, reason FROM market_blocks"
        )
        blocks = {
            r["condition_id"]: r.get("reason") or "manual_block"
            for r in records
            if r.get("condition_id")
        }
        self._engine.set_blocklist(blocks)

    def _format_timestamp(self, value: Any) -> str:
        """Normalize timestamps to ISO strings."""
        if value is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, (int, float)):
            ts = value
            if ts > 4102444800:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                return value
        return str(value)

    def _map_health_status(self, status: Any) -> str:
        """Map health status enums to API-friendly strings."""
        if hasattr(status, "value"):
            value = str(status.value)
        else:
            value = str(status)

        if value == "warning":
            return "degraded"
        return value

    async def _record_action(
        self,
        action_type: str,
        status: str,
        details: Optional[dict] = None,
        actor: str = "dashboard",
        reason: Optional[str] = None,
    ) -> None:
        """Persist a dashboard action for auditability."""
        if not self._db:
            return

        await self.ensure_control_tables()

        payload = json.dumps(details or {})
        created_at = datetime.now(timezone.utc).isoformat()
        query = """
            INSERT INTO dashboard_actions
            (action_type, status, details, actor, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        await self._db.execute(
            query,
            action_type,
            status,
            payload,
            actor,
            reason,
            created_at,
        )

    async def _fetch_scores_for_conditions(
        self, condition_ids: list[str]
    ) -> dict[str, float]:
        """
        Fetch model scores from market_scores_cache for given condition IDs.

        Returns dict mapping condition_id -> model_score.
        """
        if not self._db or not condition_ids:
            return {}

        # Use ANY() for efficient batch lookup
        query = """
            SELECT condition_id, model_score
            FROM market_scores_cache
            WHERE condition_id = ANY($1)
              AND model_score IS NOT NULL
        """
        rows = await self._db.fetch(query, condition_ids)
        return {row["condition_id"]: float(row["model_score"]) for row in rows}

    def create_app(self, testing: bool = False) -> "Flask":
        """
        Create the Flask application.

        Args:
            testing: Whether to enable testing mode

        Returns:
            Flask application instance
        """
        if Flask is None:
            raise ImportError(
                "Flask is required for dashboard. Install with: pip install flask"
            )

        app = Flask(__name__)
        app.config["TESTING"] = testing
        app.json_encoder = DecimalEncoder  # type: ignore

        # Store reference for routes
        app.dashboard = self  # type: ignore

        # Register routes
        self._register_routes(app)

        return app

    def _register_routes(self, app: "Flask") -> None:
        """Register all HTTP routes."""

        @app.route("/health")
        @require_api_key
        def health() -> Response:
            """Get overall system health."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if dashboard._health_checker:
                # Run async health check via main event loop
                try:
                    health_result = dashboard._run_async(
                        dashboard._health_checker.check_all()
                    )

                    return jsonify({
                        "status": health_result.status.value,
                        "components": [
                            {
                                "component": c.component,
                                "status": c.status.value,
                                "message": c.message,
                                "latency_ms": c.latency_ms,
                            }
                            for c in health_result.components
                        ],
                        "checked_at": health_result.checked_at.isoformat(),
                    })
                except Exception as e:
                    logger.error(f"Health check failed: {e}")
                    return jsonify({
                        "status": "error",
                        "error": str(e),
                    }), 500

            return jsonify({
                "status": "unknown",
                "message": "Health checker not configured",
            })

        @app.route("/api/positions")
        @require_api_key
        def positions() -> Response:
            """Get current open positions."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"positions": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 200, type=int)
                status = request.args.get("status", type=str)
                result = dashboard._run_async(dashboard._get_positions(limit=limit, status=status))
                return jsonify({"positions": result})
            except Exception as e:
                logger.error(f"Failed to get positions: {e}")
                return jsonify({"positions": [], "error": str(e)}), 500

        @app.route("/api/watchlist")
        @require_api_key
        def watchlist() -> Response:
            """Get watchlist entries."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"entries": [], "error": "Database not configured"})

            try:
                result = dashboard._run_async(dashboard._get_watchlist())
                return jsonify({"entries": result})
            except Exception as e:
                logger.error(f"Failed to get watchlist: {e}")
                return jsonify({"entries": [], "error": str(e)}), 500

        @app.route("/api/metrics")
        @require_api_key
        def metrics() -> Response:
            """Get trading metrics."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if dashboard._metrics_collector:
                try:
                    result = dashboard._run_async(
                        dashboard._metrics_collector.get_all_metrics()
                    )

                    return jsonify({
                        "total_trades": result.total_trades,
                        "winning_trades": result.winning_trades,
                        "losing_trades": result.losing_trades,
                        "win_rate": result.win_rate,
                        "total_pnl": float(result.total_pnl),
                        "realized_pnl": float(result.realized_pnl),
                        "unrealized_pnl": float(result.unrealized_pnl),
                        "position_count": result.position_count,
                        "capital_deployed": float(result.capital_deployed),
                        "available_balance": float(result.available_balance),
                        "calculated_at": result.calculated_at.isoformat(),
                    })
                except Exception as e:
                    logger.error(f"Failed to get metrics: {e}")
                    return jsonify({"error": str(e)}), 500

            return jsonify({
                "total_trades": 0,
                "win_rate": 0.0,
                "error": "Metrics collector not configured",
            })

        @app.route("/api/status")
        @require_api_key
        def status() -> Response:
            """Get bot status and mode."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            try:
                result = dashboard._run_async(dashboard._get_status())
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get status: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/risk", methods=["GET", "POST"])
        @require_api_key
        def risk() -> Response:
            """Get or update risk limits."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if request.method == "POST":
                payload = request.get_json(silent=True) or {}
                try:
                    result = dashboard._run_async(dashboard._update_risk_limits(payload))
                    return jsonify(result)
                except Exception as e:
                    logger.error(f"Failed to update risk limits: {e}")
                    return jsonify({"error": str(e)}), 500

            try:
                result = dashboard._run_async(dashboard._get_risk())
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get risk status: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/activity")
        @require_api_key
        def activity() -> Response:
            """Get merged activity log."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"events": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 200, type=int)
                result = dashboard._run_async(dashboard._get_activity(limit))
                return jsonify({"events": result})
            except Exception as e:
                logger.error(f"Failed to get activity: {e}")
                return jsonify({"events": [], "error": str(e)}), 500

        @app.route("/api/performance")
        @require_api_key
        def performance() -> Response:
            """Get performance summary."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"error": "Database not configured"}), 500

            try:
                range_days = request.args.get("range_days", type=int)
                limit = request.args.get("limit", 200, type=int)
                result = dashboard._run_async(
                    dashboard._get_performance(range_days=range_days, limit=limit)
                )
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get performance: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/system")
        @require_api_key
        def system() -> Response:
            """Get system configuration and uptime."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            try:
                result = dashboard._run_async(dashboard._get_system_config())
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get system config: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/logs")
        @require_api_key
        def logs() -> Response:
            """Get log-style events for the system page."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"logs": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 200, type=int)
                result = dashboard._run_async(dashboard._get_logs(limit))
                return jsonify({"logs": result})
            except Exception as e:
                logger.error(f"Failed to get logs: {e}")
                return jsonify({"logs": [], "error": str(e)}), 500

        @app.route("/api/strategy")
        @require_api_key
        def strategy() -> Response:
            """Get current strategy configuration."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            try:
                result = dashboard._run_async(dashboard._get_strategy())
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get strategy: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/decisions")
        @require_api_key
        def decisions() -> Response:
            """Get recent strategy decisions."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"decisions": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 100, type=int)
                result = dashboard._run_async(dashboard._get_decisions(limit))
                return jsonify({"decisions": result})
            except Exception as e:
                logger.error(f"Failed to get decisions: {e}")
                return jsonify({"decisions": [], "error": str(e)}), 500

        @app.route("/api/control/pause", methods=["POST"])
        @require_api_key
        def control_pause() -> Response:
            """Pause trading."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"error": "Engine not configured"}), 500

            reason = (request.get_json(silent=True) or {}).get("reason", "manual")
            dashboard._engine.pause(reason=reason)
            dashboard.broadcast_event({
                "type": "bot_state",
                "state": "paused",
                "reason": reason,
            })
            dashboard._run_async(dashboard._record_action("pause", "ok", {"reason": reason}))
            return jsonify({"status": "paused"})

        @app.route("/api/control/resume", methods=["POST"])
        @require_api_key
        def control_resume() -> Response:
            """Resume trading."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"error": "Engine not configured"}), 500

            dashboard._engine.resume()
            dashboard.broadcast_event({
                "type": "bot_state",
                "state": "running",
            })
            dashboard._run_async(dashboard._record_action("resume", "ok", {}))
            return jsonify({"status": "running"})

        @app.route("/api/control/kill", methods=["POST"])
        @require_api_key
        def control_kill() -> Response:
            """Kill switch - request bot shutdown."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._shutdown_callback:
                return jsonify({"error": "Shutdown callback not configured"}), 500

            reason = (request.get_json(silent=True) or {}).get("reason", "kill_switch")
            dashboard._run_async(dashboard._shutdown_callback(reason))
            dashboard.broadcast_event({
                "type": "bot_state",
                "state": "stopping",
                "reason": reason,
            })
            dashboard._run_async(dashboard._record_action("kill", "ok", {"reason": reason}))
            return jsonify({"status": "stopping"})

        @app.route("/api/orders/cancel_all", methods=["POST"])
        @require_api_key
        def cancel_all_orders() -> Response:
            """Cancel all open orders."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._execution_service:
                return jsonify({"error": "Execution service not configured"}), 500

            try:
                cancelled = dashboard._run_async(dashboard._execution_service.cancel_all_orders())
                dashboard._run_async(
                    dashboard._record_action("cancel_all_orders", "ok", {"count": cancelled})
                )
                return jsonify({"cancelled": cancelled})
            except Exception as e:
                logger.error(f"Failed to cancel orders: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/positions/flatten", methods=["POST"])
        @require_api_key
        def flatten_positions() -> Response:
            """Close all open positions."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._execution_service:
                return jsonify({"error": "Execution service not configured"}), 500

            reason = (request.get_json(silent=True) or {}).get("reason", "manual_flatten")
            try:
                closed = dashboard._run_async(dashboard._execution_service.flatten_positions(reason=reason))
                dashboard._run_async(
                    dashboard._record_action("flatten_positions", "ok", {"count": closed, "reason": reason})
                )
                return jsonify({"closed": closed})
            except Exception as e:
                logger.error(f"Failed to flatten positions: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/positions/refresh", methods=["POST"])
        @require_api_key
        def refresh_positions() -> Response:
            """
            Reload positions from database into in-memory tracker.

            Use this after external changes (manual DB edits, CLI sync).
            """
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._execution_service:
                return jsonify({"error": "Execution service not configured"}), 500

            try:
                # Access the position tracker and reload from DB
                tracker = dashboard._execution_service._position_tracker
                dashboard._run_async(tracker.load_positions())
                count = len(tracker.get_open_positions())
                dashboard._run_async(
                    dashboard._record_action("refresh_positions", "ok", {"count": count})
                )
                return jsonify({"success": True, "positions_loaded": count})
            except Exception as e:
                logger.error(f"Failed to refresh positions: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/positions/<position_id>/close", methods=["POST"])
        @require_api_key
        def close_position(position_id: str) -> Response:
            """Close a specific position."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._execution_service:
                return jsonify({"error": "Execution service not configured"}), 500

            payload = request.get_json(silent=True) or {}
            reason = payload.get("reason", "manual_close")
            current_price = payload.get("price")
            token_id = payload.get("token_id")

            # Dashboard rows use DB ids; map them to in-memory position ids via token_id.
            resolved_position_id = position_id
            if token_id:
                match = dashboard._execution_service.get_position_by_token(token_id)
                if match:
                    resolved_position_id = match.position_id
            if resolved_position_id == position_id and dashboard._db:
                try:
                    db_id = int(position_id)
                except (TypeError, ValueError):
                    db_id = None
                if db_id is not None:
                    record = dashboard._run_async(
                        dashboard._db.fetchrow(
                            "SELECT token_id FROM positions WHERE id = $1",
                            db_id,
                        )
                    )
                    if record and record.get("token_id"):
                        match = dashboard._execution_service.get_position_by_token(record["token_id"])
                        if match:
                            resolved_position_id = match.position_id

            try:
                # FIX: Don't wait for fill - submit order and return immediately.
                # Background sync will track the order and close position when filled.
                # This prevents dashboard timeout (10s) from cancelling the exit order.
                result = dashboard._run_async(
                    dashboard._execution_service.close_position(
                        position_id=resolved_position_id,
                        reason=reason,
                        current_price=Decimal(str(current_price)) if current_price is not None else None,
                        wait_for_fill=False,  # Return immediately after order submission
                    )
                )
                dashboard._run_async(
                    dashboard._record_action(
                        "close_position",
                        "ok" if result.success else "failed",
                        {"position_id": position_id, "reason": reason},
                    )
                )
                response_data = {
                    "success": result.success,
                    "error": result.error,
                    "position_id": result.position_id,
                    "message": "Exit order submitted. Position will close when order fills." if result.success else None,
                }
                if result.order_id:
                    response_data["order_id"] = result.order_id
                return jsonify(response_data)
            except Exception as e:
                logger.error(f"Failed to close position {position_id}: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/markets")
        @require_api_key
        def markets() -> Response:
            """Get markets from streaming watchlist."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"markets": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 200, type=int)
                category = request.args.get("category", type=str)
                search = request.args.get("q", type=str)
                result = dashboard._run_async(
                    dashboard._get_markets(limit=limit, category=category, search=search)
                )
                return jsonify({"markets": result})
            except Exception as e:
                logger.error(f"Failed to get markets: {e}")
                return jsonify({"markets": [], "error": str(e)}), 500

        @app.route("/api/market/<condition_id>")
        @require_api_key
        def market_detail(condition_id: str) -> Response:
            """Get detailed market information."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"error": "Database not configured"}), 500

            try:
                result = dashboard._run_async(dashboard._get_market_detail(condition_id))
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get market detail: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/market/<condition_id>/history")
        @require_api_key
        def market_history(condition_id: str) -> Response:
            """Get market trade history."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"history": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 200, type=int)
                result = dashboard._run_async(
                    dashboard._get_market_history(condition_id, limit=limit)
                )
                return jsonify({"history": result})
            except Exception as e:
                logger.error(f"Failed to get market history: {e}")
                return jsonify({"history": [], "error": str(e)}), 500

        @app.route("/api/market/<condition_id>/orderbook")
        @require_api_key
        def market_orderbook(condition_id: str) -> Response:
            """Get market orderbook snapshot."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            try:
                token_id = request.args.get("token_id")
                result = dashboard._run_async(
                    dashboard._get_market_orderbook(condition_id, token_id=token_id)
                )
                return jsonify(result)
            except Exception as e:
                logger.error(f"Failed to get market orderbook: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/market/<condition_id>/block", methods=["POST", "DELETE"])
        @require_api_key
        def market_block(condition_id: str) -> Response:
            """Block or unblock a market."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine or not dashboard._db:
                return jsonify({"error": "Engine or database not configured"}), 500

            payload = request.get_json(silent=True) or {}
            reason = payload.get("reason", "manual_block")
            token_id = payload.get("token_id")

            try:
                if request.method == "POST":
                    dashboard._run_async(
                        dashboard._block_market(condition_id, token_id=token_id, reason=reason)
                    )
                    return jsonify({"blocked": True})

                dashboard._run_async(dashboard._unblock_market(condition_id))
                return jsonify({"blocked": False})
            except Exception as e:
                logger.error(f"Failed to update blocklist: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/market/blocks")
        @require_api_key
        def market_blocks() -> Response:
            """Get active market blocks."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"blocks": [], "error": "Database not configured"})

            try:
                result = dashboard._run_async(dashboard._get_blocklist())
                return jsonify({"blocks": result})
            except Exception as e:
                logger.error(f"Failed to get market blocks: {e}")
                return jsonify({"blocks": [], "error": str(e)}), 500

        @app.route("/api/triggers")
        @require_api_key
        def triggers() -> Response:
            """Get recent triggers."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"triggers": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 50, type=int)
                result = dashboard._run_async(dashboard._get_triggers(limit))
                return jsonify({"triggers": result})
            except Exception as e:
                logger.error(f"Failed to get triggers: {e}")
                return jsonify({"triggers": [], "error": str(e)}), 500

        @app.route("/api/orders")
        @require_api_key
        def orders() -> Response:
            """Get recent orders."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._db:
                return jsonify({"orders": [], "error": "Database not configured"})

            try:
                limit = request.args.get("limit", 100, type=int)
                result = dashboard._run_async(dashboard._get_orders(limit))
                return jsonify({"orders": result})
            except Exception as e:
                logger.error(f"Failed to get orders: {e}")
                return jsonify({"orders": [], "error": str(e)}), 500

        @app.route("/api/orders/manual", methods=["POST"])
        @require_api_key
        def manual_order() -> Response:
            """Submit a manual order."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._execution_service:
                return jsonify({"error": "Execution service not configured"}), 500

            payload = request.get_json(silent=True) or {}
            token_id = payload.get("token_id")
            side = payload.get("side", "BUY")
            price = payload.get("price")
            size = payload.get("size")
            condition_id = payload.get("condition_id")
            reason = payload.get("reason", "manual_order")

            if not token_id or price is None or size is None:
                return jsonify({"error": "token_id, price, and size are required"}), 400

            try:
                order_id = dashboard._run_async(
                    dashboard._execution_service.order_manager.submit_order(
                        token_id=token_id,
                        side=side,
                        price=Decimal(str(price)),
                        size=Decimal(str(size)),
                        condition_id=condition_id,
                    )
                )
                dashboard.broadcast_event({
                    "type": "order",
                    "action": "manual",
                    "order_id": order_id,
                    "token_id": token_id,
                })
                dashboard._run_async(
                    dashboard._record_action(
                        "manual_order",
                        "ok",
                        details={
                            "order_id": order_id,
                            "token_id": token_id,
                            "side": side,
                            "price": price,
                            "size": size,
                            "condition_id": condition_id,
                            "reason": reason,
                        },
                    )
                )
                return jsonify({"order_id": order_id})
            except Exception as e:
                logger.error(f"Manual order failed: {e}")
                dashboard._run_async(
                    dashboard._record_action(
                        "manual_order",
                        "failed",
                        details={"token_id": token_id, "reason": reason, "error": str(e)},
                    )
                )
                return jsonify({"error": str(e)}), 500

        # =====================================================================
        # Pipeline Visibility Endpoints
        # =====================================================================

        @app.route("/api/pipeline/stats")
        @require_api_key
        def pipeline_stats() -> Response:
            """Get pipeline rejection statistics."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"error": "Engine not configured"}), 500

            try:
                minutes = request.args.get("minutes", 60, type=int)
                tracker = dashboard._engine.pipeline_tracker
                stats = tracker.get_stats(minutes)
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Failed to get pipeline stats: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/pipeline/funnel")
        @require_api_key
        def pipeline_funnel() -> Response:
            """Get pipeline funnel summary for visualization."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"error": "Engine not configured"}), 500

            try:
                minutes = request.args.get("minutes", 60, type=int)
                tracker = dashboard._engine.pipeline_tracker
                summary = tracker.get_funnel_summary(minutes)
                return jsonify(summary)
            except Exception as e:
                logger.error(f"Failed to get pipeline funnel: {e}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/pipeline/rejections")
        @require_api_key
        def pipeline_rejections() -> Response:
            """Get recent detailed rejections."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"rejections": []}), 200

            try:
                limit = request.args.get("limit", 100, type=int)
                stage = request.args.get("stage", type=str)

                tracker = dashboard._engine.pipeline_tracker

                # Convert stage string to enum if provided
                stage_enum = None
                if stage:
                    from polymarket_bot.core.pipeline_tracker import RejectionStage
                    try:
                        stage_enum = RejectionStage(stage)
                    except ValueError:
                        return jsonify({"error": f"Invalid stage: {stage}"}), 400

                rejections = tracker.get_recent_rejections(stage=stage_enum, limit=limit)
                return jsonify({
                    "rejections": [r.to_dict() for r in rejections],
                    "count": len(rejections),
                })
            except Exception as e:
                logger.error(f"Failed to get pipeline rejections: {e}")
                return jsonify({"rejections": [], "error": str(e)}), 500

        @app.route("/api/pipeline/candidates")
        @require_api_key
        def pipeline_candidates() -> Response:
            """Get candidate markets (close to threshold)."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"candidates": []}), 200

            try:
                limit = request.args.get("limit", 50, type=int)
                sort_by = request.args.get("sort", "distance", type=str)

                tracker = dashboard._engine.pipeline_tracker
                candidates = tracker.get_candidates(sort_by=sort_by, limit=limit)

                # Enrich candidates with scores from market_scores_cache
                # This ensures we show scores even for candidates created before scoring was fixed
                candidate_dicts = [c.to_dict() for c in candidates]
                if dashboard._db and candidate_dicts:
                    condition_ids = [c["condition_id"] for c in candidate_dicts if c.get("condition_id")]
                    if condition_ids:
                        try:
                            scores = dashboard._run_async(
                                dashboard._fetch_scores_for_conditions(condition_ids)
                            )
                            # Merge scores into candidates
                            for c in candidate_dicts:
                                cid = c.get("condition_id")
                                if cid and cid in scores and c.get("model_score") is None:
                                    c["model_score"] = scores[cid]
                        except Exception as e:
                            logger.debug(f"Could not enrich candidates with scores: {e}")

                return jsonify({
                    "candidates": candidate_dicts,
                    "count": len(candidate_dicts),
                })
            except Exception as e:
                logger.error(f"Failed to get pipeline candidates: {e}")
                return jsonify({"candidates": [], "error": str(e)}), 500

        @app.route("/api/pipeline/near-misses")
        @require_api_key
        def pipeline_near_misses() -> Response:
            """Get markets that came very close to triggering."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            if not dashboard._engine:
                return jsonify({"near_misses": []}), 200

            try:
                max_distance = request.args.get("max_distance", 0.02, type=float)

                tracker = dashboard._engine.pipeline_tracker
                near_misses = tracker.get_near_misses(Decimal(str(max_distance)))

                # Enrich with scores from market_scores_cache
                near_miss_dicts = [c.to_dict() for c in near_misses]
                if dashboard._db and near_miss_dicts:
                    condition_ids = [c["condition_id"] for c in near_miss_dicts if c.get("condition_id")]
                    if condition_ids:
                        try:
                            scores = dashboard._run_async(
                                dashboard._fetch_scores_for_conditions(condition_ids)
                            )
                            for c in near_miss_dicts:
                                cid = c.get("condition_id")
                                if cid and cid in scores and c.get("model_score") is None:
                                    c["model_score"] = scores[cid]
                        except Exception as e:
                            logger.debug(f"Could not enrich near-misses with scores: {e}")

                return jsonify({
                    "near_misses": near_miss_dicts,
                    "count": len(near_miss_dicts),
                })
            except Exception as e:
                logger.error(f"Failed to get near misses: {e}")
                return jsonify({"near_misses": [], "error": str(e)}), 500

        @app.route("/api/stream")
        @require_api_key
        def stream() -> Response:
            """SSE stream for real-time updates."""
            dashboard: Dashboard = app.dashboard  # type: ignore

            def generate() -> Generator[str, None, None]:
                q: queue.Queue = queue.Queue()

                with dashboard._sse_lock:
                    dashboard._sse_queues.append(q)

                try:
                    # Send initial connection event
                    yield f"data: {json.dumps({'type': 'connected'})}\n\n"

                    while True:
                        try:
                            # Wait for events with timeout
                            event = q.get(timeout=30)
                            yield f"data: {json.dumps(event)}\n\n"
                        except queue.Empty:
                            # Send keepalive
                            yield f": keepalive\n\n"

                finally:
                    with dashboard._sse_lock:
                        if q in dashboard._sse_queues:
                            dashboard._sse_queues.remove(q)

            return Response(
                generate(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        @app.route("/")
        @require_api_key  # FIX: Protect index route to avoid exposing API key
        def index() -> Response:
            """Simple dashboard home page."""
            # FIX: Include API key in JS fetch requests when auth is enabled
            # The key is embedded in the page (only accessible to authenticated users)
            # Since / is now protected, this is safe
            api_key_js = ""
            if DASHBOARD_API_KEY:
                # Escape the key for safe JS embedding
                safe_key = DASHBOARD_API_KEY.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
                api_key_js = f"const API_KEY = '{safe_key}';"
            else:
                api_key_js = "const API_KEY = null;"

            html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Polymarket Bot Dashboard</title>
    <style>
        body {{ font-family: system-ui, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #4fc3f7; }}
        .section {{ background: #16213e; padding: 20px; margin: 10px 0; border-radius: 8px; }}
        .metric {{ display: inline-block; margin: 10px 20px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #4fc3f7; }}
        .metric-label {{ color: #888; }}
        .status-healthy {{ color: #4caf50; }}
        .status-degraded {{ color: #ff9800; }}
        .status-unhealthy {{ color: #f44336; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ color: #888; }}
    </style>
</head>
<body>
    <h1>Polymarket Trading Bot</h1>

    <div class="section">
        <h2>Health Status</h2>
        <div id="health">Loading...</div>
    </div>

    <div class="section">
        <h2>Metrics</h2>
        <div id="metrics">Loading...</div>
    </div>

    <div class="section">
        <h2>Open Positions</h2>
        <div id="positions">Loading...</div>
    </div>

    <script>
        // FIX: API key for authenticated requests (embedded if auth enabled)
        {api_key_js}

        // Helper to build fetch options with auth header
        function fetchOptions() {{
            const opts = {{}};
            if (API_KEY) {{
                opts.headers = {{ 'X-API-Key': API_KEY }};
            }}
            return opts;
        }}

        // XSS-safe: Escape HTML entities in user data
        function escapeHtml(text) {{
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        }}

        // XSS-safe: Create text node instead of innerHTML
        function setTextSafe(el, text) {{
            el.textContent = text;
        }}

        async function loadHealth() {{
            try {{
                const resp = await fetch('/health', fetchOptions());
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                const el = document.getElementById('health');
                // Clear and rebuild safely
                el.innerHTML = '';
                const span = document.createElement('span');
                span.className = 'status-' + escapeHtml(data.status);
                span.textContent = (data.status || 'unknown').toUpperCase();
                el.appendChild(span);
            }} catch (e) {{
                document.getElementById('health').textContent = 'Error loading health';
            }}
        }}

        async function loadMetrics() {{
            try {{
                const resp = await fetch('/api/metrics', fetchOptions());
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                const el = document.getElementById('metrics');

                // Build DOM safely without innerHTML for data values
                el.innerHTML = '';

                const metrics = [
                    {{ value: data.total_trades || 0, label: 'Total Trades' }},
                    {{ value: ((data.win_rate || 0) * 100).toFixed(1) + '%', label: 'Win Rate' }},
                    {{ value: '$' + (data.total_pnl?.toFixed(2) || '0.00'), label: 'Total P&L' }},
                    {{ value: data.position_count || 0, label: 'Open Positions' }}
                ];

                for (const m of metrics) {{
                    const div = document.createElement('div');
                    div.className = 'metric';

                    const valueDiv = document.createElement('div');
                    valueDiv.className = 'metric-value';
                    valueDiv.textContent = String(m.value);

                    const labelDiv = document.createElement('div');
                    labelDiv.className = 'metric-label';
                    labelDiv.textContent = m.label;

                    div.appendChild(valueDiv);
                    div.appendChild(labelDiv);
                    el.appendChild(div);
                }}
            }} catch (e) {{
                document.getElementById('metrics').textContent = 'Error loading metrics';
            }}
        }}

        async function loadPositions() {{
            try {{
                const resp = await fetch('/api/positions', fetchOptions());
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                const el = document.getElementById('positions');

                if (!data.positions || data.positions.length === 0) {{
                    el.innerHTML = '';
                    const p = document.createElement('p');
                    p.textContent = 'No open positions';
                    el.appendChild(p);
                    return;
                }}

                // Build table safely using DOM methods
                const table = document.createElement('table');
                const headerRow = document.createElement('tr');
                ['Token', 'Size', 'Entry', 'Cost'].forEach(h => {{
                    const th = document.createElement('th');
                    th.textContent = h;
                    headerRow.appendChild(th);
                }});
                table.appendChild(headerRow);

                for (const p of data.positions) {{
                    const row = document.createElement('tr');

                    const tokenCell = document.createElement('td');
                    // Safely truncate and display token_id
                    tokenCell.textContent = (p.token_id || '').slice(0, 12) + '...';

                    const sizeCell = document.createElement('td');
                    sizeCell.textContent = String(p.size || 0);

                    const entryCell = document.createElement('td');
                    entryCell.textContent = '$' + String(p.entry_price || 0);

                    const costCell = document.createElement('td');
                    costCell.textContent = '$' + String(p.entry_cost || 0);

                    row.appendChild(tokenCell);
                    row.appendChild(sizeCell);
                    row.appendChild(entryCell);
                    row.appendChild(costCell);
                    table.appendChild(row);
                }}

                el.innerHTML = '';
                el.appendChild(table);
            }} catch (e) {{
                document.getElementById('positions').textContent = 'Error loading positions';
            }}
        }}

        loadHealth();
        loadMetrics();
        loadPositions();

        setInterval(loadHealth, 30000);
        setInterval(loadMetrics, 60000);
        setInterval(loadPositions, 30000);
    </script>
</body>
</html>
"""
            # FIX: Prevent caching of page with embedded API key
            return Response(
                html,
                mimetype="text/html",
                headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
            )

    async def _get_positions(
        self,
        limit: int = 200,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get positions from database."""
        if not self._db:
            return []

        # Use correct column names: id (not position_id), entry_timestamp (not entry_time)
        params: List[Any] = []
        filters: List[str] = []
        if status and status != "all":
            params.append(status)
            filters.append(f"status = ${len(params)}")

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)

        query = f"""
            SELECT id, token_id, condition_id, size, entry_price,
                   entry_cost, current_price, unrealized_pnl,
                   entry_timestamp, realized_pnl, status, description
            FROM positions
            {where_clause}
            ORDER BY entry_timestamp DESC
            LIMIT ${len(params)}
        """
        records = await self._db.fetch(query, *params)

        return [
            {
                "position_id": str(r["id"]),  # Map id to position_id for API compatibility
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "size": float(r["size"]),
                "entry_price": float(r["entry_price"]),
                "entry_cost": float(r["entry_cost"]),
                "current_price": float(r["current_price"]) if r.get("current_price") is not None else None,
                "unrealized_pnl": float(r["unrealized_pnl"]) if r.get("unrealized_pnl") is not None else None,
                "entry_time": r["entry_timestamp"],  # Map entry_timestamp to entry_time for API
                "realized_pnl": float(r.get("realized_pnl", 0) or 0),
                "status": r["status"],
                "description": r.get("description"),
            }
            for r in records
        ]

    async def _get_markets(
        self,
        limit: int = 200,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get market universe snapshot from stream_watchlist."""
        if not self._db:
            return []

        filters: List[str] = []
        params: List[Any] = []

        if category and category.lower() != "all":
            params.append(category)
            filters.append(f"category = ${len(params)}")

        if search:
            params.append(f"%{search}%")
            filters.append(
                f"(question ILIKE ${len(params)} OR slug ILIKE ${len(params)})"
            )

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)

        query = f"""
            SELECT market_id, condition_id, question, category,
                   best_bid, best_ask, liquidity, volume,
                   end_date, generated_at
            FROM stream_watchlist
            {where_clause}
            ORDER BY volume DESC NULLS LAST
            LIMIT ${len(params)}
        """

        records = await self._db.fetch(query, *params)

        return [
            {
                "market_id": r["market_id"],
                "condition_id": r["condition_id"],
                "question": r["question"],
                "category": r.get("category"),
                "best_bid": float(r["best_bid"]) if r.get("best_bid") is not None else None,
                "best_ask": float(r["best_ask"]) if r.get("best_ask") is not None else None,
                "liquidity": float(r["liquidity"]) if r.get("liquidity") is not None else None,
                "volume": float(r["volume"]) if r.get("volume") is not None else None,
                "end_date": r.get("end_date"),
                "generated_at": r.get("generated_at"),
            }
            for r in records
        ]

    async def _get_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent orders from execution and live order tables."""
        if not self._db:
            return []

        orders: List[Dict[str, Any]] = []

        # Execution-layer orders table
        exec_query = """
            SELECT order_id, token_id, condition_id, side, price, size,
                   filled_size, avg_fill_price, status, created_at, updated_at
            FROM orders
            ORDER BY created_at DESC
            LIMIT $1
        """
        try:
            exec_records = await self._db.fetch(exec_query, limit)
        except Exception:
            exec_records = []
        for r in exec_records:
            orders.append({
                "order_id": r["order_id"],
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "side": r.get("side"),
                "order_price": float(r["price"]),
                "order_size": float(r["size"]),
                "fill_price": float(r["avg_fill_price"]) if r.get("avg_fill_price") is not None else None,
                "fill_size": float(r["filled_size"]) if r.get("filled_size") is not None else None,
                "status": r["status"],
                "submitted_at": self._format_timestamp(r["created_at"]),
                "filled_at": self._format_timestamp(r["updated_at"]) if r.get("updated_at") else None,
            })

        # Legacy live_orders table (if present)
        live_query = """
            SELECT order_id, token_id, condition_id, order_price, order_size,
                   fill_price, fill_size, status, submitted_at, filled_at
            FROM live_orders
            ORDER BY submitted_at DESC
            LIMIT $1
        """
        try:
            live_records = await self._db.fetch(live_query, limit)
        except Exception:
            live_records = []
        for r in live_records:
            orders.append({
                "order_id": r.get("order_id"),
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "side": None,
                "order_price": float(r["order_price"]) if r.get("order_price") is not None else None,
                "order_size": float(r["order_size"]) if r.get("order_size") is not None else None,
                "fill_price": float(r["fill_price"]) if r.get("fill_price") is not None else None,
                "fill_size": float(r["fill_size"]) if r.get("fill_size") is not None else None,
                "status": r["status"],
                "submitted_at": r["submitted_at"],
                "filled_at": r.get("filled_at"),
            })

        orders.sort(
            key=lambda o: self._format_timestamp(o.get("submitted_at") or ""),
            reverse=True,
        )
        return orders[:limit]

    async def _get_watchlist(self) -> List[Dict[str, Any]]:
        """Get active watchlist entries."""
        if not self._db:
            return []

        query = """
            SELECT token_id, condition_id, question, trigger_price,
                   initial_score, current_score, time_to_end_hours,
                   created_at, status
            FROM trade_watchlist
            WHERE status = 'watching'
            ORDER BY current_score DESC
            LIMIT 100
        """
        records = await self._db.fetch(query)

        return [
            {
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "question": r["question"],
                "trigger_price": float(r["trigger_price"]) if r["trigger_price"] else None,
                "initial_score": r["initial_score"],
                "current_score": r["current_score"],
                "time_to_end_hours": r["time_to_end_hours"],
                "created_at": r["created_at"],
                "status": r["status"],
            }
            for r in records
        ]

    async def _get_triggers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent triggers."""
        if not self._db:
            return []

        query = """
            SELECT token_id, condition_id, threshold, price, trade_size,
                   model_score, triggered_at
            FROM triggers
            ORDER BY triggered_at DESC
            LIMIT $1
        """
        records = await self._db.fetch(query, limit)

        return [
            {
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "threshold": float(r["threshold"]) if r["threshold"] else None,
                "price": float(r["price"]) if r["price"] else None,
                "trade_size": float(r["trade_size"]) if r.get("trade_size") else None,
                "model_score": r.get("model_score"),
                "triggered_at": r["triggered_at"],
            }
            for r in records
        ]

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse timestamps into timezone-aware datetimes."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            ts = value
            if ts > 4102444800:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                return None
        return None

    async def _get_last_trade_time(self) -> Optional[str]:
        """Find the most recent trade-related timestamp."""
        if not self._db:
            return None

        candidates: List[datetime] = []

        queries = [
            ("SELECT MAX(filled_at) AS ts FROM live_orders", "ts"),
            ("SELECT MAX(submitted_at) AS ts FROM live_orders", "ts"),
            ("SELECT MAX(created_at) AS ts FROM orders", "ts"),
            ("SELECT MAX(created_at) AS ts FROM exit_events", "ts"),
        ]

        for query, field in queries:
            try:
                record = await self._db.fetchrow(query)
                if record and record.get(field):
                    dt = self._parse_datetime(record.get(field))
                    if dt:
                        candidates.append(dt)
            except Exception:
                continue

        if not candidates:
            return None

        latest = max(candidates)
        return latest.isoformat()

    async def _get_status(self) -> Dict[str, Any]:
        """Assemble bot status for the dashboard."""
        last_heartbeat = datetime.now(timezone.utc).isoformat()
        health_status = "unknown"
        websocket_connected = False

        if self._health_checker:
            health = await self._health_checker.check_all()
            health_status = self._map_health_status(health.status)
            last_heartbeat = health.checked_at.isoformat()
            websocket = next(
                (c for c in health.components if c.component == "websocket"),
                None,
            )
            if websocket:
                websocket_connected = self._map_health_status(websocket.status) == "healthy"

        mode = "stopped"
        if self._bot_config:
            mode = "dry_run" if self._bot_config.dry_run else "live"
        if self._engine and self._engine.is_paused:
            mode = "paused"
        if not self._engine or not self._engine.is_running:
            mode = "stopped"

        error_rate = 0.0
        if self._engine and self._engine.stats.events_processed:
            error_rate = self._engine.stats.errors / self._engine.stats.events_processed

        last_trade_time = await self._get_last_trade_time()

        from polymarket_bot import __version__

        return {
            "mode": mode,
            "status": health_status,
            "last_heartbeat": last_heartbeat,
            "last_trade_time": last_trade_time,
            "error_rate": error_rate,
            "websocket_connected": websocket_connected,
            "version": __version__,
        }

    async def _get_risk(self) -> Dict[str, Any]:
        """Get risk limits and utilization."""
        if not self._db:
            return {}

        current_exposure = await self._db.fetchval(
            "SELECT COALESCE(SUM(entry_cost), 0) FROM positions WHERE status = 'open'"
        )
        current_exposure = float(current_exposure or 0)

        available_balance = 0.0
        if self._metrics_collector:
            metrics = await self._metrics_collector.get_all_metrics()
            available_balance = float(metrics.available_balance)

        max_positions = (
            int(self._engine.config.max_positions)
            if self._engine and self._engine.config.max_positions is not None
            else 0
        )
        position_size = (
            float(self._execution_service._config.default_position_size)
            if self._execution_service
            else 0.0
        )
        max_total_exposure = (
            float(self._max_total_exposure_override)
            if self._max_total_exposure_override is not None
            else position_size * max_positions
        )

        min_balance_reserve = (
            float(self._execution_service._config.min_balance_reserve)
            if self._execution_service
            else 0.0
        )

        total_assets = available_balance + current_exposure
        exposure_percent = (current_exposure / total_assets * 100) if total_assets else 0.0
        balance_health = (
            min(100.0, (available_balance / min_balance_reserve) * 100)
            if min_balance_reserve
            else 100.0
        )

        limits = {
            "max_position_size": position_size,
            "max_total_exposure": max_total_exposure,
            "max_positions": max_positions,
            "min_balance_reserve": min_balance_reserve,
            "price_threshold": float(self._engine.config.price_threshold)
            if self._engine
            else 0.0,
            "stop_loss": float(self._execution_service._config.stop_loss)
            if self._execution_service
            else 0.0,
            "profit_target": float(self._execution_service._config.profit_target)
            if self._execution_service
            else 0.0,
            "min_hold_days": self._execution_service._config.min_hold_days
            if self._execution_service
            else 0,
        }

        return {
            "current_exposure": current_exposure,
            "exposure_percent": exposure_percent,
            "balance_health": balance_health,
            "limits": limits,
        }

    async def _update_risk_limits(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update runtime risk limits."""
        def pick_value(*keys: str) -> Optional[Any]:
            for key in keys:
                if key in payload and payload[key] is not None:
                    return payload[key]
            return None

        max_position_size = pick_value("maxPositionSize", "max_position_size")
        max_total_exposure = pick_value("maxTotalExposure", "max_total_exposure")
        max_positions = pick_value("maxPositions", "max_positions")
        min_balance_reserve = pick_value("minBalanceReserve", "min_balance_reserve")
        price_threshold = pick_value("priceThreshold", "price_threshold")
        stop_loss = pick_value("stopLoss", "stop_loss")
        profit_target = pick_value("profitTarget", "profit_target")
        min_hold_days = pick_value("minHoldDays", "min_hold_days")
        max_trade_age_seconds = pick_value("maxTradeAgeSeconds", "max_trade_age_seconds")
        max_price_deviation = pick_value("maxPriceDeviation", "max_price_deviation")

        if self._engine:
            self._engine.update_config(
                price_threshold=Decimal(str(price_threshold)) if price_threshold is not None else None,
                position_size=Decimal(str(max_position_size)) if max_position_size is not None else None,
                max_positions=int(max_positions) if max_positions is not None else None,
                max_trade_age_seconds=int(max_trade_age_seconds) if max_trade_age_seconds is not None else None,
                max_price_deviation=Decimal(str(max_price_deviation)) if max_price_deviation is not None else None,
            )

        if self._execution_service:
            self._execution_service.update_config(
                max_price=Decimal(str(price_threshold)) if price_threshold is not None else None,
                default_position_size=Decimal(str(max_position_size))
                if max_position_size is not None
                else None,
                min_balance_reserve=Decimal(str(min_balance_reserve))
                if min_balance_reserve is not None
                else None,
                profit_target=Decimal(str(profit_target)) if profit_target is not None else None,
                stop_loss=Decimal(str(stop_loss)) if stop_loss is not None else None,
                min_hold_days=int(min_hold_days) if min_hold_days is not None else None,
            )

        if min_balance_reserve is not None and self._health_checker:
            try:
                self._health_checker._min_balance_threshold = Decimal(str(min_balance_reserve))
            except Exception:
                pass

        if max_total_exposure is not None:
            self._max_total_exposure_override = Decimal(str(max_total_exposure))

        await self._record_action(
            "risk_update",
            "ok",
            details=payload,
        )

        return await self._get_risk()

    async def _get_activity(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Merge activity events from core tables."""
        if not self._db:
            return []

        events: List[Dict[str, Any]] = []

        trigger_rows = await self._db.fetch(
            """
            SELECT t.token_id, t.condition_id, t.price, t.trade_size, t.model_score, t.triggered_at,
                   p.description
            FROM triggers t
            LEFT JOIN positions p ON t.condition_id = p.condition_id
            ORDER BY t.triggered_at DESC
            LIMIT $1
            """,
            limit,
        )
        for row in trigger_rows:
            timestamp = self._parse_datetime(row.get("triggered_at"))
            question = row.get("description") or f"Token {row['token_id'][:6]}..."
            if len(question) > 50:
                question = question[:47] + "..."
            price_str = f" @ ${float(row['price']):.3f}" if row.get("price") else ""
            events.append({
                "id": f"trigger-{row['token_id']}-{row.get('triggered_at')}",
                "type": "signal",
                "timestamp": self._format_timestamp(row.get("triggered_at")),
                "summary": f"Trigger: {question}{price_str}",
                "details": {
                    "token_id": row["token_id"],
                    "condition_id": row["condition_id"],
                    "price": float(row["price"]) if row.get("price") else None,
                    "trade_size": float(row["trade_size"]) if row.get("trade_size") else None,
                    "model_score": row.get("model_score"),
                    "question": row.get("description"),
                },
                "severity": "info",
                "_sort": timestamp or datetime.now(timezone.utc),
            })

        try:
            order_rows = await self._db.fetch(
                """
                SELECT o.order_id, o.token_id, o.condition_id, o.side, o.price, o.size,
                       o.status, o.created_at, o.updated_at, p.description
                FROM orders o
                LEFT JOIN positions p ON o.condition_id = p.condition_id
                ORDER BY o.created_at DESC
                LIMIT $1
                """,
                limit,
            )
        except Exception:
            order_rows = []
        for row in order_rows:
            status = row.get("status", "pending")
            if status == "filled":
                event_type = "order_filled"
                severity = "success"
            elif status == "cancelled":
                event_type = "order_cancelled"
                severity = "warning"
            elif status == "failed":
                event_type = "error"
                severity = "error"
            else:
                event_type = "order_submitted"
                severity = "info"

            ts_value = row.get("updated_at") if status in ("filled", "cancelled", "failed") else row.get("created_at")
            timestamp = self._parse_datetime(ts_value)
            price = float(row["price"]) if row.get("price") is not None else None
            size = float(row["size"]) if row.get("size") is not None else None
            question = row.get("description") or f"Order {row['token_id'][:6]}..."
            if len(question) > 40:
                question = question[:37] + "..."

            events.append({
                "id": f"order-{row['order_id']}",
                "type": event_type,
                "timestamp": self._format_timestamp(ts_value),
                "summary": f"{status.capitalize()}: {question} | {row.get('side', '')} {size:.0f if size else ''} @ {price:.3f if price else ''}".strip(),
                "details": {
                    "order_id": row["order_id"],
                    "token_id": row["token_id"],
                    "condition_id": row["condition_id"],
                    "side": row.get("side"),
                    "price": price,
                    "size": size,
                    "status": status,
                    "question": row.get("description"),
                },
                "severity": severity,
                "_sort": timestamp or datetime.now(timezone.utc),
            })

        exit_rows = await self._db.fetch(
            """
            SELECT e.id, e.position_id, e.token_id, e.condition_id, e.exit_price, e.size,
                   e.net_pnl, e.reason, e.created_at, p.description
            FROM exit_events e
            LEFT JOIN positions p ON e.position_id::text = p.id::text
            ORDER BY e.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        for row in exit_rows:
            pnl = float(row.get("net_pnl") or 0)
            severity = "success" if pnl >= 0 else "warning"
            timestamp = self._parse_datetime(row.get("created_at"))
            question = row.get("description") or f"Position {row['token_id'][:6]}..."
            # Truncate long questions
            if len(question) > 60:
                question = question[:57] + "..."
            events.append({
                "id": f"exit-{row['id']}",
                "type": "position_closed",
                "timestamp": self._format_timestamp(row.get("created_at")),
                "summary": f"Closed: {question} | PnL ${pnl:.2f}",
                "details": {
                    "position_id": row["position_id"],
                    "token_id": row["token_id"],
                    "condition_id": row.get("condition_id"),
                    "exit_price": float(row["exit_price"]),
                    "size": float(row["size"]),
                    "pnl": pnl,
                    "reason": row.get("reason"),
                    "question": row.get("description"),
                },
                "severity": severity,
                "_sort": timestamp or datetime.now(timezone.utc),
            })

        position_rows = await self._db.fetch(
            """
            SELECT id, token_id, condition_id, entry_price, size, entry_timestamp, description
            FROM positions
            WHERE status = 'open'
            ORDER BY entry_timestamp DESC
            LIMIT $1
            """,
            limit,
        )
        for row in position_rows:
            timestamp = self._parse_datetime(row.get("entry_timestamp"))
            question = row.get("description") or f"Position {row['token_id'][:6]}..."
            # Truncate long questions
            if len(question) > 50:
                question = question[:47] + "..."
            events.append({
                "id": f"position-{row['id']}",
                "type": "position_opened",
                "timestamp": self._format_timestamp(row.get("entry_timestamp")),
                "summary": f"Opened: {question} | {float(row['size']):.0f} @ {float(row['entry_price']):.3f}",
                "details": {
                    "position_id": str(row["id"]),
                    "token_id": row["token_id"],
                    "condition_id": row.get("condition_id"),
                    "entry_price": float(row["entry_price"]),
                    "size": float(row["size"]),
                    "question": row.get("description"),
                },
                "severity": "info",
                "_sort": timestamp or datetime.now(timezone.utc),
            })

        await self.ensure_control_tables()
        action_rows = await self._db.fetch(
            """
            SELECT id, action_type, status, details, reason, created_at
            FROM dashboard_actions
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        for row in action_rows:
            action_type = row["action_type"]
            severity = "info"
            event_type = "alert"
            if action_type in ("pause", "resume", "kill"):
                event_type = "bot_state_change"
                severity = "warning" if action_type != "resume" else "success"
                if action_type == "kill":
                    severity = "error"
            elif action_type == "cancel_all_orders":
                event_type = "order_cancelled"
                severity = "warning"
            elif action_type == "flatten_positions":
                event_type = "position_closed"
                severity = "warning"
            elif action_type in ("block_market", "unblock_market"):
                event_type = "alert"
                severity = "warning" if action_type == "block_market" else "info"

            details = {}
            if row.get("details"):
                try:
                    details = json.loads(row["details"])
                except Exception:
                    details = {"raw": row["details"]}

            timestamp = self._parse_datetime(row.get("created_at"))
            events.append({
                "id": f"action-{row['id']}",
                "type": event_type,
                "timestamp": self._format_timestamp(row.get("created_at")),
                "summary": f"Action: {action_type.replace('_', ' ')}",
                "details": details,
                "severity": severity,
                "_sort": timestamp or datetime.now(timezone.utc),
            })

        events.sort(key=lambda e: e["_sort"], reverse=True)
        trimmed = []
        for event in events[:limit]:
            event.pop("_sort", None)
            trimmed.append(event)
        return trimmed

    async def _get_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Map activity events to log-style entries."""
        events = await self._get_activity(limit)
        logs: List[Dict[str, Any]] = []
        for event in events:
            severity = event.get("severity", "info")
            if severity == "error":
                level = "error"
            elif severity == "warning":
                level = "warning"
            else:
                level = "info"

            logs.append({
                "id": event["id"],
                "timestamp": event["timestamp"],
                "level": level,
                "source": event["type"],
                "message": event["summary"],
            })
        return logs

    async def _get_performance(
        self,
        range_days: Optional[int] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Compute performance summary, equity, and trade history."""
        if not self._db:
            return {}

        cutoff = None
        if range_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=range_days)

        stats_limit = max(limit, 500)
        records = await self._db.fetch(
            """
            SELECT id, position_id, token_id, condition_id, entry_price, exit_price,
                   size, net_pnl, hours_held, reason, created_at
            FROM exit_events
            ORDER BY created_at DESC
            LIMIT $1
            """,
            stats_limit,
        )

        filtered = []
        for row in records:
            closed_at = self._parse_datetime(row.get("created_at"))
            if cutoff and closed_at and closed_at < cutoff:
                continue
            filtered.append((row, closed_at))

        pnls = [float(row.get("net_pnl") or 0) for row, _ in filtered]
        total_trades = len(pnls)
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = (len(wins) / total_trades) if total_trades else 0.0
        profit_factor = (sum(wins) / abs(sum(losses))) if losses else 0.0
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (abs(sum(losses)) / len(losses)) if losses else 0.0
        best_trade = max(pnls) if pnls else 0.0
        worst_trade = min(pnls) if pnls else 0.0

        daily_series: List[Dict[str, Any]] = []
        daily_records = await self._db.fetch(
            """
            SELECT date, total_pnl, realized_pnl, num_trades, num_wins, num_losses
            FROM daily_pnl
            ORDER BY date ASC
            """
        )
        if daily_records:
            for row in daily_records:
                date_value = row["date"]
                daily_series.append({
                    "date": str(date_value),
                    "pnl": float(row.get("total_pnl") or row.get("realized_pnl") or 0),
                    "trades": int(row.get("num_trades") or 0),
                    "wins": int(row.get("num_wins") or 0),
                    "losses": int(row.get("num_losses") or 0),
                })
        else:
            buckets: Dict[str, Dict[str, Any]] = {}
            for row, closed_at in filtered:
                if not closed_at:
                    continue
                key = closed_at.date().isoformat()
                bucket = buckets.setdefault(
                    key, {"date": key, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
                )
                pnl = float(row.get("net_pnl") or 0)
                bucket["pnl"] += pnl
                bucket["trades"] += 1
                if pnl >= 0:
                    bucket["wins"] += 1
                else:
                    bucket["losses"] += 1
            daily_series = [buckets[k] for k in sorted(buckets.keys())]

        if cutoff:
            daily_series = [
                d for d in daily_series
                if self._parse_datetime(d["date"]) and self._parse_datetime(d["date"]) >= cutoff
            ]

        equity_points: List[Dict[str, Any]] = []
        cumulative = 0.0
        for daily in daily_series:
            cumulative += daily["pnl"]
            equity_points.append({
                "timestamp": daily["date"],
                "equity": cumulative,
            })

        max_drawdown = 0.0
        peak = 0.0
        for point in equity_points:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        max_drawdown_percent = (max_drawdown / peak * 100) if peak > 0 else 0.0

        sharpe_ratio = 0.0
        if len(daily_series) > 1:
            returns = [d["pnl"] for d in daily_series]
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance)
            if std_dev > 0:
                sharpe_ratio = (mean / std_dev) * math.sqrt(252)

        trades: List[Dict[str, Any]] = []
        trade_records = filtered[:limit]

        token_ids = list({row["token_id"] for row, _ in trade_records})
        token_questions: Dict[str, str] = {}
        if token_ids:
            meta_records = await self._db.fetch(
                "SELECT token_id, question FROM polymarket_token_meta WHERE token_id = ANY($1)",
                token_ids,
            )
            token_questions = {r["token_id"]: r.get("question") or "" for r in meta_records}

        condition_ids = list({row["condition_id"] for row, _ in trade_records if row.get("condition_id")})
        categories: Dict[str, str] = {}
        if condition_ids:
            market_records = await self._db.fetch(
                "SELECT condition_id, category FROM stream_watchlist WHERE condition_id = ANY($1)",
                condition_ids,
            )
            categories = {r["condition_id"]: r.get("category") or "Unknown" for r in market_records}

        for row, closed_at in trade_records:
            hours_held = float(row.get("hours_held") or 0)
            closed_at = closed_at or datetime.now(timezone.utc)
            opened_at = closed_at - timedelta(hours=hours_held) if hours_held else closed_at
            entry_price = float(row.get("entry_price") or 0)
            size = float(row.get("size") or 0)
            entry_cost = entry_price * size if entry_price and size else 0
            pnl = float(row.get("net_pnl") or 0)
            trades.append({
                "trade_id": str(row["id"]),
                "position_id": row.get("position_id"),
                "token_id": row.get("token_id"),
                "question": token_questions.get(row.get("token_id"), "Unknown market"),
                "side": "BUY",
                "size": size,
                "entry_price": entry_price,
                "exit_price": float(row.get("exit_price") or 0),
                "pnl": pnl,
                "pnl_percent": (pnl / entry_cost * 100) if entry_cost else 0.0,
                "opened_at": opened_at.isoformat(),
                "closed_at": closed_at.isoformat(),
                "holding_period": hours_held / 24 if hours_held else 0.0,
                "category": categories.get(row.get("condition_id"), "Unknown"),
            })

        def group_by_period(period: str) -> List[Dict[str, Any]]:
            buckets: Dict[str, Dict[str, Any]] = {}
            for daily in daily_series:
                dt = self._parse_datetime(daily["date"]) or datetime.now(timezone.utc)
                if period == "weekly":
                    key = f"{dt.isocalendar().year}-W{dt.isocalendar().week}"
                elif period == "monthly":
                    key = dt.strftime("%Y-%m")
                else:
                    key = daily["date"]
                bucket = buckets.setdefault(
                    key, {"period": key, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
                )
                bucket["pnl"] += daily["pnl"]
                bucket["trades"] += daily["trades"]
                bucket["wins"] += daily["wins"]
                bucket["losses"] += daily["losses"]
            items = list(buckets.values())
            return items[-5:] if period != "daily" else items[-7:]

        return {
            "stats": {
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "max_drawdown_percent": max_drawdown_percent,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
            },
            "equity": equity_points,
            "trades": trades,
            "pnl": {
                "daily": group_by_period("daily"),
                "weekly": group_by_period("weekly"),
                "monthly": group_by_period("monthly"),
            },
        }

    async def _get_system_config(self) -> Dict[str, Any]:
        """Return system configuration details."""
        environment = os.environ.get("ENVIRONMENT", "development")
        commit_hash = os.environ.get("GIT_SHA", "unknown")

        from polymarket_bot import __version__

        host = self._bot_config.dashboard_host if self._bot_config else "localhost"
        port = self._bot_config.dashboard_port if self._bot_config else 9050
        api_base_url = f"http://{host}:{port}"

        return {
            "environment": environment,
            "version": __version__,
            "commit_hash": commit_hash,
            "api_base_url": api_base_url,
            "ws_base_url": api_base_url,
            "features": {
                "live_trading": bool(self._bot_config and not self._bot_config.dry_run),
                "alerts": bool(self._bot_config and self._bot_config.telegram_bot_token),
                "streaming": True,
            },
            "uptime": (datetime.now(timezone.utc) - self._started_at).total_seconds(),
        }

    async def _get_strategy(self) -> Dict[str, Any]:
        """Return strategy configuration snapshot."""
        strategy = self._engine.strategy if self._engine and self._engine.strategy else None
        strategy_name = strategy.name if strategy else (self._bot_config.strategy_name if self._bot_config else "unknown")
        strategy_version = getattr(strategy, "version", "1.0.0") if strategy else "1.0.0"
        enabled = bool(self._engine and self._engine.is_running and not self._engine.is_paused)

        from polymarket_bot.strategies.filters.hard_filters import BLOCKED_CATEGORIES

        parameters = [
            {
                "key": "price_threshold",
                "label": "Price Threshold",
                "type": "number",
                "value": float(self._engine.config.price_threshold) if self._engine else 0.0,
                "defaultValue": float(self._engine.config.price_threshold) if self._engine else 0.0,
                "min": 0.5,
                "max": 0.99,
                "step": 0.01,
                "unit": "",
                "description": "Minimum price to trigger entry",
            },
            {
                "key": "position_size",
                "label": "Position Size",
                "type": "number",
                "value": float(self._execution_service._config.default_position_size)
                if self._execution_service
                else 0.0,
                "defaultValue": float(self._execution_service._config.default_position_size)
                if self._execution_service
                else 0.0,
                "min": 1,
                "max": 10000,
                "step": 1,
                "unit": "USD",
                "description": "Default position size in USD",
            },
            {
                "key": "max_positions",
                "label": "Max Positions",
                "type": "number",
                "value": self._engine.config.max_positions if self._engine else 0,
                "defaultValue": self._engine.config.max_positions if self._engine else 0,
                "min": 1,
                "max": 200,
                "step": 1,
                "unit": "",
                "description": "Maximum concurrent positions",
            },
            {
                "key": "max_price_deviation",
                "label": "Max Price Deviation",
                "type": "number",
                "value": float(self._engine.config.max_price_deviation) if self._engine else 0.0,
                "defaultValue": float(self._engine.config.max_price_deviation) if self._engine else 0.0,
                "min": 0.01,
                "max": 0.5,
                "step": 0.01,
                "unit": "",
                "description": "Orderbook deviation guardrail",
            },
            {
                "key": "stop_loss",
                "label": "Stop Loss",
                "type": "number",
                "value": float(self._execution_service._config.stop_loss) if self._execution_service else 0.0,
                "defaultValue": float(self._execution_service._config.stop_loss) if self._execution_service else 0.0,
                "min": 0.1,
                "max": 1.0,
                "step": 0.01,
                "unit": "",
                "description": "Stop loss exit threshold",
            },
            {
                "key": "profit_target",
                "label": "Profit Target",
                "type": "number",
                "value": float(self._execution_service._config.profit_target) if self._execution_service else 0.0,
                "defaultValue": float(self._execution_service._config.profit_target) if self._execution_service else 0.0,
                "min": 0.5,
                "max": 1.0,
                "step": 0.01,
                "unit": "",
                "description": "Profit target exit threshold",
            },
            {
                "key": "min_hold_days",
                "label": "Min Hold Days",
                "type": "number",
                "value": self._execution_service._config.min_hold_days if self._execution_service else 0,
                "defaultValue": self._execution_service._config.min_hold_days if self._execution_service else 0,
                "min": 0,
                "max": 30,
                "step": 1,
                "unit": "days",
                "description": "Minimum hold time before exits apply",
            },
        ]

        return {
            "name": strategy_name,
            "version": strategy_version,
            "enabled": enabled,
            "parameters": parameters,
            "filters": {
                "blockedCategories": sorted(list(BLOCKED_CATEGORIES)),
                "weatherFilterEnabled": True,
                "minTradeSize": float(self._execution_service._config.default_position_size)
                if self._execution_service
                else 0.0,
                "maxTradeAge": self._engine.config.max_trade_age_seconds if self._engine else 300,
                "minTimeToExpiry": 6,
                "maxPriceDeviation": float(self._engine.config.max_price_deviation)
                if self._engine
                else 0.0,
            },
            "lastModified": datetime.now(timezone.utc).isoformat(),
        }

    async def _get_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent decision logs from candidates."""
        if not self._db:
            return []

        records = await self._db.fetch(
            """
            SELECT id, token_id, condition_id, threshold, price, status,
                   score, model_score, created_at
            FROM polymarket_candidates
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )

        token_ids = list({r["token_id"] for r in records})
        questions: Dict[str, str] = {}
        if token_ids:
            meta = await self._db.fetch(
                "SELECT token_id, question FROM polymarket_token_meta WHERE token_id = ANY($1)",
                token_ids,
            )
            questions = {r["token_id"]: r.get("question") or "" for r in meta}

        decisions = []
        for record in records:
            status = record.get("status", "pending")
            if status == "rejected":
                decision = "reject"
            elif status in ("approved", "executed"):
                decision = "entry"
            elif status == "pending":
                decision = "watch"
            else:
                decision = "hold"

            decisions.append({
                "id": str(record["id"]),
                "marketId": record.get("condition_id") or "",
                "tokenId": record.get("token_id"),
                "question": questions.get(record.get("token_id"), "Unknown market"),
                "timestamp": self._format_timestamp(record.get("created_at")),
                "triggerPrice": float(record.get("price") or 0),
                "tradeSize": None,
                "modelScore": record.get("model_score"),
                "decision": decision,
                "reason": status,
                "filters": {
                    "g1Passed": True,
                    "g5Passed": True,
                    "g6Passed": True,
                    "sizePassed": True,
                },
            })

        return decisions

    async def _get_market_detail(self, condition_id: str) -> Dict[str, Any]:
        """Return detailed market snapshot."""
        if not self._db:
            return {}

        record = await self._db.fetchrow(
            """
            SELECT sw.market_id, sw.condition_id, sw.question, sw.category,
                   sw.best_bid, sw.best_ask, sw.liquidity, sw.volume,
                   sw.end_date, sw.generated_at,
                   msc.model_score, msc.spread_pct, msc.time_to_end_hours, msc.filter_rejections
            FROM stream_watchlist sw
            LEFT JOIN market_scores_cache msc ON msc.condition_id = sw.condition_id
            WHERE sw.condition_id = $1
            ORDER BY sw.generated_at DESC
            LIMIT 1
            """,
            condition_id,
        )

        if not record:
            record = await self._db.fetchrow(
                """
                SELECT condition_id, question, category, best_bid, best_ask, liquidity, volume,
                       end_date, updated_at
                FROM market_scores_cache
                WHERE condition_id = $1
                """,
                condition_id,
            )

        question = record.get("question") if record else None
        if not question:
            meta = await self._db.fetchrow(
                "SELECT question FROM polymarket_token_meta WHERE condition_id = $1 LIMIT 1",
                condition_id,
            )
            question = meta.get("question") if meta else None

        token_rows = await self._db.fetch(
            """
            SELECT token_id, outcome, outcome_index
            FROM polymarket_token_meta
            WHERE condition_id = $1
            ORDER BY outcome_index NULLS LAST
            """,
            condition_id,
        )
        tokens = [
            {
                "token_id": r.get("token_id"),
                "outcome": r.get("outcome"),
                "outcome_index": r.get("outcome_index"),
            }
            for r in token_rows
        ]

        best_bid = float(record["best_bid"]) if record and record.get("best_bid") is not None else None
        best_ask = float(record["best_ask"]) if record and record.get("best_ask") is not None else None
        mid_price = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else best_bid or best_ask
        spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None

        position = await self._db.fetchrow(
            """
            SELECT id, token_id, size, entry_price, entry_cost, current_price, current_value,
                   unrealized_pnl, realized_pnl, entry_timestamp, status, side, outcome
            FROM positions
            WHERE condition_id = $1 AND status = 'open'
            ORDER BY entry_timestamp DESC
            LIMIT 1
            """,
            condition_id,
        )

        open_orders = await self._db.fetch(
            """
            SELECT order_id, token_id, side, price, size, status, created_at
            FROM orders
            WHERE condition_id = $1 AND status IN ('pending', 'live', 'partial')
            ORDER BY created_at DESC
            LIMIT 20
            """,
            condition_id,
        )

        last_trade_row = await self._db.fetchrow(
            """
            SELECT trade_id, price, size, side, timestamp
            FROM polymarket_trades
            WHERE condition_id = $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            condition_id,
        )
        last_trade = None
        if last_trade_row:
            last_trade = {
                "trade_id": last_trade_row.get("trade_id"),
                "price": float(last_trade_row.get("price") or 0),
                "size": float(last_trade_row.get("size") or 0),
                "side": last_trade_row.get("side"),
                "timestamp": self._format_timestamp(last_trade_row.get("timestamp")),
            }

        signal_row = await self._db.fetchrow(
            """
            SELECT token_id, status, price, threshold, model_score, created_at
            FROM polymarket_candidates
            WHERE condition_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            condition_id,
        )
        last_signal: Optional[Dict[str, Any]] = None
        if signal_row:
            status = signal_row.get("status", "pending")
            if status == "rejected":
                decision = "reject"
            elif status in ("approved", "executed"):
                decision = "entry"
            elif status == "pending":
                decision = "watch"
            else:
                decision = "hold"
            last_signal = {
                "token_id": signal_row.get("token_id"),
                "status": status,
                "decision": decision,
                "price": float(signal_row.get("price") or 0),
                "threshold": float(signal_row.get("threshold") or 0),
                "model_score": signal_row.get("model_score"),
                "created_at": self._format_timestamp(signal_row.get("created_at")),
            }

        last_fill_row = await self._db.fetchrow(
            """
            SELECT order_id, token_id, side, price, size, filled_size, avg_fill_price, status,
                   created_at, updated_at
            FROM orders
            WHERE condition_id = $1 AND status = 'filled'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            condition_id,
        )
        last_fill: Optional[Dict[str, Any]] = None
        if last_fill_row:
            order_price = float(last_fill_row.get("price") or 0)
            avg_fill = (
                float(last_fill_row.get("avg_fill_price"))
                if last_fill_row.get("avg_fill_price") is not None
                else None
            )
            slippage_bps = None
            if avg_fill is not None and order_price:
                slippage_bps = (avg_fill - order_price) / order_price * 10000
            last_fill = {
                "order_id": last_fill_row.get("order_id"),
                "token_id": last_fill_row.get("token_id"),
                "side": last_fill_row.get("side"),
                "price": order_price,
                "size": float(last_fill_row.get("size") or 0),
                "filled_size": float(last_fill_row.get("filled_size") or 0),
                "avg_fill_price": avg_fill,
                "slippage_bps": slippage_bps,
                "status": last_fill_row.get("status"),
                "filled_at": self._format_timestamp(last_fill_row.get("updated_at")),
            }

        return {
            "market": {
                "market_id": record.get("market_id") if record else None,
                "condition_id": condition_id,
                "question": question or "Unknown market",
                "category": record.get("category") if record else None,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid_price,
                "spread": spread,
                "liquidity": float(record["liquidity"]) if record and record.get("liquidity") is not None else None,
                "volume": float(record["volume"]) if record and record.get("volume") is not None else None,
                "end_date": record.get("end_date") if record else None,
                "updated_at": record.get("generated_at") if record else None,
                "model_score": record.get("model_score") if record else None,
                "time_to_end_hours": record.get("time_to_end_hours") if record else None,
                "filter_rejections": record.get("filter_rejections") if record else None,
            },
            "position": {
                "position_id": str(position["id"]),
                "token_id": position["token_id"],
                "size": float(position["size"]),
                "entry_price": float(position["entry_price"]),
                "entry_cost": float(position["entry_cost"]),
                "current_price": float(position["current_price"]) if position.get("current_price") is not None else None,
                "current_value": float(position["current_value"]) if position.get("current_value") is not None else None,
                "unrealized_pnl": float(position["unrealized_pnl"]) if position.get("unrealized_pnl") is not None else None,
                "realized_pnl": float(position["realized_pnl"] or 0),
                "entry_time": position.get("entry_timestamp"),
                "status": position.get("status"),
                "side": position.get("side"),
                "outcome": position.get("outcome"),
                "pnl_percent": (
                    float(position["unrealized_pnl"]) / float(position["entry_cost"]) * 100
                    if position.get("unrealized_pnl") is not None and position.get("entry_cost")
                    else None
                ),
            } if position else None,
            "orders": [
                {
                    "order_id": r["order_id"],
                    "token_id": r["token_id"],
                    "side": r.get("side"),
                    "price": float(r["price"]),
                    "size": float(r["size"]),
                    "status": r.get("status"),
                    "submitted_at": self._format_timestamp(r.get("created_at")),
                }
                for r in open_orders
            ],
            "tokens": tokens,
            "last_signal": last_signal,
            "last_fill": last_fill,
            "last_trade": last_trade,
        }

    async def _get_market_history(self, condition_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Get recent trades for a market."""
        if not self._db:
            return []

        records = await self._db.fetch(
            """
            SELECT trade_id, price, size, side, timestamp
            FROM polymarket_trades
            WHERE condition_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
            """,
            condition_id,
            limit,
        )

        history = []
        for record in records:
            history.append({
                "trade_id": record.get("trade_id"),
                "price": float(record["price"]) if record.get("price") is not None else None,
                "size": float(record["size"]) if record.get("size") is not None else None,
                "side": record.get("side"),
                "timestamp": self._format_timestamp(record.get("timestamp")),
            })
        return history

    async def _get_market_orderbook(
        self,
        condition_id: str,
        token_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the latest orderbook snapshot for a market/token."""
        if not self._db:
            return {}

        selected_token = token_id
        if not selected_token:
            token_row = await self._db.fetchrow(
                """
                SELECT token_id
                FROM polymarket_token_meta
                WHERE condition_id = $1
                ORDER BY outcome_index NULLS LAST
                LIMIT 1
                """,
                condition_id,
            )
            selected_token = token_row.get("token_id") if token_row else None

        if not selected_token:
            return {
                "condition_id": condition_id,
                "token_id": None,
                "bids": [],
                "asks": [],
                "source": "unavailable",
            }

        try:
            record = await self._db.fetchrow(
                """
                SELECT condition_id, token_id, snapshot_at, best_bid, best_ask, spread, mid_price,
                       bids, asks, bid_depth_5pct, ask_depth_5pct
                FROM orderbook_snapshots
                WHERE condition_id = $1 AND token_id = $2
                ORDER BY snapshot_at DESC
                LIMIT 1
                """,
                condition_id,
                selected_token,
            )
        except Exception:
            record = None

        if not record:
            return {
                "condition_id": condition_id,
                "token_id": selected_token,
                "bids": [],
                "asks": [],
                "source": "unavailable",
            }

        def parse_levels(raw: Any) -> List[Dict[str, float]]:
            if not raw:
                return []
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    return []
            levels: List[Dict[str, float]] = []
            for level in raw or []:
                if isinstance(level, dict):
                    price = level.get("price")
                    size = level.get("size")
                elif isinstance(level, (list, tuple)) and len(level) >= 2:
                    price, size = level[0], level[1]
                else:
                    continue
                if price is None or size is None:
                    continue
                levels.append({
                    "price": float(price),
                    "size": float(size),
                })
            return levels

        bids = parse_levels(record.get("bids"))
        asks = parse_levels(record.get("asks"))

        best_bid = float(record["best_bid"]) if record.get("best_bid") is not None else None
        best_ask = float(record["best_ask"]) if record.get("best_ask") is not None else None
        mid_price = float(record["mid_price"]) if record.get("mid_price") is not None else None
        spread = float(record["spread"]) if record.get("spread") is not None else None

        def depth_within(levels: List[Dict[str, float]], best: Optional[float], pct: float, side: str) -> float:
            if best is None or not levels:
                return 0.0
            if side == "bid":
                threshold = best * (1 - pct)
                return sum(level["size"] for level in levels if level["price"] >= threshold)
            threshold = best * (1 + pct)
            return sum(level["size"] for level in levels if level["price"] <= threshold)

        def vwap(levels: List[Dict[str, float]], size: float) -> Optional[float]:
            if not levels or size <= 0:
                return None
            remaining = size
            total_cost = 0.0
            for level in levels:
                take = min(level["size"], remaining)
                total_cost += take * level["price"]
                remaining -= take
                if remaining <= 0:
                    break
            if remaining > 0:
                return None
            return total_cost / size

        default_size = (
            float(self._execution_service._config.default_position_size)
            if self._execution_service
            else None
        )
        sizes = [10.0, 25.0, 50.0]
        if default_size and default_size > 0:
            sizes = [max(default_size * 0.5, 1.0), default_size, default_size * 2]

        buy_slippage = []
        sell_slippage = []
        for size in sizes:
            buy_avg = vwap(asks, size)
            if buy_avg is None or best_ask in (None, 0):
                buy_slippage.append({
                    "size": size,
                    "avg_price": None,
                    "slippage_bps": None,
                })
            else:
                buy_slippage.append({
                    "size": size,
                    "avg_price": buy_avg,
                    "slippage_bps": (buy_avg - best_ask) / best_ask * 10000,
                })

            sell_avg = vwap(bids, size)
            if sell_avg is None or best_bid in (None, 0):
                sell_slippage.append({
                    "size": size,
                    "avg_price": None,
                    "slippage_bps": None,
                })
            else:
                sell_slippage.append({
                    "size": size,
                    "avg_price": sell_avg,
                    "slippage_bps": (best_bid - sell_avg) / best_bid * 10000,
                })

        return {
            "condition_id": condition_id,
            "token_id": selected_token,
            "snapshot_at": self._format_timestamp(record.get("snapshot_at")),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "bids": bids,
            "asks": asks,
            "depth": {
                "bid": {
                    "pct1": depth_within(bids, best_bid, 0.01, "bid"),
                    "pct5": float(record.get("bid_depth_5pct") or 0)
                    if record.get("bid_depth_5pct") is not None
                    else depth_within(bids, best_bid, 0.05, "bid"),
                    "pct10": depth_within(bids, best_bid, 0.10, "bid"),
                },
                "ask": {
                    "pct1": depth_within(asks, best_ask, 0.01, "ask"),
                    "pct5": float(record.get("ask_depth_5pct") or 0)
                    if record.get("ask_depth_5pct") is not None
                    else depth_within(asks, best_ask, 0.05, "ask"),
                    "pct10": depth_within(asks, best_ask, 0.10, "ask"),
                },
            },
            "slippage": {
                "buy": buy_slippage,
                "sell": sell_slippage,
            },
            "source": "snapshot",
        }

    async def _block_market(self, condition_id: str, token_id: Optional[str], reason: str) -> None:
        """Persist a market block and update engine."""
        if not self._db:
            return

        await self.ensure_control_tables()
        await self._db.execute(
            """
            INSERT INTO market_blocks (condition_id, token_id, reason, actor, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (condition_id) DO UPDATE
            SET token_id = $2, reason = $3, actor = $4, created_at = $5
            """,
            condition_id,
            token_id,
            reason,
            "dashboard",
            datetime.now(timezone.utc).isoformat(),
        )

        if self._engine:
            self._engine.block_market(condition_id, reason=reason)

        await self._record_action(
            "block_market",
            "ok",
            details={"condition_id": condition_id, "token_id": token_id, "reason": reason},
        )

    async def _unblock_market(self, condition_id: str) -> None:
        """Remove a market from the blocklist."""
        if not self._db:
            return

        await self.ensure_control_tables()
        await self._db.execute(
            "DELETE FROM market_blocks WHERE condition_id = $1",
            condition_id,
        )

        if self._engine:
            self._engine.unblock_market(condition_id)

        await self._record_action(
            "unblock_market",
            "ok",
            details={"condition_id": condition_id},
        )

    async def _get_blocklist(self) -> List[Dict[str, Any]]:
        """Return active market blocks."""
        if not self._db:
            return []

        await self.ensure_control_tables()
        records = await self._db.fetch(
            "SELECT condition_id, token_id, reason, created_at FROM market_blocks ORDER BY created_at DESC"
        )
        return [
            {
                "condition_id": r["condition_id"],
                "token_id": r.get("token_id"),
                "reason": r.get("reason"),
                "created_at": r.get("created_at"),
            }
            for r in records
        ]

    def broadcast_event(self, event: Dict[str, Any]) -> None:
        """Broadcast event to all SSE subscribers."""
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        with self._sse_lock:
            for q in self._sse_queues:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass  # Skip if queue is full


def create_app(
    db: Optional["Database"] = None,
    health_checker: Optional[Any] = None,
    metrics_collector: Optional[Any] = None,
    engine: Optional[Any] = None,
    execution_service: Optional[Any] = None,
    bot_config: Optional[Any] = None,
    shutdown_callback: Optional[Callable[[str], Any]] = None,
    started_at: Optional[datetime] = None,
    testing: bool = False,
) -> "Flask":
    """
    Factory function to create the dashboard app.

    Args:
        db: Database connection
        health_checker: HealthChecker instance
        metrics_collector: MetricsCollector instance
        testing: Enable testing mode

    Returns:
        Flask application
    """
    dashboard = Dashboard(
        db=db,
        health_checker=health_checker,
        metrics_collector=metrics_collector,
        engine=engine,
        execution_service=execution_service,
        bot_config=bot_config,
        shutdown_callback=shutdown_callback,
        started_at=started_at,
    )
    return dashboard.create_app(testing=testing)
