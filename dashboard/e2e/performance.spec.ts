/**
 * E2E Tests for Performance Page
 * TDD - Tests written first
 */
import { test, expect } from './fixtures';

test.describe('Performance Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  // =========================================================================
  // Layout
  // =========================================================================

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /performance/i })).toBeVisible();
  });

  test('should have time range selector', async ({ page }) => {
    const rangeSelector = page.getByTestId('time-range-selector');
    await expect(rangeSelector).toBeVisible();

    await expect(rangeSelector.getByRole('button', { name: /7d/i })).toBeVisible();
    await expect(rangeSelector.getByRole('button', { name: /30d/i })).toBeVisible();
    await expect(rangeSelector.getByRole('button', { name: /90d/i })).toBeVisible();
    await expect(rangeSelector.getByRole('button', { name: /all/i })).toBeVisible();
  });

  // =========================================================================
  // KPIs
  // =========================================================================

  test('should display performance KPIs', async ({ page }) => {
    const kpis = page.getByTestId('performance-kpis');
    await expect(kpis).toBeVisible();

    await expect(kpis.getByText(/total p&l/i)).toBeVisible();
    await expect(kpis.getByText(/win rate/i)).toBeVisible();
    await expect(kpis.getByText(/sharpe/i)).toBeVisible();
    await expect(kpis.getByText(/max drawdown/i)).toBeVisible();
  });

  // =========================================================================
  // Equity Curve
  // =========================================================================

  test('should display equity curve chart', async ({ page }) => {
    const chart = page.getByTestId('equity-curve-chart');
    await expect(chart).toBeVisible();

    // Should have SVG (Recharts renders SVG)
    await expect(chart.locator('svg')).toBeVisible();
  });

  test('should update chart when range changes', async ({ page }) => {
    await page.getByRole('button', { name: /7d/i }).click();
    await expect(page).toHaveURL(/range=7d/);

    // Chart should still be visible
    await expect(page.getByTestId('equity-curve-chart')).toBeVisible();
  });

  // =========================================================================
  // Win/Loss Stats
  // =========================================================================

  test('should display win/loss statistics', async ({ page }) => {
    const stats = page.getByTestId('win-loss-stats');
    await expect(stats).toBeVisible();

    await expect(stats.getByText(/winning trades/i)).toBeVisible();
    await expect(stats.getByText(/losing trades/i)).toBeVisible();
    await expect(stats.getByText(/avg win/i)).toBeVisible();
    await expect(stats.getByText(/avg loss/i)).toBeVisible();
  });

  test('should display execution quality panel', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /execution quality/i })).toBeVisible();
  });

  // =========================================================================
  // P&L Breakdown
  // =========================================================================

  test('should have P&L breakdown tabs', async ({ page }) => {
    const tabs = page.getByTestId('pnl-breakdown');
    await expect(tabs).toBeVisible();

    await expect(tabs.getByRole('tab', { name: /daily/i })).toBeVisible();
    await expect(tabs.getByRole('tab', { name: /weekly/i })).toBeVisible();
    await expect(tabs.getByRole('tab', { name: /monthly/i })).toBeVisible();
  });

  test('should switch P&L breakdown view', async ({ page }) => {
    await page.getByRole('tab', { name: /weekly/i }).click();

    await expect(page.getByRole('tab', { name: /weekly/i })).toHaveAttribute('aria-selected', 'true');
  });

  // =========================================================================
  // Trade History
  // =========================================================================

  test('should display trade history table', async ({ page }) => {
    const table = page.getByTestId('trade-history-table');
    await expect(table).toBeVisible();

    await expect(table.getByRole('columnheader', { name: /market/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /side/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /p&l/i })).toBeVisible();
    await expect(table.getByRole('columnheader', { name: /date/i })).toBeVisible();
  });

  test('should paginate trade history', async ({ page }) => {
    const pagination = page.getByTestId('trade-pagination');

    if (await pagination.isVisible()) {
      await pagination.getByRole('button', { name: /next/i }).click();
      await expect(page).toHaveURL(/page=2/);
    }
  });

  // =========================================================================
  // Empty State
  // =========================================================================

  test('should show empty state when no trades', async ({ page }) => {
    // This might show if there's no trade data
    const emptyState = page.locator('[data-testid="empty-state"]');
    const table = page.getByTestId('trade-history-table');

    // Either table with data or empty state should be visible
    const tableVisible = await table.isVisible();
    const emptyVisible = await emptyState.first().isVisible();

    expect(tableVisible || emptyVisible).toBeTruthy();
  });
});
