#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Restarting containers (quick, uses cache) ==="
docker compose down
docker compose up -d --build

echo ""
docker compose ps
