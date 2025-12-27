import { test, expect } from '@playwright/test';
import { getMarketsSearchInput } from './helpers';

// Helper to get market count from the header
async function getMarketCount(page: import('@playwright/test').Page): Promise<number> {
  const header = page.locator('p.text-gray-400.text-sm').first();
  const text = await header.textContent();
  return parseInt(text?.replace(/,/g, '').match(/(\d+)/)?.[1] || '0');
}

test.describe('Market Detail Page', () => {
  test('navigating to market shows details', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    // Click first market link (the internal link with href starting with /markets/)
    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();

    // Should navigate to detail page
    await expect(page).toHaveURL(/\/markets\//);

    // Should show market question as heading
    const contentHeading = page.locator('h1.text-2xl');
    await expect(contentHeading).toBeVisible();
  });

  test('back button returns to list', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    // Navigate to detail
    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // Click back button
    const backBtn = page.locator('a:has-text("Back")');
    await expect(backBtn).toBeVisible();
    await backBtn.click();

    // Should return to main page
    await expect(page).toHaveURL('/');
  });

  test('displays market question', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    // Get market question text
    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    const questionText = await marketLink.textContent();
    expect(questionText).toBeTruthy();

    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // The main heading on the detail page (not in the nav) has text-2xl
    // Look for a heading that contains our question text
    const marketHeading = page.locator('h1.text-2xl').filter({ hasNotText: 'Market Explorer' }).first();
    await expect(marketHeading).toContainText(questionText!.substring(0, 20));
  });

  test('displays price data', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // Should show YES somewhere on the page
    await expect(page.locator('text=YES')).toBeVisible();
  });

  test('displays liquidity data', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // Should show volume or liquidity information
    await expect(page.getByText(/Volume|Liquidity/i).first()).toBeVisible();
  });

  test('Polymarket link is present', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('tbody tr');

    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // Should have link to Polymarket
    const polymarketLink = page.locator('a:has-text("View on Polymarket")');
    await expect(polymarketLink).toBeVisible();
    const href = await polymarketLink.getAttribute('href');
    expect(href).toContain('polymarket.com');
  });

  test('invalid market ID shows error', async ({ page }) => {
    await page.goto('/markets/invalid-market-id-12345');

    // Should show error or not found message
    await expect(page.locator('text=/not found|error|invalid/i')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Combined Workflows', () => {
  test('search then filter then sort', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');

    // 1. Search
    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('will');
    await searchInput.press('Enter');
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // 2. Filter by category
    const politicsBtn = page.locator('button:has-text("Politics")').first();
    await expect(politicsBtn).toBeVisible();
    await politicsBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // 3. Sort by price
    const priceBtn = page.locator('button:has-text("Price")');
    await priceBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Should show filtered, sorted results
    const count = await getMarketCount(page);
    expect(count).toBeGreaterThan(0);
  });

  test('browse markets, view detail, return to same page', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');

    // Go to page 2
    const nextBtn = page.locator('button:has-text("Next")');
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    const page2Footer = page.locator('span.text-gray-400.text-sm').filter({ hasText: /Page 2 of/ });
    await expect(page2Footer).toBeVisible();

    // Click a market
    const marketLink = page.locator('tbody tr a[href^="/markets/"]').first();
    await marketLink.click();
    await page.waitForURL(/\/markets\//);

    // Go back using browser back button
    await page.goBack();

    // Should return to list page
    await expect(page).toHaveURL('/');
  });

  test('apply multiple filters then clear all', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('table');

    // Get initial count
    const initialCount = await getMarketCount(page);

    // Apply search
    const searchInput = getMarketsSearchInput(page);
    await searchInput.fill('bitcoin');
    await searchInput.press('Enter');
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Apply category filter
    const cryptoBtn = page.locator('button:has-text("Crypto")').first();
    await expect(cryptoBtn).toBeVisible();
    await cryptoBtn.click();
    await page.waitForResponse(resp => resp.url().includes('/api/markets') && resp.status() === 200);

    // Clear all filters - may serve from cache
    const clearBtn = page.locator('button:has-text("Clear all filters")');
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();

    // Wait for UI to update (may be cached)
    await expect(async () => {
      const restoredCount = await getMarketCount(page);
      expect(restoredCount).toBe(initialCount);
    }).toPass({ timeout: 5000 });

    // Search should be cleared
    await expect(searchInput).toHaveValue('');
  });
});
