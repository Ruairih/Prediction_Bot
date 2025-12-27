# Market Explorer Testing Plan

## Overview

This document outlines a comprehensive testing strategy for the Market Explorer application, covering backend API tests (pytest), frontend component tests (Vitest), and end-to-end browser tests (Playwright).

## Testing Stack

| Layer | Framework | Purpose |
|-------|-----------|---------|
| Backend API | pytest + pytest-asyncio + httpx | API endpoint testing, model validation |
| Frontend Unit | Vitest + React Testing Library | Component logic, hooks, utilities |
| E2E Browser | Playwright | Full user workflow testing |

## Test Directory Structure

```
market-explorer/
├── backend/
│   └── tests/
│       ├── conftest.py              # Fixtures, test DB setup
│       ├── test_api_health.py       # Health endpoint tests
│       ├── test_api_markets.py      # Market listing/filtering tests
│       ├── test_api_categories.py   # Categories endpoint tests
│       ├── test_models.py           # Domain model validation tests
│       └── test_repositories.py     # Repository layer tests
│
├── frontend/
│   └── tests/
│       ├── setup.ts                 # Test setup (MSW, etc.)
│       ├── components/
│       │   ├── MarketTable.test.tsx
│       │   └── Layout.test.tsx
│       ├── hooks/
│       │   └── useMarkets.test.tsx
│       └── utils/
│           └── formatters.test.ts
│
└── e2e/
    ├── playwright.config.ts
    ├── fixtures/
    │   └── test-data.ts
    └── tests/
        ├── markets-listing.spec.ts   # Market browsing workflows
        ├── market-filters.spec.ts    # Filter functionality
        ├── market-search.spec.ts     # Search functionality
        ├── market-detail.spec.ts     # Detail page tests
        ├── pagination.spec.ts        # Pagination workflows
        └── visual-regression.spec.ts # Screenshot comparisons
```

---

## Phase 1: Backend API Tests (pytest)

### 1.1 Health Endpoint Tests
```python
# test_api_health.py
- test_health_returns_200
- test_health_response_schema
- test_health_contains_version
```

### 1.2 Market Listing Tests
```python
# test_api_markets.py

# Basic functionality
- test_list_markets_returns_paginated_response
- test_list_markets_default_page_size_100
- test_list_markets_default_sort_volume_desc

# Filtering
- test_filter_by_single_category
- test_filter_by_multiple_categories
- test_filter_by_min_price
- test_filter_by_max_price
- test_filter_by_price_range
- test_filter_by_min_volume
- test_filter_by_min_liquidity
- test_filter_by_search_query
- test_filter_by_resolved_true
- test_filter_by_resolved_false
- test_filter_combined_multiple_criteria

# Sorting
- test_sort_by_volume_24h_desc
- test_sort_by_volume_24h_asc
- test_sort_by_liquidity_score
- test_sort_by_yes_price
- test_sort_by_end_time
- test_sort_nulls_last

# Pagination
- test_pagination_first_page
- test_pagination_middle_page
- test_pagination_last_page
- test_pagination_has_next_true
- test_pagination_has_next_false
- test_pagination_has_prev_true
- test_pagination_has_prev_false
- test_pagination_total_pages_calculation
- test_page_size_50
- test_page_size_500

# Validation errors
- test_invalid_page_zero_returns_422
- test_invalid_page_negative_returns_422
- test_invalid_page_size_over_500_returns_422
- test_invalid_sort_field_returns_400
- test_invalid_status_value_returns_400
- test_search_too_short_returns_422

# Edge cases
- test_empty_results_returns_empty_items
- test_single_result_pagination
- test_special_characters_in_search
```

### 1.3 Market Detail Tests
```python
# test_api_markets.py (continued)
- test_get_market_by_valid_id
- test_get_market_invalid_id_returns_404
- test_get_market_response_schema
- test_get_market_includes_price_data
- test_get_market_includes_liquidity_data
```

