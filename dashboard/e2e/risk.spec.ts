/**
 * E2E Tests for Risk Page
 * TDD - Tests written first
 */
import { test, expect } from './fixtures';

test.describe('Risk Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/risk');
  });

  // =========================================================================
  // Layout
  // =========================================================================

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /exposure & guardrails/i })).toBeVisible();
  });

  // =========================================================================
  // Exposure Summary
  // =========================================================================

  test('should display exposure tiles', async ({ page }) => {
    await expect(page.getByText(/current exposure/i)).toBeVisible();
    await expect(page.getByText('Deployable Capital', { exact: true })).toBeVisible();
    await expect(page.getByText(/exposure %/i)).toBeVisible();
    await expect(page.getByText(/leverage/i)).toBeVisible();
  });

  test('should show exposure meter', async ({ page }) => {
    const meter = page.getByText(/exposure meter/i).locator('..');
    await expect(meter.locator('[role="progressbar"]')).toBeVisible();
  });

  // =========================================================================
  // Risk Limits
  // =========================================================================

  test('should display risk limits form', async ({ page }) => {
    const limits = page.getByRole('heading', { name: /risk limits/i }).locator('..').locator('..');
    await expect(limits.locator('input')).toHaveCount(8);
    await expect(page.getByRole('button', { name: /save limits/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /reset/i })).toBeVisible();
  });

  test('should allow editing risk limits', async ({ page }) => {
    const limits = page.getByRole('heading', { name: /risk limits/i }).locator('..').locator('..');
    const firstInput = limits.locator('input').first();
    const original = await firstInput.inputValue();
    await firstInput.fill('123');
    await expect(firstInput).toHaveValue('123');
    await firstInput.fill(original);
  });

  // =========================================================================
  // Alerts & Overrides
  // =========================================================================

  test('should show active alerts', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /active alerts/i })).toBeVisible();
    await expect(page.getByText(/exposure above 60%/i)).toBeVisible();
  });

  test('should show manual overrides', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /manual overrides/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /pause trading/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /cancel all orders/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /flatten positions/i })).toBeVisible();
  });
});
