/**
 * E2E Tests for Strategy Page
 * TDD - Tests written first
 */
import { test, expect } from './fixtures';

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
    await expect(status).toContainText(/version/i);
  });

  // =========================================================================
  // Enable/Disable Toggle
  // =========================================================================

  test('should have enable/disable toggle', async ({ page }) => {
    const toggle = page.getByRole('switch', { name: /enable strategy/i });
    await expect(toggle).toBeVisible();
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
    const inputs = params.locator('input');
    await expect(inputs.first()).toBeVisible();
  });

  test('should have save and revert buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /save changes/i })).toBeVisible();
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
    await expect(filters).toContainText(/weather/i);
  });

  // =========================================================================
  // Decision Log
  // =========================================================================

  test('should display decision log', async ({ page }) => {
    const log = page.getByTestId('decision-log');
    await expect(log).toBeVisible();
    await expect(log.getByRole('button', { name: /export/i })).toBeVisible();
  });

  test('should show recent decisions', async ({ page }) => {
    const log = page.getByTestId('decision-log');
    await expect(log).toContainText(/will bitcoin reach/i);
  });
});