### 1.4 Categories Tests
```python
# test_api_categories.py
- test_get_categories_returns_dict
- test_get_categories_sorted_by_count_desc
- test_get_categories_excludes_null
- test_get_categories_with_resolved_false
- test_get_categories_with_resolved_true
- test_categories_counts_accurate
```

### 1.5 Model Validation Tests
```python
# test_models.py

# PriceData
- test_price_data_valid_prices
- test_price_data_invalid_price_below_zero
- test_price_data_invalid_price_above_one
- test_price_data_bid_greater_than_ask_raises
- test_price_data_spread_calculation
- test_price_data_mid_price_calculation
- test_price_data_optional_no_price

# LiquidityData
- test_liquidity_data_valid
- test_liquidity_data_negative_volume_raises
- test_liquidity_data_negative_liquidity_raises

# Market
- test_market_empty_condition_id_raises
- test_market_empty_question_raises
- test_market_time_to_expiry_future
- test_market_time_to_expiry_past
- test_market_time_to_expiry_none
```

---

## Phase 2: Frontend Component Tests (Vitest)

### 2.1 Utility Function Tests
```typescript
// formatters.test.ts
- test_formatPrice_valid_price
- test_formatPrice_null_returns_dash
- test_formatVolume_millions
- test_formatVolume_thousands
- test_formatVolume_small
- test_formatSpread_percentage
- test_formatEndTime_days_remaining
- test_formatEndTime_hours_remaining
- test_formatEndTime_expired
```

### 2.2 Hook Tests
```typescript
// useMarkets.test.tsx
- test_useMarkets_fetches_with_correct_params
- test_useMarkets_refetches_on_filter_change
- test_useMarkets_handles_loading_state
- test_useMarkets_handles_error_state
- test_useCategories_with_resolved_filter
```

### 2.3 Component Tests
```typescript
// MarketTable.test.tsx
- test_renders_market_rows
- test_renders_loading_state
- test_renders_empty_state
- test_watchlist_toggle
- test_price_bar_colors
- test_external_link_rendered

// MarketsPage.test.tsx
- test_filter_panel_toggle
- test_category_selection
- test_search_input
- test_sort_button_click
- test_pagination_buttons
```

---

## Phase 3: End-to-End Tests (Playwright)

### 3.1 Markets Listing Workflows
```typescript
// markets-listing.spec.ts

test.describe('Markets Listing', () => {
  test('displays markets on page load')
  test('shows correct market count')
  test('displays market data in table')
  test('market rows are clickable')
  test('external Polymarket links work')
})
```

### 3.2 Filter Functionality
```typescript
// market-filters.spec.ts

test.describe('Category Filters', () => {
  test('clicking category filters results')
  test('category shows correct count')
  test('multiple categories can be selected')
  test('clicking selected category deselects it')
  test('clear filters resets categories')
})

test.describe('Status Filters', () => {
  test('Active button shows only active markets')
  test('Resolved button shows only resolved markets')
  test('All button shows all markets')
  test('default filter is Active')
})

test.describe('Price Range Filters', () => {
  test('min price filters low-priced markets')
  test('max price filters high-priced markets')
  test('price range combination works')
})

test.describe('Volume/Liquidity Filters', () => {
  test('min volume filter works')
  test('min liquidity filter works')
})
```

### 3.3 Search Functionality
```typescript
// market-search.spec.ts

test.describe('Search', () => {
  test('search input accepts text')
  test('pressing Enter triggers search')
  test('search button triggers search')
  test('search filters results')
  test('clearing search shows all results')
  test('search is case-insensitive')
  test('no results shows empty state')
})
```

### 3.4 Sorting
```typescript
// market-sorting.spec.ts

test.describe('Sorting', () => {
  test('default sort is volume descending')
  test('clicking volume toggles sort direction')
  test('clicking liquidity sorts by liquidity')
  test('clicking price sorts by price')
  test('clicking end time sorts by end time')
  test('sort indicator shows current sort')
})
```

