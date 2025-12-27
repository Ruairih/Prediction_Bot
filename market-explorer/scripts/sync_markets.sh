#!/bin/bash
# Sync markets from Polymarket Gamma API
#
# Usage:
#   ./scripts/sync_markets.sh           # Quick active-only sync
#   ./scripts/sync_markets.sh --full    # Full sync including resolved markets
#
# For recurring sync, add to crontab:
#   */10 * * * * cd /workspace/market-explorer && ./scripts/sync_markets.sh >> /tmp/market_sync.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"

# Database URL - adjust if running outside Docker
export EXPLORER_DATABASE_URL="${EXPLORER_DATABASE_URL:-postgresql://predict:predict@postgres:5432/predict}"

cd "$BACKEND_DIR"

if [ "$1" = "--full" ]; then
    echo "[$(date)] Starting full market sync..."
    python3 sync_markets_v2.py
else
    echo "[$(date)] Starting active-only market sync..."
    python3 sync_markets_v2.py --active-only
fi

echo "[$(date)] Sync complete"
