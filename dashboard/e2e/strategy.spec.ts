/**
 * E2E Tests for Strategy Page
 * TDD - Tests written first
 */
import { test, expect } from '@playwright/test';

test.describe('Strategy Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/strategy');
  });

  // =========================================================================
  // Layout
  // =========================================================================

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /strategy/i })).toBeVisible();
  });

  test('should show strategy status card', async ({ page }) => {
    const status = page.getByTestId('strategy-status');
    await expect(status).toBeVisible();
    // Should show strategy name or version info
    await expect(status).toContainText(/momentum|version/i);
  });

  // =========================================================================
  // Enable/Disable Toggle
  // =========================================================================

  test('should have enable/disable toggle', async ({ page }) => {
    const toggle = page.getByRole('switch', { name: /enable/i });
    await expect(toggle).toBeVisible();
  });

  test.fixme('should confirm before disabling strategy', async ({ page }) => {
    // FIXME: Confirmation dialog pending
    const toggle = page.getByRole('switch', { name: /enable/i });

    // If enabled, click to disable
    if (await toggle.getAttribute('aria-checked') === 'true') {
      await toggle.click();

      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText(/disable/i);
    }
  });

  // =========================================================================
  // Strategy Parameters
  // =========================================================================

  test('should display strategy parameters', async ({ page }) => {
    const params = page.getByTestId('strategy-parameters');
    await expect(params).toBeVisible();
  });

  test('should have parameter input fields', async ({ page }) => {
    const params = page.getByTestId('strategy-parameters');

    // Should have at least one parameter field
    const inputs = params.locator('input, select');
    await expect(inputs.first()).toBeVisible();
  });

  test.fixme('should validate parameter ranges', async ({ page }) => {
    // FIXME: Validation UI not fully implemented
    const params = page.getByTestId('strategy-parameters');
    const numberInput = params.locator('input[type="number"]').first();

    if (await numberInput.count() > 0) {
      // Try to enter invalid value
      await numberInput.fill('-9999');
      await numberInput.blur();

      // Should show validation error
      await expect(page.getByText(/invalid|error|min|max/i)).toBeVisible();
    }
  });

  test('should have save and revert buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /save/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /revert/i })).toBeVisible();
  });

  // =========================================================================
  // Filter Configuration
  // =========================================================================

  test('should display filter configuration', async ({ page }) => {
    const filters = page.getByTestId('filter-config');
    await expect(filters).toBeVisible();
  });

  test('should show blocked categories', async ({ page }) => {
    const filters = page.getByTestId('filter-config');
    await expect(filters).toContainText(/categories|weather|filter/i);
  });

  // =========================================================================
  // Backtesting
  // =========================================================================

  test('should have backtest section', async ({ page }) => {
    const backtest = page.getByTestId('backtest-section');
    await expect(backtest).toBeVisible();
  });

  test('should have run backtest button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /run backtest/i })).toBeVisible();
  });

  test.fixme('should show backtest results', async ({ page }) => {
    // FIXME: Backtest implementation pending
    await page.getByRole('button', { name: /run backtest/i }).click();

    // Should show loading state
    await expect(page.getByText(/running/i)).toBeVisible();

    // Wait for results
    await page.waitForSelector('[data-testid="backtest-results"]', { timeout: 30000 });
    await expect(page.getByTestId('backtest-results')).toBeVisible();
  });

  test('should show backtest history', async ({ page }) => {
    const history = page.getByTestId('backtest-history');
    await expect(history).toBeVisible();
  });

  // =========================================================================
  // Unsaved Changes
  // =========================================================================

  test.fixme('should warn about unsaved changes on navigation', async ({ page }) => {
    // FIXME: Navigation guard pending
    const params = page.getByTestId('strategy-parameters');
    const input = params.locator('input').first();

    if (await input.count() > 0) {
      await input.fill('999');

      // Try to navigate away
      await page.getByRole('link', { name: /overview/i }).click();

      // Should show warning dialog
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText(/unsaved/i);
    }
  });
});
