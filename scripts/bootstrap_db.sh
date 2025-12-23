#!/bin/bash
# =============================================================================
# Bootstrap Database
# =============================================================================
# Comprehensive database initialization script for the Polymarket Trading Bot.
#
# This script:
# 1. Creates the database if it doesn't exist
# 2. Applies all migrations in order
# 3. Verifies schema integrity
# 4. Reports any issues
#
# Usage:
#   ./scripts/bootstrap_db.sh              # Use defaults
#   ./scripts/bootstrap_db.sh --create-db  # Also create database if missing
#   ./scripts/bootstrap_db.sh --check      # Just verify, don't modify
#
# Environment variables:
#   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# =============================================================================

set -e

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5433}"
DB_USER="${DB_USER:-predict}"
DB_PASSWORD="${DB_PASSWORD:-predict}"
DB_NAME="${DB_NAME:-predict}"
SEED_DIR="${SEED_DIR:-seed}"
CREATE_DB=false
CHECK_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --create-db)
            CREATE_DB=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--create-db] [--check]"
            echo ""
            echo "Options:"
            echo "  --create-db  Create database if it doesn't exist"
            echo "  --check      Only verify schema, don't modify"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "Polymarket Trading Bot - Database Bootstrap"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  Host:     $DB_HOST:$DB_PORT"
echo "  Database: $DB_NAME"
echo "  User:     $DB_USER"
echo "  Mode:     $([ "$CHECK_ONLY" = true ] && echo "CHECK ONLY" || echo "APPLY")"
echo ""

# Function to run psql (with ON_ERROR_STOP for fail-fast behavior)
psql_cmd() {
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -v ON_ERROR_STOP=1 "$@"
}

# Function to check if postgres is ready
wait_for_postgres() {
    echo "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if psql_cmd -d postgres -c "SELECT 1" > /dev/null 2>&1; then
            echo -e "${GREEN}PostgreSQL is ready!${NC}"
            return 0
        fi
        echo "  Attempt $i/30..."
        sleep 1
    done
    echo -e "${RED}ERROR: PostgreSQL not ready after 30 attempts${NC}"
    exit 1
}

# Function to check if database exists
db_exists() {
    psql_cmd -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" 2>/dev/null | grep -q 1
}

# Function to create database
create_database() {
    echo "Creating database '$DB_NAME'..."
    psql_cmd -d postgres -c "CREATE DATABASE $DB_NAME" 2>/dev/null || true
    echo -e "${GREEN}Database created or already exists${NC}"
}

# Wait for PostgreSQL
wait_for_postgres

# Create database if requested and doesn't exist
if [ "$CREATE_DB" = true ]; then
    if ! db_exists; then
        create_database
    else
        echo "Database '$DB_NAME' already exists"
    fi
fi

# Verify database exists
if ! db_exists; then
    echo -e "${RED}ERROR: Database '$DB_NAME' does not exist${NC}"
    echo "Run with --create-db to create it"
    exit 1
fi

# Apply migrations (unless check-only mode)
if [ "$CHECK_ONLY" = false ]; then
    echo ""
    echo "Applying migrations from $SEED_DIR/..."
    echo ""

    # Get sorted list of .sql files
    SQL_FILES=$(find "$SEED_DIR" -name "*.sql" -type f 2>/dev/null | sort)

    if [ -z "$SQL_FILES" ]; then
        echo -e "${YELLOW}WARNING: No SQL files found in $SEED_DIR/${NC}"
    else
        for sql_file in $SQL_FILES; do
            filename=$(basename "$sql_file")
            echo -n "  $filename: "

            # Capture output and exit code
            OUTPUT=$(psql_cmd -d $DB_NAME -f "$sql_file" 2>&1)
            RESULT=$?

            if [ $RESULT -eq 0 ]; then
                # Check for ERRORs in output (psql sometimes returns 0 even with errors)
                if echo "$OUTPUT" | grep -q "ERROR:"; then
                    echo -e "${YELLOW}PARTIAL (some errors)${NC}"
                else
                    echo -e "${GREEN}OK${NC}"
                fi
            else
                echo -e "${YELLOW}WARNING${NC}"
            fi
        done
    fi
fi

# Verify schema
echo ""
echo "Verifying schema..."
echo ""

# Define required tables and their expected columns
declare -A REQUIRED_TABLES
REQUIRED_TABLES["positions"]="token_id,status,entry_price"
REQUIRED_TABLES["orders"]="order_id,token_id,status"
REQUIRED_TABLES["triggers"]="token_id,condition_id,threshold"
REQUIRED_TABLES["polymarket_first_triggers"]="token_id,condition_id,threshold"
REQUIRED_TABLES["market_universe"]="condition_id,question,tier"
REQUIRED_TABLES["polymarket_trades"]="condition_id,trade_id,price"
REQUIRED_TABLES["price_candles"]="condition_id,resolution,bucket_start"

ALL_OK=true

for table in "${!REQUIRED_TABLES[@]}"; do
    echo -n "  $table: "

    # Check if table exists
    EXISTS=$(psql_cmd -d $DB_NAME -t -c \
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null | tr -d ' ')

    if [ "$EXISTS" = "t" ]; then
        # Check required columns
        IFS=',' read -ra COLUMNS <<< "${REQUIRED_TABLES[$table]}"
        MISSING_COLS=""

        for col in "${COLUMNS[@]}"; do
            COL_EXISTS=$(psql_cmd -d $DB_NAME -t -c \
                "SELECT EXISTS (SELECT FROM information_schema.columns
                 WHERE table_name = '$table' AND column_name = '$col');" 2>/dev/null | tr -d ' ')
            if [ "$COL_EXISTS" != "t" ]; then
                MISSING_COLS="$MISSING_COLS $col"
            fi
        done

        if [ -z "$MISSING_COLS" ]; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${YELLOW}MISSING COLUMNS:${MISSING_COLS}${NC}"
            ALL_OK=false
        fi
    else
        echo -e "${RED}MISSING${NC}"
        ALL_OK=false
    fi
done

# Check primary key constraints
echo ""
echo "Checking primary key constraints..."
echo ""

# Check triggers table PK includes condition_id
TRIGGERS_PK=$(psql_cmd -d $DB_NAME -t -c "
    SELECT string_agg(a.attname, ',')
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    WHERE i.indrelid = 'polymarket_first_triggers'::regclass AND i.indisprimary;
" 2>/dev/null | tr -d ' ')

echo -n "  polymarket_first_triggers PK: "
if echo "$TRIGGERS_PK" | grep -q "condition_id"; then
    echo -e "${GREEN}OK ($TRIGGERS_PK)${NC}"
else
    echo -e "${YELLOW}NEEDS MIGRATION - current: ($TRIGGERS_PK)${NC}"
    if [ "$CHECK_ONLY" = false ]; then
        echo "    Run seed/02_add_condition_id_to_triggers_pk.sql to fix"
    fi
    ALL_OK=false
fi

# Summary
echo ""
echo "=============================================="
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}Database bootstrap complete!${NC}"
else
    echo -e "${YELLOW}Database bootstrap complete with warnings${NC}"
    echo "Some tables or columns may be missing."
    echo "The bot may not function correctly."
fi
echo "=============================================="
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:***@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
