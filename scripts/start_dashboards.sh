#!/bin/bash
# Start all dashboards inside the container
# Run this after: docker compose up -d

set -e

echo "=== Starting Polymarket Dashboards ==="
echo ""

# Check if we're inside the container
if [ ! -f /.dockerenv ]; then
    echo "This script should be run INSIDE the container."
    echo "Use: docker compose exec dev ./scripts/start_dashboards.sh"
    exit 1
fi

cd /workspace

# Activate virtual environment if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "[1/3] Starting trading bot (includes Flask dashboard on :9050)..."
DATABASE_URL=postgresql://predict:predict@postgres:5432/predict \
    nohup python -m polymarket_bot.main > /tmp/bot.log 2>&1 &
sleep 3

echo "[2/3] Starting React dashboard on :3000..."
cd /workspace/dashboard
nohup npm run dev > /tmp/react-dashboard.log 2>&1 &
cd /workspace
sleep 2

echo "[3/3] Starting Ingestion dashboard on :8081..."
nohup python scripts/run_ingestion.py > /tmp/ingestion.log 2>&1 &
sleep 2

echo ""
echo "=== All dashboards started ==="
echo ""
echo "Logs:"
echo "  - Bot:        tail -f /tmp/bot.log"
echo "  - React:      tail -f /tmp/react-dashboard.log"
echo "  - Ingestion:  tail -f /tmp/ingestion.log"
echo ""
echo "Access (via Tailscale):"
echo "  - Flask:      http://<tailscale-ip>:9050/"
echo "  - React:      http://<tailscale-ip>:3000/"
echo "  - Ingestion:  http://<tailscale-ip>:8081/"
echo ""
echo "Health checks:"
curl -s http://localhost:9050/health | head -c 50 && echo "... (Flask OK)"
curl -s http://localhost:3000/ > /dev/null && echo "React OK"
curl -s http://localhost:8081/health | head -c 50 && echo "... (Ingestion OK)"
