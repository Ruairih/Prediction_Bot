/**
 * Comprehensive E2E Smoke Tests for Dashboard Pages
 * Uses shared API mocks for stable rendering.
 */
import { test, expect } from './fixtures';

// =============================================================================
// Overview Page Tests
// =============================================================================
test.describe('Overview Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display the sidebar navigation', async ({ page }) => {
    const sidebar = page.getByTestId('sidebar');
    await expect(sidebar).toBeVisible();
  });

  test('should display bot status widget', async ({ page }) => {
    const statusWidget = page.getByTestId('bot-status');
    await expect(statusWidget).toBeVisible();
  });

  test('should display KPI tiles', async ({ page }) => {
    const kpiSection = page.locator('[data-testid^="kpi-"]');
    const count = await kpiSection.count();
    expect(count).toBeGreaterThan(0);
  });

  test('should display activity stream', async ({ page }) => {
    const activityStream = page.getByTestId('activity-stream');
    await expect(activityStream).toBeVisible();
  });

  test('should show mode indicator in status bar', async ({ page }) => {
    const modeIndicator = page.getByTestId('mode-indicator');
    await expect(modeIndicator).toBeVisible();
  });
});

// =============================================================================
// Positions Page Tests
// =============================================================================
test.describe('Positions Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/positions');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /positions & orders/i })).toBeVisible();
  });

  test('should display positions summary', async ({ page }) => {
    const summary = page.getByTestId('positions-summary');
    await expect(summary).toBeVisible();
  });

  test('should display positions table', async ({ page }) => {
    const table = page.getByTestId('positions-table');
    await expect(table).toBeVisible();
  });
});

// =============================================================================
// Performance Page Tests
// =============================================================================
test.describe('Performance Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/performance');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /performance/i })).toBeVisible();
  });

  test('should display equity curve chart', async ({ page }) => {
    const chart = page.getByTestId('equity-curve-chart');
    await expect(chart).toBeVisible();
  });

  test('should display execution quality panel', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /execution quality/i })).toBeVisible();
  });
});

// =============================================================================
// Markets Page Tests
// =============================================================================
test.describe('Markets Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/markets');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /market radar/i })).toBeVisible();
  });

  test('should have search input', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();
  });

  test('should display markets table', async ({ page }) => {
    const table = page.getByRole('table');
    await expect(table).toBeVisible();
  });
});

// =============================================================================
// Market Deep Link Tests
// =============================================================================
test.describe('Market Deep Links', () => {
  test('should navigate from pipeline candidate to selected market', async ({ page }) => {
    await page.goto('/pipeline');

    const marketLink = page.getByRole('link', { name: 'Will Bitcoin reach $100k by end of 2024?' });
    await Promise.all([
      page.waitForURL('**/markets**'),
      marketLink.first().click(),
    ]);

    const detailPanel = page.getByRole('heading', { name: /selected market/i }).locator('..');
    await expect(detailPanel.getByText('Will Bitcoin reach $100k by end of 2024?')).toBeVisible();
  });

  test('should navigate from activity drawer to selected market', async ({ page }) => {
    await page.goto('/activity');

    const firstItem = page.getByTestId('activity-list-item').first();
    await firstItem.click();

    const drawer = page.getByTestId('activity-drawer');
    await expect(drawer).toBeVisible();

    const marketLink = drawer.getByRole('link', { name: /view market details/i });
    await Promise.all([
      page.waitForURL('**/markets**'),
      marketLink.click(),
    ]);

    const detailPanel = page.getByRole('heading', { name: /selected market/i }).locator('..');
    await expect(detailPanel.getByText('Will Bitcoin reach $100k by end of 2024?')).toBeVisible();
  });
});

// =============================================================================
// Pipeline Page Tests
// =============================================================================
test.describe('Pipeline Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/pipeline');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /pipeline/i })).toBeVisible();
  });

  test('should display rejection funnel', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /rejection funnel/i })).toBeVisible();
  });
});

// =============================================================================
// Strategy Page Tests
// =============================================================================
test.describe('Strategy Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/strategy');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /strategy/i })).toBeVisible();
  });

  test('should display decision log', async ({ page }) => {
    const log = page.getByTestId('decision-log');
    await expect(log).toBeVisible();
  });
});

// =============================================================================
// Risk Page Tests
// =============================================================================
test.describe('Risk Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/risk');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /exposure & guardrails/i })).toBeVisible();
  });
});

// =============================================================================
// Activity Page Tests
// =============================================================================
test.describe('Activity Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/activity');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /^activity$/i })).toBeVisible();
  });

  test('should display activity list', async ({ page }) => {
    const activityList = page.getByTestId('activity-list');
    await expect(activityList).toBeVisible();
  });

  test('should display activity filters', async ({ page }) => {
    const filters = page.getByTestId('activity-filters');
    await expect(filters).toBeVisible();
  });
});

// =============================================================================
// System Page Tests
// =============================================================================
test.describe('System Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/system');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /system/i })).toBeVisible();
  });

  test('should display system health grid', async ({ page }) => {
    const health = page.getByTestId('system-health');
    await expect(health).toBeVisible();
  });
});

// =============================================================================
// Settings Page Tests
// =============================================================================
test.describe('Settings Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('should display page title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /operator preferences/i })).toBeVisible();
  });
});

// =============================================================================
// Navigation Tests
// =============================================================================
test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should navigate to all pages from sidebar', async ({ page }) => {
    const routes = [
      { name: 'portfolio', url: '/positions' },
      { name: 'markets', url: '/markets' },
      { name: 'pipeline', url: '/pipeline' },
      { name: 'strategy', url: '/strategy' },
      { name: 'performance', url: '/performance' },
      { name: 'risk', url: '/risk' },
      { name: 'activity', url: '/activity' },
      { name: 'system', url: '/system' },
      { name: 'settings', url: '/settings' },
    ];

    for (const route of routes) {
      const link = page.getByRole('link', { name: new RegExp(route.name, 'i') });
      if (await link.isVisible()) {
        await link.click();
        await expect(page).toHaveURL(new RegExp(route.url));
        await page.goto('/');
      }
    }
  });
});
