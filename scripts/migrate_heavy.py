#!/usr/bin/env python3
"""
Standalone SQLite to PostgreSQL Migration Script

Run this OUTSIDE of Claude Code to avoid memory/timeout issues:

    docker exec -it polymarket_bot python3 /workspace/scripts/migrate_heavy.py

Or from host with direct DB access:

    SQLITE_SOURCE=/path/to/guardrail.sqlite \
    DATABASE_URL=postgresql://predict:predict@localhost:5432/predict \
    python3 scripts/migrate_heavy.py
"""

import os
import sys
import sqlite3
import psycopg2
from datetime import datetime, timedelta

# Configuration
SQLITE_PATH = os.environ.get('SQLITE_SOURCE', '/data/guardrail.sqlite')
PG_URL = os.environ.get('DATABASE_URL', 'postgresql://predict:predict@postgres:5432/predict')
BATCH_SIZE = 1000  # Process rows in batches to avoid memory issues

# Time filter: only migrate last 60 days
TWO_MONTHS_AGO = datetime.now() - timedelta(days=60)
TWO_MONTHS_TS = int(TWO_MONTHS_AGO.timestamp())
TWO_MONTHS_ISO = TWO_MONTHS_AGO.strftime('%Y-%m-%d')

# Table definitions: (date_column, date_type)
# date_type: 'int' for unix timestamp, 'text' for ISO date, None for no filter
TABLES = {
    'polymarket_trades': ('timestamp', 'int'),
    'polymarket_first_triggers': ('trigger_timestamp', 'int'),
    'polymarket_candidates': ('trigger_timestamp', 'int'),
    'paper_trades': ('created_at', 'text'),
    'live_orders': ('submitted_at', 'text'),
    'positions': ('created_at', 'text'),
    'daily_pnl': ('date', 'text'),
    'exit_events': ('created_at', 'text'),
    'score_history': ('scored_at', 'int'),
    'trade_watchlist': ('created_at', 'int'),
    'polymarket_resolutions': (None, None),
    'polymarket_token_meta': (None, None),
    'market_scores_cache': (None, None),
    'stream_watchlist': (None, None),
}


def get_row_count(sqlite_conn, table, date_col, date_type):
    """Get count of rows to migrate for progress reporting."""
    if date_col is None:
        query = f"SELECT COUNT(*) FROM {table}"
    elif date_type == 'int':
        query = f"SELECT COUNT(*) FROM {table} WHERE {date_col} >= {TWO_MONTHS_TS}"
    else:
        query = f"SELECT COUNT(*) FROM {table} WHERE {date_col} >= '{TWO_MONTHS_ISO}'"

    try:
        return sqlite_conn.execute(query).fetchone()[0]
    except sqlite3.OperationalError:
        return -1  # Table doesn't exist


def migrate_table(sqlite_conn, pg_conn, table, date_col, date_type):
    """Migrate a single table with batched inserts."""
    pg_cur = pg_conn.cursor()

    # Build query with date filter
    if date_col is None:
        query = f"SELECT * FROM {table}"
    elif date_type == 'int':
        query = f"SELECT * FROM {table} WHERE {date_col} >= {TWO_MONTHS_TS}"
    else:
        query = f"SELECT * FROM {table} WHERE {date_col} >= '{TWO_MONTHS_ISO}'"

    try:
        cursor = sqlite_conn.execute(query)
    except sqlite3.OperationalError as e:
        print(f"  SKIP: {e}")
        return 0

    # Get column names from first row
    first_row = cursor.fetchone()
    if first_row is None:
        print(f"  No rows to migrate")
        return 0

    cols = first_row.keys()
    col_names = ', '.join(cols)
    placeholders = ', '.join(['%s'] * len(cols))

    # Clear existing data in postgres
    pg_cur.execute(f"DELETE FROM {table}")
    pg_conn.commit()

    # Insert first row
    total_migrated = 0
    batch = [tuple(first_row[col] for col in cols)]
    errors = 0

    # Process remaining rows in batches
    while True:
        rows = cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break

        for row in rows:
            batch.append(tuple(row[col] for col in cols))

        # Insert batch
        for values in batch:
            try:
                pg_cur.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    values
                )
                total_migrated += 1
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  Error: {e}")

        pg_conn.commit()
        batch = []

        # Progress indicator
        sys.stdout.write(f"\r  Migrated {total_migrated} rows...")
        sys.stdout.flush()

    # Final batch
    for values in batch:
        try:
            pg_cur.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                values
            )
            total_migrated += 1
        except Exception as e:
            errors += 1

    pg_conn.commit()
    print(f"\r  Migrated {total_migrated} rows ({errors} errors)")
    return total_migrated


def main():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {PG_URL.split('@')[1] if '@' in PG_URL else PG_URL}")
    print(f"Date filter: >= {TWO_MONTHS_ISO}")
    print(f"Batch size: {BATCH_SIZE}")
    print("=" * 60)

    # Connect to SQLite (immutable mode for read-only mounted files)
    print("\nConnecting to SQLite...")
    try:
        sqlite_conn = sqlite3.connect(f'file:{SQLITE_PATH}?immutable=1', uri=True)
        sqlite_conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"ERROR connecting to SQLite: {e}")
        sys.exit(1)

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(PG_URL)
    except Exception as e:
        print(f"ERROR connecting to PostgreSQL: {e}")
        sys.exit(1)

    # Pre-scan tables
    print("\nScanning tables...")
    table_counts = {}
    for table, (date_col, date_type) in TABLES.items():
        count = get_row_count(sqlite_conn, table, date_col, date_type)
        if count >= 0:
            table_counts[table] = count
            print(f"  {table}: {count:,} rows")
        else:
            print(f"  {table}: (not found)")

    total_rows = sum(table_counts.values())
    print(f"\nTotal rows to migrate: {total_rows:,}")

    # Migrate each table
    print("\n" + "=" * 60)
    print("Starting migration...")
    print("=" * 60)

    grand_total = 0
    for table, (date_col, date_type) in TABLES.items():
        if table not in table_counts:
            continue
        print(f"\n[{table}]")
        count = migrate_table(sqlite_conn, pg_conn, table, date_col, date_type)
        grand_total += count

    # Cleanup
    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "=" * 60)
    print(f"Migration complete! Total: {grand_total:,} rows")
    print("=" * 60)


if __name__ == '__main__':
    main()
