/**
 * E2E Tests for System Page
 * TDD - Tests written first
 */
import { test, expect } from '@playwright/test';

test.describe('System Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/system');
  });

  // =========================================================================
  // Layout
  // =========================================================================

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /system/i })).toBeVisible();
  });

  // =========================================================================
  // Health Overview
  // =========================================================================

  test('should display system health grid', async ({ page }) => {
    const health = page.getByTestId('system-health');
    await expect(health).toBeVisible();
  });

  test('should show overall health status', async ({ page }) => {
    const status = page.getByTestId('overall-health-status');
    await expect(status).toBeVisible();

    // Should have status indicator
    await expect(status.locator('[data-status]')).toBeVisible();
  });

  test('should display service status cards', async ({ page }) => {
    const cards = page.getByTestId('service-status-card');
    await expect(cards.first()).toBeVisible();

    // Should show status and latency
    const firstCard = cards.first();
    await expect(firstCard.getByText(/healthy|degraded|unhealthy/i)).toBeVisible();
  });

  // =========================================================================
  // Connection Status
  // =========================================================================

  test('should display WebSocket status', async ({ page }) => {
    const wsStatus = page.getByTestId('websocket-status');
    await expect(wsStatus).toBeVisible();

    await expect(wsStatus.getByText(/connected|disconnected/i)).toBeVisible();
  });

  test('should display database status', async ({ page }) => {
    const dbStatus = page.getByTestId('database-status');
    await expect(dbStatus).toBeVisible();

    // Should show connection status and latency
    await expect(dbStatus).toContainText(/connected|disconnected/i);
    await expect(dbStatus).toContainText(/ms/i);
  });

  // =========================================================================
  // Rate Limits
  // =========================================================================

  test('should display rate limit status', async ({ page }) => {
    const rateLimits = page.getByTestId('rate-limits');
    await expect(rateLimits).toBeVisible();
  });

  test('should show rate limit progress bars', async ({ page }) => {
    const rateLimits = page.getByTestId('rate-limits');
    const progressBars = rateLimits.locator('[role="progressbar"]');

    await expect(progressBars.first()).toBeVisible();
  });

  // =========================================================================
  // Log Viewer
  // =========================================================================

  test('should display log viewer', async ({ page }) => {
    const logs = page.getByTestId('log-viewer');
    await expect(logs).toBeVisible();
  });

  test('should have log filter controls', async ({ page }) => {
    const logFilters = page.getByTestId('log-filters');
    await expect(logFilters).toBeVisible();

    await expect(logFilters.getByRole('combobox', { name: /level/i })).toBeVisible();
    await expect(logFilters.getByRole('searchbox')).toBeVisible();
  });

  test('should filter logs by level', async ({ page }) => {
    const levelSelect = page.getByTestId('log-filters').locator('select');
    await levelSelect.selectOption('error');

    // Log display should update (URL may or may not update based on implementation)
    await expect(levelSelect).toHaveValue('error');
  });

  test('should search logs', async ({ page }) => {
    const searchBox = page.getByTestId('log-filters').getByRole('searchbox');
    await searchBox.fill('error');

    await page.waitForTimeout(500);
    // Verify search box has value
    await expect(searchBox).toHaveValue('error');
  });

  test('should have auto-scroll toggle', async ({ page }) => {
    const toggle = page.getByRole('switch', { name: /auto.?scroll/i });
    await expect(toggle).toBeVisible();
  });

  // =========================================================================
  // Configuration
  // =========================================================================

  test('should display system configuration', async ({ page }) => {
    const config = page.getByTestId('system-config');
    await expect(config).toBeVisible();

    await expect(config.getByText(/version/i)).toBeVisible();
    await expect(config.getByText(/environment/i)).toBeVisible();
  });

  test('should have copy config button', async ({ page }) => {
    const copyBtn = page.getByRole('button', { name: /copy/i });
    await expect(copyBtn).toBeVisible();
  });

  // =========================================================================
  // Uptime
  // =========================================================================

  test('should display uptime', async ({ page }) => {
    const uptime = page.getByTestId('system-uptime');
    await expect(uptime).toBeVisible();

    await expect(uptime.getByText(/uptime/i)).toBeVisible();
  });

  // =========================================================================
  // Refresh
  // =========================================================================

  test('should have refresh button', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh/i });
    await expect(refreshBtn).toBeVisible();
  });

  test('should show last updated time', async ({ page }) => {
    await expect(page.getByText(/last.*updated|refreshed/i)).toBeVisible();
  });
});