### 3.5 Pagination
```typescript
// pagination.spec.ts

test.describe('Pagination', () => {
  test('page info shows correct count')
  test('Next button goes to next page')
  test('Previous button goes to previous page')
  test('First button goes to first page')
  test('Last button goes to last page')
  test('buttons disabled at boundaries')
  test('page size selector changes page size')
  test('changing filter resets to page 1')
})
```

### 3.6 Market Detail Page
```typescript
// market-detail.spec.ts

test.describe('Market Detail', () => {
  test('navigating to market shows details')
  test('back button returns to list')
  test('displays market question')
  test('displays price data')
  test('displays liquidity data')
  test('displays time remaining')
  test('Polymarket link is correct')
  test('invalid market ID shows error')
})
```

### 3.7 Combined Workflows
```typescript
// workflows.spec.ts

test.describe('User Workflows', () => {
  test('search then filter then sort')
  test('browse markets, view detail, return to same page')
  test('apply multiple filters then clear all')
  test('change page size mid-browsing')
})
```

---

## Test Data Strategy

### Backend Test Fixtures
```python
# conftest.py

@pytest.fixture
async def test_db():
    """Create test database with sample data."""
    # 100 markets with varied:
    # - Categories (Sports, Crypto, Politics, Other)
    # - Prices (0.05 - 0.95)
    # - Volumes (0 - 10M)
    # - Resolved status (true/false)
    # - End times (past, near future, far future)

@pytest.fixture
def sample_markets():
    """Return list of test market data."""
    return [
        {"condition_id": "test-1", "question": "Will Bitcoin reach $100k?", ...},
        {"condition_id": "test-2", "question": "Lakers vs Celtics", ...},
        # ... 100 total
    ]
```

### E2E Test Data
- Use actual database (seeded with sync_markets_v2.py)
- Tests are read-only (no mutations)
- Parallel tests safe (no shared state)

---

## CI/CD Integration

### GitHub Actions Workflow
```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Run pytest
        run: cd backend && pytest -v --cov

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Vitest
        run: cd frontend && npm test

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Playwright
        run: npx playwright install --with-deps
      - name: Run Playwright tests
        run: npx playwright test
```

---

## Coverage Targets

| Component | Target | Priority |
|-----------|--------|----------|
| API Endpoints | 95% | High |
| Domain Models | 95% | High |
| Repository Layer | 90% | High |
| React Hooks | 85% | Medium |
| React Components | 80% | Medium |
| E2E Workflows | 100% of critical paths | High |

---

## Test Execution Commands

```bash
# Backend tests
cd backend
pytest -v                          # All tests
pytest -v --cov=src/explorer       # With coverage
pytest -v -k "test_api"            # Only API tests
pytest -v -k "test_model"          # Only model tests

# Frontend tests
cd frontend
npm test                           # Run Vitest
npm test -- --coverage             # With coverage
npm test -- --watch                # Watch mode

# E2E tests
cd e2e
npx playwright test                # All tests
npx playwright test --headed       # With browser visible
npx playwright test --ui           # Interactive UI mode
npx playwright test filters        # Specific test file
npx playwright show-report         # View HTML report
```

---

## Critical Test Scenarios (Must Pass)

1. **Market Listing** - Users can see paginated list of markets
2. **Category Filter** - Clicking Sports shows only Sports markets
3. **Search** - Searching "bitcoin" returns Bitcoin-related markets
4. **Sorting** - Volume sort shows highest volume first
5. **Pagination** - Can navigate through all pages
6. **Market Detail** - Clicking market shows full details
7. **Filter Reset** - Clear filters returns to default state
8. **Empty State** - Invalid search shows "No markets found"

---

## Implementation Priority

1. **Phase 1 (Day 1)**: Backend API tests - most critical for data integrity
2. **Phase 2 (Day 1-2)**: E2E Playwright tests - validates user workflows
3. **Phase 3 (Day 2)**: Frontend unit tests - component-level coverage

This plan ensures comprehensive coverage of all functionality while prioritizing the most critical paths first.
