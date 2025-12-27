import { test, expect } from '@playwright/test';
import { getMarketsSearchInput } from './helpers';

test.describe('Search Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('search input accepts text', async ({ page }) => {
    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('bitcoin');

    await expect(searchInput).toHaveValue('bitcoin');
  });

  test('pressing Enter triggers search and filters results', async ({ page }) => {
    // Get initial count from header (format: "20,086 markets • Page 1 of 101")
    const headerCount = page.locator('p.text-gray-400.text-sm').first();
    const initialCountText = await headerCount.textContent();
    const initialCount = parseInt(initialCountText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');

    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('bitcoin');
    await searchInput.press('Enter');

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Wait for the count to change
    await expect(async () => {
      const newText = await headerCount.textContent();
      const newCount = parseInt(newText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
      expect(newCount).toBeLessThan(initialCount);
    }).toPass({ timeout: 10000 });

    // Verify we have results
    const filteredCountText = await headerCount.textContent();
    const filteredCount = parseInt(filteredCountText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
    expect(filteredCount).toBeGreaterThan(0);
  });

  test('search button triggers search', async ({ page }) => {
    // Get initial count from header
    const headerCount = page.locator('p.text-gray-400.text-sm').first();
    const initialCountText = await headerCount.textContent();
    const initialCount = parseInt(initialCountText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');

    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('trump');

    const searchBtn = page.locator('button:has-text("Search")');
    await searchBtn.click();

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Wait for the count to change
    await expect(async () => {
      const newText = await headerCount.textContent();
      const newCount = parseInt(newText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
      expect(newCount).toBeLessThan(initialCount);
    }).toPass({ timeout: 10000 });

    // Verify we have results
    const filteredCountText = await headerCount.textContent();
    const filteredCount = parseInt(filteredCountText?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
    expect(filteredCount).toBeGreaterThan(0);
  });

  test('search filters results to show matching content', async ({ page }) => {
    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('bitcoin');
    await searchInput.press('Enter');

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Wait for results to update - look for bitcoin in first row
    await expect(async () => {
      const firstRowText = await page.locator('tbody tr').first().textContent();
      expect(firstRowText?.toLowerCase()).toContain('bitcoin');
    }).toPass({ timeout: 10000 });
  });

  test('search is case-insensitive', async ({ page }) => {
    const searchInput = getMarketsSearchInput(page);

    // Search with uppercase
    await searchInput.fill('BITCOIN');
    await searchInput.press('Enter');

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Wait for results to update
    await expect(async () => {
      const firstRowText = await page.locator('tbody tr').first().textContent();
      expect(firstRowText?.toLowerCase()).toContain('bitcoin');
    }).toPass({ timeout: 10000 });

    // Should find results
    const rowCount = await page.locator('tbody tr').count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('no results shows empty state', async ({ page }) => {
    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('xyznonexistentmarket12345');
    await searchInput.press('Enter');

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Wait for empty state - check header shows 0 markets
    const headerCount = page.locator('p.text-gray-400.text-sm').first();
    await expect(async () => {
      const text = await headerCount.textContent();
      expect(text).toContain('0 markets');
    }).toPass({ timeout: 10000 });
  });
});
