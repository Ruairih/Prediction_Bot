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
import os
import queue
import threading
from datetime import datetime, timezone
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
                result = dashboard._run_async(dashboard._get_positions())
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

    async def _get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions from database."""
        if not self._db:
            return []

        # Use correct column names: id (not position_id), entry_timestamp (not entry_time)
        query = """
            SELECT id, token_id, condition_id, size, entry_price,
                   entry_cost, entry_timestamp, realized_pnl, status
            FROM positions
            WHERE status = 'open'
            ORDER BY entry_timestamp DESC
        """
        records = await self._db.fetch(query)

        return [
            {
                "position_id": str(r["id"]),  # Map id to position_id for API compatibility
                "token_id": r["token_id"],
                "condition_id": r["condition_id"],
                "size": float(r["size"]),
                "entry_price": float(r["entry_price"]),
                "entry_cost": float(r["entry_cost"]),
                "entry_time": r["entry_timestamp"],  # Map entry_timestamp to entry_time for API
                "realized_pnl": float(r.get("realized_pnl", 0) or 0),
                "status": r["status"],
            }
            for r in records
        ]

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

    def broadcast_event(self, event: Dict[str, Any]) -> None:
        """Broadcast event to all SSE subscribers."""
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
    )
    return dashboard.create_app(testing=testing)
