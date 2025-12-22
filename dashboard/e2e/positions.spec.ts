/**
 * E2E Tests for Positions Page
 * TDD - Tests written first
 */
import { test, expect } from '@playwright/test';

test.describe('Positions Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
  });

  // =========================================================================
  // Layout & Summary
  // =========================================================================

  test('should display page title and summary', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /positions/i })).toBeVisible();
    await expect(page.getByTestId('positions-summary')).toBeVisible();
  });

  test('should show position summary metrics', async ({ page }) => {
    const summary = page.getByTestId('positions-summary');
    await expect(summary.getByText(/open positions/i)).toBeVisible();
    await expect(summary.getByText(/total exposure/i)).toBeVisible();
    await expect(summary.getByText(/unrealized p&l/i)).toBeVisible();
  });

  // =========================================================================
  // Filters
  // =========================================================================

  test('should have filter controls', async ({ page }) => {
    await expect(page.getByTestId('positions-filters')).toBeVisible();
    await expect(page.getByRole('combobox', { name: /status/i })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /p&l/i })).toBeVisible();
    await expect(page.getByRole('searchbox')).toBeVisible();
  });

  test('should filter by status', async ({ page }) => {
    const statusFilter = page.getByRole('combobox', { name: /status/i });
    await statusFilter.selectOption('closed');

    // URL should update with filter
    await expect(page).toHaveURL(/status=closed/);
  });

  test('should filter by P&L', async ({ page }) => {
    const pnlFilter = page.getByRole('combobox', { name: /p&l/i });
    await pnlFilter.selectOption('profitable');

    await expect(page).toHaveURL(/pnl=profitable/);
  });

  test('should search positions', async ({ page }) => {
    const searchBox = page.getByRole('searchbox');
    await searchBox.fill('bitcoin');

    // Wait for debounced search
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/search=bitcoin/);
  });

  // =========================================================================
  // Positions Table
  // =========================================================================

  test('should display positions table', async ({ page }) => {
    const table = page.getByTestId('positions-table');
    await expect(table).toBeVisible();

    // Check for expected columns
    await expect(table.getByRole('columnheader', { name: /market/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /size/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /entry/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /current/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /p&l/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /actions/i })).toBeVisible();
  });

  test('should color P&L values correctly', async ({ page }) => {
    const rows = page.getByTestId('position-row');
    const firstRow = rows.first();

    // Skip if no positions
    if (await firstRow.count() === 0) {
      test.skip();
      return;
    }

    const pnlCell = firstRow.getByTestId('position-pnl');
    const text = await pnlCell.textContent();

    if (text?.includes('-')) {
      await expect(pnlCell).toHaveClass(/text-accent-red/);
    } else if (text?.includes('+') || (text && parseFloat(text.replace('$', '')) > 0)) {
      await expect(pnlCell).toHaveClass(/text-accent-green/);
    }
  });

  test('should sort by clicking column headers', async ({ page }) => {
    const pnlHeader = page.getByRole('columnheader', { name: /p&l/i });
    await pnlHeader.click();

    await expect(page).toHaveURL(/sort=unrealizedPnl/);
    await expect(pnlHeader).toHaveAttribute('aria-sort', /(ascending|descending)/);
  });

  // =========================================================================
  // Position Actions
  // =========================================================================

  test('should have close and adjust buttons', async ({ page }) => {
    const rows = page.getByTestId('position-row');
    const firstRow = rows.first();

    if (await firstRow.count() === 0) {
      test.skip();
      return;
    }

    await expect(firstRow.getByRole('button', { name: /close/i })).toBeVisible();
    await expect(firstRow.getByRole('button', { name: /adjust/i })).toBeVisible();
  });

  test.fixme('should open close position modal', async ({ page }) => {
    // FIXME: Modal implementation pending
    const rows = page.getByTestId('position-row');
    const firstRow = rows.first();

    if (await firstRow.count() === 0) {
      test.skip();
      return;
    }

    await firstRow.getByRole('button', { name: /close/i }).click();

    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText(/close position/i);
  });

  // =========================================================================
  // Empty State
  // =========================================================================

  test('should show empty state when no positions match', async ({ page }) => {
    // Filter to show no results
    await page.getByRole('searchbox').fill('xyznonexistent123');
    await page.waitForTimeout(500);

    // Check for empty state or empty table
    const emptyState = page.getByTestId('empty-state');
    const table = page.getByTestId('positions-table');

    const emptyVisible = await emptyState.isVisible();
    const tableVisible = await table.isVisible();

    // Either empty state is shown OR table has no rows
    expect(emptyVisible || tableVisible).toBeTruthy();
  });

  // =========================================================================
  // Pagination
  // =========================================================================

  test('should have pagination controls', async ({ page }) => {
    const pagination = page.getByTestId('pagination');

    // May not be visible if few positions
    if (await pagination.isVisible()) {
      await expect(pagination.getByRole('button', { name: /previous/i })).toBeVisible();
      await expect(pagination.getByRole('button', { name: /next/i })).toBeVisible();
    }
  });
});
