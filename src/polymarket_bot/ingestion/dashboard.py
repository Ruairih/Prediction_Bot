"""
FastAPI dashboard for ingestion service monitoring.

Provides:
    - HTML dashboard with live metrics
    - REST API endpoints for status and metrics
    - WebSocket endpoint for real-time event streaming
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from .service import IngestionService

logger = logging.getLogger(__name__)

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_dashboard_app(service: "IngestionService") -> FastAPI:
    """
    Create the FastAPI dashboard application.

    Args:
        service: The ingestion service to monitor

    Returns:
        FastAPI application instance
    """
    app = FastAPI(
        title="Polymarket Ingestion Monitor",
        description="Real-time monitoring dashboard for Polymarket data ingestion",
        version="1.0.0",
    )

    # WebSocket connections for live updates
    active_websockets: list[WebSocket] = []

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve the main dashboard HTML page."""
        template_path = TEMPLATES_DIR / "index.html"
        if template_path.exists():
            return HTMLResponse(content=template_path.read_text())

        # Fallback inline template if file doesn't exist
        return HTMLResponse(content=get_inline_dashboard_html())

    @app.get("/api/status")
    async def get_status():
        """Get current service health status."""
        health = service.health()
        return health.to_dict()

    @app.get("/api/metrics")
    async def get_metrics():
        """Get current ingestion metrics."""
        metrics = service.metrics
        if metrics:
            return metrics.to_dict()
        return {"error": "Metrics not available"}

    @app.get("/api/events")
    async def get_events(limit: int = 50, offset: int = 0):
        """
        Get recent processed events.

        Args:
            limit: Maximum number of events to return
            offset: Number of events to skip
        """
        if service.processor:
            events = service.processor.get_recent_events(limit=limit, offset=offset)
            return {
                "events": [
                    {
                        "event_type": e.event_type,
                        "token_id": e.token_id,
                        "timestamp": e.timestamp.isoformat(),
                        "accepted": e.accepted,
                        "price": str(e.price) if e.price else None,
                        "size": str(e.size) if e.size else None,
                        "g1_filtered": e.g1_filtered,
                        "g3_backfilled": e.g3_backfilled,
                        "g5_flagged": e.g5_flagged,
                        "reason": e.reason,
                        "question": e.question,
                    }
                    for e in events
                ],
                "total": len(service.processor.recent_events),
                "limit": limit,
                "offset": offset,
            }
        return {"events": [], "total": 0}

    @app.get("/api/stats")
    async def get_stats():
        """Get processing statistics."""
        if service.processor:
            stats = service.processor.stats
            return {
                "total_processed": stats.total_processed,
                "total_accepted": stats.total_accepted,
                "total_rejected": stats.total_rejected,
                "g1_filtered": stats.g1_filtered,
                "g3_backfilled": stats.g3_backfilled,
                "g3_failed": stats.g3_failed,
                "g5_flagged": stats.g5_flagged,
            }
        return {}

    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        """
        WebSocket endpoint for live event streaming.

        Sends metrics updates every second.
        """
        await websocket.accept()
        active_websockets.append(websocket)
        logger.info(f"Dashboard WebSocket connected (total: {len(active_websockets)})")

        try:
            while True:
                # Send metrics update
                metrics = service.metrics
                health = service.health()

                data = {
                    "type": "update",
                    "health": health.to_dict(),
                    "metrics": metrics.to_dict() if metrics else {},
                }

                await websocket.send_json(data)

                # Wait before next update
                await asyncio.sleep(1)

        except WebSocketDisconnect:
            logger.info("Dashboard WebSocket disconnected")
        except Exception as e:
            logger.error(f"Dashboard WebSocket error: {e}")
        finally:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    @app.get("/health")
    async def health_check():
        """
        Health check endpoint for Docker/Kubernetes.

        Returns 200 if healthy, 503 if unhealthy.
        """
        health = service.health()
        if health.healthy:
            return {"status": "healthy"}
        return {"status": "unhealthy", "details": health.details}

    return app


