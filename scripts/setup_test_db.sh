#!/bin/bash
# =============================================================================
# Setup Test Database
# =============================================================================
# This script initializes the PostgreSQL test database with the schema.
#
# Usage:
#   ./scripts/setup_test_db.sh
#
# Prerequisites:
#   - PostgreSQL running (via docker-compose or locally)
#   - psql client installed
# =============================================================================

set -e

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5433}"
DB_USER="${DB_USER:-predict}"
DB_PASSWORD="${DB_PASSWORD:-predict}"
DB_NAME="${DB_NAME:-predict}"

echo "=================================="
echo "Setting up test database"
echo "=================================="
echo "Host: $DB_HOST:$DB_PORT"
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
for i in {1..30}; do
    if PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT 1" > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo "  Attempt $i/30..."
    sleep 1
done

# Apply schema
echo ""
echo "Applying schema from seed/01_schema.sql..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f seed/01_schema.sql

echo ""
echo "=================================="
echo "Test database setup complete!"
echo "=================================="
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "Run tests with:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME pytest"
