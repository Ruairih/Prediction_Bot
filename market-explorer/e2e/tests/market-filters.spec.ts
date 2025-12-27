import { test, expect } from '@playwright/test';

// Helper to get market count from the header
async function getMarketCount(page: import('@playwright/test').Page): Promise<number> {
  const header = page.locator('p.text-gray-400.text-sm').first();
  const text = await header.textContent();
  return parseInt(text?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
}

test.describe('Category Filters', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('clicking category button filters results', async ({ page }) => {
    // Get initial count
    const initialCount = await getMarketCount(page);

    // Click on Politics category
    const politicsBtn = page.locator('button:has-text("Politics")').first();
    await expect(politicsBtn).toBeVisible();
    await politicsBtn.click();

    // Wait for API response
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Count should change
    const newCount = await getMarketCount(page);
    expect(newCount).toBeGreaterThan(0);
    expect(newCount).not.toBe(initialCount);
  });

  test('category shows count in parentheses', async ({ page }) => {
    // Look for any button with count in parentheses
    const categoryWithCount = page.locator('button').filter({ hasText: /\(\d+\)/ });
    await expect(categoryWithCount.first()).toBeVisible();
  });

  test('clicking selected category deselects it', async ({ page }) => {
    const politicsBtn = page.locator('button:has-text("Politics")').first();
    await expect(politicsBtn).toBeVisible();

    // Get initial count
    const initialCount = await getMarketCount(page);

    // Click to select
    await politicsBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Get filtered count
    const filteredCount = await getMarketCount(page);
    expect(filteredCount).toBeLessThan(initialCount);

    // Click again to deselect - may serve from cache
    await politicsBtn.click();

    // Wait for UI to update
    await expect(async () => {
      const restoredCount = await getMarketCount(page);
      expect(restoredCount).toBe(initialCount);
    }).toPass({ timeout: 5000 });
  });

  test('clear filters resets to default', async ({ page }) => {
    // Get initial count
    const initialCount = await getMarketCount(page);

    // Apply category filter
    const cryptoBtn = page.locator('button:has-text("Crypto")').first();
    await expect(cryptoBtn).toBeVisible();
    await cryptoBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Verify filter applied
    const filteredCount = await getMarketCount(page);
    expect(filteredCount).toBeLessThan(initialCount);

    // Click clear filters - may serve from cache
    const clearBtn = page.locator('button:has-text("Clear all filters")');
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();

    // Wait for UI to update
    await expect(async () => {
      const restoredCount = await getMarketCount(page);
      expect(restoredCount).toBe(initialCount);
    }).toPass({ timeout: 5000 });
  });
});

test.describe('Status Filters', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('default filter is Active', async ({ page }) => {
    // Active button should be highlighted
    const activeBtn = page.locator('button:has-text("Active")');
    await expect(activeBtn).toBeVisible();
    await expect(activeBtn).toHaveClass(/bg-blue-600/);
  });

  test('clicking Resolved shows resolved markets', async ({ page }) => {
    // Get active count first
    const activeCount = await getMarketCount(page);

    const resolvedBtn = page.locator('button:has-text("Resolved")');
    await expect(resolvedBtn).toBeVisible();
    await resolvedBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should update results
    const resolvedCount = await getMarketCount(page);
    expect(resolvedCount).toBeGreaterThan(0);
    expect(resolvedCount).not.toBe(activeCount);

    // Resolved button should be highlighted
    await expect(resolvedBtn).toHaveClass(/bg-purple-600/);
  });

  test('clicking All shows all markets', async ({ page }) => {
    // Get active count first
    const activeCount = await getMarketCount(page);

    const allBtn = page.locator('button:has-text("All")').last();
    await expect(allBtn).toBeVisible();
    await allBtn.click();

    // Wait for API response or UI update
    try {
      await page.waitForResponse(
        resp => resp.url().includes('/api/markets') && resp.status() === 200,
        { timeout: 5000 }
      );
    } catch {
      // May be cached, wait for UI update instead
      await page.waitForTimeout(500);
    }

    // All should include active + resolved, so count should be >= active
    const allCount = await getMarketCount(page);
    expect(allCount).toBeGreaterThanOrEqual(activeCount);
  });
});

test.describe('Price Range Filters', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('min price filter reduces results', async ({ page }) => {
    // Get initial count
    const initialCount = await getMarketCount(page);

    // Find min price input
    const minPriceInput = page.locator('input[placeholder="0.00"]').first();
    await expect(minPriceInput).toBeVisible();

    await minPriceInput.fill('0.5');
    await minPriceInput.press('Tab');
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Results should be filtered
    const filteredCount = await getMarketCount(page);
    expect(filteredCount).toBeLessThan(initialCount);
  });

  test('max price filter reduces results', async ({ page }) => {
    // Get initial count
    const initialCount = await getMarketCount(page);

    const maxPriceInput = page.locator('input[placeholder="1.00"]').first();
    await expect(maxPriceInput).toBeVisible();

    await maxPriceInput.fill('0.3');
    await maxPriceInput.press('Tab');
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Results should be filtered
    const filteredCount = await getMarketCount(page);
    expect(filteredCount).toBeLessThan(initialCount);
  });
});
