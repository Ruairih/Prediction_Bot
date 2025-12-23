#!/bin/bash
# =============================================================================
# Setup Test Database
# =============================================================================
# This script initializes the PostgreSQL database with the full schema.
# Applies all seed/*.sql files in order.
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
SEED_DIR="${SEED_DIR:-seed}"

echo "=================================="
echo "Setting up database"
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
    if [ $i -eq 30 ]; then
        echo "ERROR: PostgreSQL not ready after 30 attempts"
        exit 1
    fi
    echo "  Attempt $i/30..."
    sleep 1
done

# Apply all seed files in order
echo ""
echo "Applying migrations from $SEED_DIR/..."

# Get sorted list of .sql files
SQL_FILES=$(find "$SEED_DIR" -name "*.sql" -type f | sort)

if [ -z "$SQL_FILES" ]; then
    echo "WARNING: No SQL files found in $SEED_DIR/"
else
    for sql_file in $SQL_FILES; do
        echo "  Applying: $sql_file"
        # Use ON_ERROR_STOP=1 to fail fast on real errors
        # Capture output and check exit code separately
        OUTPUT=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
            -v ON_ERROR_STOP=1 -f "$sql_file" 2>&1)
        RESULT=$?
        if [ $RESULT -eq 0 ]; then
            echo "    OK"
        else
            echo "    ERROR: Migration failed!"
            echo "$OUTPUT" | grep -i "error" || echo "$OUTPUT"
            exit 1
        fi
    done
fi

# Verify key tables exist
echo ""
echo "Verifying schema..."
TABLES_TO_CHECK="positions orders triggers market_universe polymarket_first_triggers"
MISSING_TABLES=""

for table in $TABLES_TO_CHECK; do
    EXISTS=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -t -c \
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null | tr -d ' ')
    if [ "$EXISTS" = "t" ]; then
        echo "  $table: OK"
    else
        echo "  $table: MISSING"
        MISSING_TABLES="$MISSING_TABLES $table"
    fi
done

if [ -n "$MISSING_TABLES" ]; then
    echo ""
    echo "WARNING: Some tables are missing:$MISSING_TABLES"
    echo "The bot may not function correctly."
fi

echo ""
echo "=================================="
echo "Database setup complete!"
echo "=================================="
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "Run tests with:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME pytest"
echo ""
