#!/usr/bin/env python3
"""Migrate last 2 months of data from SQLite to Postgres."""

import os
import sqlite3
import psycopg2
from datetime import datetime, timedelta

SQLITE_PATH = os.environ.get('SQLITE_SOURCE', '/data/guardrail.sqlite')
PG_URL = os.environ.get('DATABASE_URL', 'postgresql://predict:predict@postgres:5432/predict')

TWO_MONTHS_AGO = datetime.now() - timedelta(days=60)
TWO_MONTHS_TS = int(TWO_MONTHS_AGO.timestamp())
TWO_MONTHS_ISO = TWO_MONTHS_AGO.strftime('%Y-%m-%d')

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

def migrate():
    print(f"Connecting to SQLite: {SQLITE_PATH}")
    # Use immutable mode for read-only mounted file (avoids journal creation)
    sqlite_conn = sqlite3.connect(f'file:{SQLITE_PATH}?immutable=1', uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    
    print(f"Connecting to Postgres...")
    pg_conn = psycopg2.connect(PG_URL)
    pg_cur = pg_conn.cursor()
    
    for table, (date_col, date_type) in TABLES.items():
        print(f"\nMigrating {table}...")
        
        if date_col is None:
            query = f"SELECT * FROM {table}"
        elif date_type == 'int':
            query = f"SELECT * FROM {table} WHERE {date_col} >= {TWO_MONTHS_TS}"
        else:
            query = f"SELECT * FROM {table} WHERE {date_col} >= '{TWO_MONTHS_ISO}'"
        
        try:
            rows = sqlite_conn.execute(query).fetchall()
        except sqlite3.OperationalError as e:
            print(f"  Skipping {table}: {e}")
            continue
            
        if not rows:
            print(f"  No rows found")
            continue
        
        cols = rows[0].keys()
        col_names = ', '.join(cols)
        placeholders = ', '.join(['%s'] * len(cols))
        
        pg_cur.execute(f"DELETE FROM {table}")
        
        for row in rows:
            values = tuple(row[col] for col in cols)
            try:
                pg_cur.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    values
                )
            except Exception as e:
                print(f"  Error inserting row: {e}")
                continue
        
        pg_conn.commit()
        print(f"  Migrated {len(rows)} rows")
    
    sqlite_conn.close()
    pg_conn.close()
    print("\nDone!")

if __name__ == '__main__':
    migrate()
