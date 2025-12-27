#!/bin/bash
# Full startup script - run on HOST after reboot
# Starts Docker containers and all dashboards

set -e

cd "$(dirname "$0")/.."

echo "=== Polymarket Bot Startup ==="
echo ""

echo "[1/3] Starting Docker containers..."
docker compose up -d
sleep 5

echo ""
echo "[2/3] Starting dashboards inside container..."
docker compose exec -d dev bash -c "./scripts/start_dashboards.sh"

# Also start Market Explorer
echo "[2b/3] Starting Market Explorer..."
docker compose exec -d dev bash -c "cd /workspace/market-explorer/backend && uvicorn src.explorer.api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/market-explorer-api.log 2>&1 &"
docker compose exec -d dev bash -c "cd /workspace/market-explorer/frontend && npm run dev > /tmp/market-explorer-frontend.log 2>&1 &"

echo ""
echo "[3/3] Configuring Tailscale serves..."
# These are idempotent - safe to run multiple times
sudo tailscale serve --bg --tcp 9050 tcp://localhost:9050 2>/dev/null || true
sudo tailscale serve --bg --tcp 3000 tcp://localhost:3000 2>/dev/null || true
sudo tailscale serve --bg --tcp 3004 tcp://localhost:3004 2>/dev/null || true
sudo tailscale serve --bg --tcp 8000 tcp://localhost:8000 2>/dev/null || true

echo ""
echo "=== Startup complete ==="
echo ""
echo "Tailscale serves configured:"
tailscale serve status 2>/dev/null || echo "  (run 'tailscale serve status' to verify)"
echo ""
echo "Services available:"
echo "  - :9050 -> Flask trading dashboard"
echo "  - :3000 -> React trading dashboard"
echo "  - :3004 -> Market Explorer frontend"
echo "  - :8000 -> Market Explorer API"
echo ""
echo "View logs:"
echo "  docker compose exec dev tail -f /tmp/bot.log"
echo "  docker compose exec dev tail -f /tmp/react-dashboard.log"
echo "  docker compose exec dev tail -f /tmp/market-explorer-api.log"
