#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Tearing down containers ==="
docker compose down

echo ""
echo "=== Rebuilding images (no cache) ==="
docker compose build --no-cache

echo ""
echo "=== Starting containers ==="
docker compose up -d

echo ""
echo "=== Waiting for services to be healthy ==="
sleep 3

echo ""
echo "=== Container status ==="
docker compose ps

echo ""
echo "=== Done! ==="
echo "Ports exposed:"
echo "  - 3000: React dashboard (Vite dev server)"
echo "  - 9050: Flask trading dashboard"
echo "  - 8081: Ingestion dashboard"
echo "  - 8000: API"
echo "  - 5433: PostgreSQL"
echo "  - 6380: Redis"
echo ""
echo "To attach to dev container:"
echo "  docker compose exec dev bash"