def get_inline_dashboard_html() -> str:
    """Return inline HTML dashboard as fallback."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket Ingestion Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
            line-height: 1.5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #30363d;
        }
        h1 {
            font-size: 20px;
            font-weight: 600;
            color: #f0f6fc;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-healthy {
            background: #238636;
            color: #fff;
        }
        .status-unhealthy {
            background: #da3633;
            color: #fff;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 16px;
        }
        .card-title {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: #8b949e;
            margin-bottom: 12px;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #21262d;
        }
        .metric-row:last-child {
            border-bottom: none;
        }
        .metric-label {
            color: #8b949e;
        }
        .metric-value {
            font-weight: 600;
            color: #f0f6fc;
        }
        .metric-value.success {
            color: #3fb950;
        }
        .metric-value.warning {
            color: #d29922;
        }
        .metric-value.error {
            color: #f85149;
        }
        .events-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        .events-table th {
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid #30363d;
            color: #8b949e;
            font-weight: 600;
        }
        .events-table td {
            padding: 8px;
            border-bottom: 1px solid #21262d;
        }
        .events-table tr:hover {
            background: #1f2428;
        }
        .tag {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
        }
        .tag-g1 { background: #f85149; color: #fff; }
        .tag-g3 { background: #d29922; color: #fff; }
        .tag-g5 { background: #a371f7; color: #fff; }
        .tag-ok { background: #238636; color: #fff; }
        .uptime {
            font-size: 14px;
            color: #8b949e;
        }
        #connection-status {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .ws-connected { background: #3fb950; }
        .ws-disconnected { background: #f85149; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1><span id="connection-status" class="ws-disconnected"></span>POLYMARKET INGESTION</h1>
                <span class="uptime" id="uptime">Starting...</span>
            </div>
            <span class="status-badge status-unhealthy" id="health-badge">LOADING</span>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-title">Connection</div>
                <div class="metric-row">
                    <span class="metric-label">WebSocket</span>
                    <span class="metric-value" id="ws-state">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Last Message</span>
                    <span class="metric-value" id="last-msg">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Reconnections</span>
                    <span class="metric-value" id="reconnects">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Markets</span>
                    <span class="metric-value" id="markets">-</span>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Data Flow (5 min)</div>
                <div class="metric-row">
                    <span class="metric-label">Events</span>
                    <span class="metric-value" id="events">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Rate</span>
                    <span class="metric-value" id="rate">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Trades Stored</span>
                    <span class="metric-value" id="trades">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Price Updates</span>
                    <span class="metric-value" id="updates">-</span>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Data Quality</div>
                <div class="metric-row">
                    <span class="metric-label">Avg Trade Age</span>
                    <span class="metric-value" id="avg-age">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Freshness</span>
                    <span class="metric-value" id="freshness">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Errors (1h)</span>
                    <span class="metric-value" id="errors">-</span>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Gotcha Protection</div>
                <div class="metric-row">
                    <span class="metric-label">G1 Stale</span>
                    <span class="metric-value" id="g1">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">G3 No-size</span>
                    <span class="metric-value" id="g3-missing">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">G3 Backfilled</span>
                    <span class="metric-value" id="g3-backfill">-</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">G5 Diverge</span>
                    <span class="metric-value" id="g5">-</span>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Recent Events</div>
            <table class="events-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th style="max-width: 400px;">Market</th>
                        <th>Price</th>
                        <th>Size</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody id="events-body">
                    <tr><td colspan="5" style="text-align: center; color: #8b949e;">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let ws = null;
        let reconnectAttempts = 0;

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws/live`);

            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('connection-status').className = 'ws-connected';
                reconnectAttempts = 0;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('connection-status').className = 'ws-disconnected';
                // Reconnect with backoff
                reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                setTimeout(connectWebSocket, delay);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        function updateDashboard(data) {
            const health = data.health || {};
            const metrics = data.metrics || {};
            const ws = health.websocket || {};

            // Health badge
            const badge = document.getElementById('health-badge');
            if (health.healthy) {
                badge.textContent = 'HEALTHY';
                badge.className = 'status-badge status-healthy';
            } else {
                badge.textContent = 'UNHEALTHY';
                badge.className = 'status-badge status-unhealthy';
            }

            // Uptime
            const uptime = health.uptime_seconds || 0;
            const hours = Math.floor(uptime / 3600);
            const mins = Math.floor((uptime % 3600) / 60);
            document.getElementById('uptime').textContent = `Running ${hours}h ${mins}m`;

            // Connection
            document.getElementById('ws-state').textContent = ws.state || '-';
            document.getElementById('ws-state').className = 'metric-value ' + (ws.connected ? 'success' : 'error');

            const lastMsg = ws.last_message_age_seconds;
            document.getElementById('last-msg').textContent = lastMsg !== null ? `${lastMsg.toFixed(1)}s ago` : '-';
            document.getElementById('last-msg').className = 'metric-value ' + (lastMsg < 30 ? 'success' : lastMsg < 60 ? 'warning' : 'error');

            document.getElementById('reconnects').textContent = metrics.reconnection_count || 0;
            document.getElementById('markets').textContent = ws.subscribed_markets || 0;

            // Data flow
            document.getElementById('events').textContent = metrics.events_received || 0;
            document.getElementById('rate').textContent = `${(metrics.events_per_second || 0).toFixed(1)}/sec`;
            document.getElementById('trades').textContent = metrics.trades_stored || 0;
            document.getElementById('updates').textContent = metrics.price_updates_received || 0;

            // Data quality
            document.getElementById('avg-age').textContent = `${(metrics.average_trade_age_seconds || 0).toFixed(1)}s`;
            document.getElementById('freshness').textContent = `${(metrics.freshness_percentage || 100).toFixed(1)}%`;
            document.getElementById('errors').textContent = metrics.errors_last_hour || 0;
            document.getElementById('errors').className = 'metric-value ' + (metrics.errors_last_hour === 0 ? 'success' : 'error');

            // Gotcha protection
            document.getElementById('g1').textContent = metrics.g1_stale_filtered || 0;
            document.getElementById('g1').className = 'metric-value ' + (metrics.g1_stale_filtered > 0 ? 'warning' : 'success');
            document.getElementById('g3-missing').textContent = metrics.g3_missing_size || 0;
            document.getElementById('g3-backfill').textContent = metrics.g3_size_backfilled || 0;
            document.getElementById('g5').textContent = metrics.g5_divergence_detected || 0;
            document.getElementById('g5').className = 'metric-value ' + (metrics.g5_divergence_detected > 0 ? 'error' : 'success');
        }

        // Fetch recent events periodically
        async function fetchEvents() {
            try {
                const response = await fetch('/api/events?limit=20');
                const data = await response.json();

                const tbody = document.getElementById('events-body');
                if (data.events && data.events.length > 0) {
                    tbody.innerHTML = data.events.map(e => {
                        const time = new Date(e.timestamp).toLocaleTimeString();
                        // Show market question if available, otherwise truncated token ID
                        const market = e.question
                            ? (e.question.length > 60 ? e.question.substring(0, 60) + '...' : e.question)
                            : e.token_id.substring(0, 10) + '...';
                        const price = e.price || '-';
                        const size = e.size || '-';

                        let status = '<span class="tag tag-ok">OK</span>';
                        if (e.g1_filtered) status = '<span class="tag tag-g1">G1</span>';
                        else if (e.g5_flagged) status = '<span class="tag tag-g5">G5</span>';
                        else if (e.g3_backfilled) status = '<span class="tag tag-g3">G3</span>';

                        return `<tr>
                            <td>${time}</td>
                            <td title="${e.question || e.token_id}" style="max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${market}</td>
                            <td>${price}</td>
                            <td>${size}</td>
                            <td>${status}</td>
                        </tr>`;
                    }).join('');
                } else {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #8b949e;">No events yet</td></tr>';
                }
            } catch (error) {
                console.error('Failed to fetch events:', error);
            }
        }

        // Initialize
        connectWebSocket();
        fetchEvents();
        setInterval(fetchEvents, 5000);
    </script>
</body>
</html>'''


async def run_dashboard(
    service: "IngestionService",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    """
    Run the dashboard as a standalone server.

    Args:
        service: The ingestion service to monitor
        host: Host to bind to
        port: Port to listen on
    """
    import uvicorn

    app = create_dashboard_app(service)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
