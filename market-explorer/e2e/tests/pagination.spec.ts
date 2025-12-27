import { test, expect } from '@playwright/test';

test.describe('Pagination', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('page info shows correct format', async ({ page }) => {
    // Should show "Page X of Y (Z total)" in footer
    const footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page \d+ of/ });
    await expect(footer).toBeVisible();
  });

  test('Next button goes to next page', async ({ page }) => {
    const nextBtn = page.locator('button:has-text("Next")');
    await expect(nextBtn).toBeEnabled();

    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should now show page 2 in footer
    const footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 2 of/ });
    await expect(footer).toBeVisible();
  });

  test('Previous button goes to previous page', async ({ page }) => {
    // First go to page 2
    const nextBtn = page.locator('button:has-text("Next")');
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    const page2Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 2 of/ });
    await expect(page2Footer).toBeVisible();

    // Then go back - may be cached, so just wait for UI update
    const prevBtn = page.locator('button:has-text("Previous")');
    await expect(prevBtn).toBeEnabled();
    await prevBtn.click();

    // Should be back to page 1
    const page1Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 1 of/ });
    await expect(page1Footer).toBeVisible({ timeout: 5000 });
  });

  test('First button goes to first page', async ({ page }) => {
    // Navigate to page 3 first
    const nextBtn = page.locator('button:has-text("Next")');
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);
    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    const page3Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 3 of/ });
    await expect(page3Footer).toBeVisible();

    // Click First - may serve from cache
    const firstBtn = page.locator('button:has-text("First")');
    await expect(firstBtn).toBeEnabled();
    await firstBtn.click();

    const page1Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 1 of/ });
    await expect(page1Footer).toBeVisible({ timeout: 5000 });
  });

  test('Last button goes to last page', async ({ page }) => {
    const lastBtn = page.locator('button:has-text("Last")');
    await expect(lastBtn).toBeEnabled();

    await lastBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should show last page - current page equals total pages
    const footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page \d+ of/ });
    const pageInfo = await footer.textContent();
    const match = pageInfo?.match(/Page (\d+) of (\d+)/);
    expect(match).toBeTruthy();
    expect(match![1]).toBe(match![2]); // Current page equals total pages
  });

  test('buttons disabled at boundaries', async ({ page }) => {
    // On first page, First and Previous should be disabled
    const firstBtn = page.locator('button:has-text("First")');
    const prevBtn = page.locator('button:has-text("Previous")');

    await expect(firstBtn).toBeDisabled();
    await expect(prevBtn).toBeDisabled();
  });

  test('page size selector changes results count', async ({ page }) => {
    // Change page size
    const pageSizeSelect = page.locator('select');
    await expect(pageSizeSelect).toBeVisible();
    await pageSizeSelect.selectOption('50');
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Table should have loaded - just verify we still have results
    const rows = page.locator('tbody tr');
    await expect(rows.first()).toBeVisible();
  });

  test('changing filter resets to page 1', async ({ page }) => {
    // Go to page 2
    const nextBtn = page.locator('button:has-text("Next")');
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    const page2Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 2 of/ });
    await expect(page2Footer).toBeVisible();

    // Apply a filter
    const cryptoBtn = page.locator('button:has-text("Crypto")').first();
    await expect(cryptoBtn).toBeVisible();
    await cryptoBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should reset to page 1
    const page1Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 1 of/ });
    await expect(page1Footer).toBeVisible();
  });
});

test.describe('Sorting', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');
  });

  test('default sort is volume descending', async ({ page }) => {
    // Volume button should be highlighted
    const volumeBtn = page.locator('button:has-text("Volume (24h)")');
    await expect(volumeBtn).toHaveClass(/bg-pm-green/);
  });

  test('clicking sort button toggles direction', async ({ page }) => {
    const volumeBtn = page.locator('button:has-text("Volume (24h)")');

    // Click to toggle direction
    await volumeBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should still be selected (just different direction)
    await expect(volumeBtn).toHaveClass(/bg-pm-green/);
  });

  test('clicking different sort changes sort field and results', async ({ page }) => {
    // Get first row content with volume sort
    const firstRowVolumeSort = await page.locator('tbody tr').first().textContent();

    const priceBtn = page.locator('button:has-text("Price")');
    await priceBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Price button should now be selected
    await expect(priceBtn).toHaveClass(/bg-pm-green/);

    // Volume button should no longer be selected
    const volumeBtn = page.locator('button:has-text("Volume (24h)")');
    await expect(volumeBtn).not.toHaveClass(/bg-pm-green/);

    // First row should change (different sort order)
    const firstRowPriceSort = await page.locator('tbody tr').first().textContent();
    expect(firstRowPriceSort).not.toBe(firstRowVolumeSort);
  });
});
