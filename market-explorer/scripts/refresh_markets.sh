#!/bin/bash
# Refresh market data with fixed sync script
# This should be run after deploying the fixes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")/backend"

# Check if running inside Docker or locally
if [ -f /.dockerenv ]; then
    DB_URL="${EXPLORER_DATABASE_URL:-postgresql://predict:predict@postgres:5432/predict}"
else
    DB_URL="${EXPLORER_DATABASE_URL:-postgresql://predict:predict@localhost:5433/predict}"
fi

echo "=== Market Explorer Data Refresh ==="
echo "Database: ${DB_URL%%@*}@***"
echo ""

cd "$BACKEND_DIR"

# Run the sync script
echo "Step 1: Running market sync (active markets only)..."
EXPLORER_DATABASE_URL="$DB_URL" python sync_markets_v2.py --active-only

echo ""
echo "Step 2: Running cleanup migration..."
# Apply the stale data cleanup migration
psql "$DB_URL" < "$SCRIPT_DIR/../shared/migrations/004_cleanup_stale_markets.sql" 2>/dev/null || echo "Migration may already be applied or DB unavailable"

echo ""
echo "=== Refresh Complete ==="
echo "The dashboard should now show correct liquidity data for active markets."
