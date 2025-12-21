#!/usr/bin/env python3
"""
Run the ingestion service standalone with live dashboard.

Usage:
    python scripts/run_ingestion.py

Dashboard will be available at http://localhost:8081

Features:
- Real-time price updates from Polymarket WebSocket
- Live monitoring dashboard
- Automatic reconnection on disconnect
- Market data from 10,000+ active markets

Credentials:
- Loads from polymarket_api_creds.json in project root
- G3/G5 features require CLOB API auth (not yet implemented)
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Get project root (parent of scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Credentials file path
CREDS_FILE = PROJECT_ROOT / "polymarket_api_creds.json"


def load_credentials() -> dict | None:
    """Load Polymarket API credentials from JSON file."""
    if not CREDS_FILE.exists():
        return None

    try:
        with open(CREDS_FILE) as f:
            creds = json.load(f)

        # Validate required fields
        required = ["api_key", "api_secret", "api_passphrase"]
        if all(creds.get(k) and creds[k] != f"your-{k.replace('_', '-')}-here" for k in required):
            return creds
        return None
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load credentials: {e}")
        return None

from polymarket_bot.ingestion import (
    IngestionConfig,
    IngestionService,
)


async def main():
    # Configure logging
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load credentials from file
    creds = load_credentials()
    has_api_key = creds is not None

    print("=" * 60)
    print("POLYMARKET INGESTION SERVICE")
    print("=" * 60)
    print()
    print("Dashboard: http://localhost:8081")
    print("Health:    http://localhost:8081/health")
    print("Metrics:   http://localhost:8081/api/metrics")
    print("Events:    http://localhost:8081/api/events")
    print()
    if has_api_key:
        print(f"Credentials: Loaded from {CREDS_FILE.name}")
        # Note: G3/G5 require CLOB API auth headers (not yet implemented in client)
        # For now, disable these features to avoid 401 errors
        print("G3 (size backfill): DISABLED (CLOB auth not implemented)")
        print("G5 (price check):   DISABLED (CLOB auth not implemented)")
    else:
        print(f"Credentials: Not found at {CREDS_FILE}")
        print("G3/G5 features: DISABLED")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Configure service
    # Note: G3/G5 disabled until CLOB API auth is implemented in client
    config = IngestionConfig(
        # Dashboard settings
        dashboard_enabled=True,
        dashboard_host="0.0.0.0",
        dashboard_port=8081,
        # Subscribe to all active markets
        subscribe_all_markets=True,
        # Trade age filter (G1 protection) - always enabled
        max_trade_age_seconds=300,
        # G3/G5 disabled - CLOB API requires auth headers not yet implemented
        backfill_missing_size=False,
        check_price_divergence=False,
        # WebSocket settings
        heartbeat_timeout=60.0,  # More lenient timeout
        max_reconnect_delay=30.0,
    )

    # Create service
    service = IngestionService(config=config)

    # Start service
    await service.start()

    # Print status periodically
    try:
        while True:
            await asyncio.sleep(10)
            metrics = service.metrics
            if metrics:
                print(
                    f"[Status] Events: {metrics.events_received:,} | "
                    f"Rate: {metrics.events_per_second:.1f}/s | "
                    f"Uptime: {metrics.uptime_seconds:.0f}s"
                )
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()
        print("\nService stopped.")


if __name__ == "__main__":
    asyncio.run(main())
