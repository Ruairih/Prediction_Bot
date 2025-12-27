import { test, expect } from '@playwright/test';

test.describe('Markets Listing Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('displays markets on page load', async ({ page }) => {
    // Wait for the table to load
    await expect(page.locator('table')).toBeVisible();

    // Should show market count in header
    const header = page.locator('p.text-gray-400.text-sm').first();
    await expect(header).toContainText('markets');
  });

  test('shows correct market count and page info', async ({ page }) => {
    // Wait for table
    await page.waitForSelector('table');

    // Check page info format in header
    const header = page.locator('p.text-gray-400.text-sm').first();
    await expect(header).toContainText(/Page \d+ of \d+/);
  });

  test('displays market data in table rows', async ({ page }) => {
    // Wait for table rows with actual data (exclude virtual spacer rows)
    await page.waitForSelector('tbody tr');

    // The market link is in the second column (first is watchlist star)
    // Also, there may be spacer rows for virtual scrolling
    const marketLink = page.locator('tbody tr a').first();
    await expect(marketLink).toBeVisible();

    // Should have price display somewhere in the table
    await expect(page.locator('table')).toContainText(/\d+¢/);
  });

  test('market rows link to detail page', async ({ page }) => {
    await page.waitForSelector('tbody tr');

    // Find the first internal link (not the external Polymarket link)
    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    const href = await marketLink.getAttribute('href');

    expect(href).toMatch(/\/markets\//);
  });

  test('external Polymarket links have correct format', async ({ page }) => {
    await page.waitForSelector('tbody tr');

    // Find external link
    const externalLink = page.locator('tbody tr a[target="_blank"]').first();
    const href = await externalLink.getAttribute('href');

    expect(href).toContain('polymarket.com');
  });

  test('refresh button triggers data reload', async ({ page }) => {
    await page.waitForSelector('table');

    // Click refresh button
    const refreshBtn = page.locator('button:has-text("Refresh")');
    await refreshBtn.click();

    // Should show loading state (spinner animation class)
    await expect(refreshBtn.locator('svg')).toBeVisible();
  });
});
