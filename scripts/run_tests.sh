#!/bin/bash
# =============================================================================
# Run All Tests
# =============================================================================
# Convenience script to run tests with common configurations.
#
# Usage:
#   ./scripts/run_tests.sh              # Run all tests
#   ./scripts/run_tests.sh unit         # Run unit tests only
#   ./scripts/run_tests.sh integration  # Run integration tests only
#   ./scripts/run_tests.sh coverage     # Run with coverage report
#   ./scripts/run_tests.sh quick        # Run fast tests only
# =============================================================================

set -e

# Default database URL
export DATABASE_URL="${DATABASE_URL:-postgresql://predict:predict@localhost:5433/predict}"

case "${1:-all}" in
    unit)
        echo "Running unit tests..."
        pytest src/polymarket_bot/ -v -m "not integration" --tb=short
        ;;
    integration)
        echo "Running integration tests..."
        pytest tests/integration/ -v -m integration --tb=short
        ;;
    coverage)
        echo "Running tests with coverage..."
        pytest src/polymarket_bot/ -v \
            --cov=src/polymarket_bot \
            --cov-report=html \
            --cov-report=term-missing \
            --tb=short
        echo ""
        echo "Coverage report: htmlcov/index.html"
        ;;
    quick)
        echo "Running quick tests (no integration, no slow)..."
        pytest src/polymarket_bot/ -v -m "not integration and not slow" --tb=short -x
        ;;
    storage)
        echo "Running storage layer tests..."
        pytest src/polymarket_bot/storage/tests/ -v --tb=short
        ;;
    all|*)
        echo "Running all tests..."
        pytest -v --tb=short
        ;;
esac
