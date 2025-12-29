/**
 * Debug test for market navigation
 */
import { test, expect } from './fixtures';

test.describe.skip('Debug Market Navigation', () => {
  test('debug pipeline to markets navigation', async ({ page }) => {
    // Go to pipeline page
    await page.goto('/pipeline');
    await page.waitForTimeout(3000); // Wait for data to load

    // Take screenshot of pipeline page
    await page.screenshot({ path: 'test-results/pipeline-before.png', fullPage: true });

    // Scroll down to find market links
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);

    // Take screenshot after scroll
    await page.screenshot({ path: 'test-results/pipeline-scrolled.png', fullPage: true });

    // Find the first market link
    const marketLinks = page.locator('a[href*="/markets?conditionId="]');
    const count = await marketLinks.count();
    console.log(`Found ${count} market links on pipeline page`);

    if (count > 0) {
      const firstLink = marketLinks.first();
      const href = await firstLink.getAttribute('href');
      const linkText = await firstLink.textContent();
      console.log(`First link href: ${href}`);
      console.log(`First link text: ${linkText}`);

      // Click the link
      await firstLink.click();
      await page.waitForTimeout(2000);

      // Log the current URL
      const currentUrl = page.url();
      console.log(`Navigated to URL: ${currentUrl}`);

      // Take screenshot of markets page
      await page.screenshot({ path: 'test-results/markets-after.png', fullPage: true });

      // Check if the URL has conditionId
      expect(currentUrl).toContain('/markets');

      // Log what we see
      const pageText = await page.textContent('body');
      console.log(`Page contains "Selected Market": ${pageText?.includes('Selected Market')}`);
      console.log(`Page contains market detail: ${pageText?.includes('Bid / Ask') || pageText?.includes('Market Detail')}`);

      // Check if there's any selected market content
      const detailSection = page.locator('text=Selected Market').locator('xpath=..');
      if (await detailSection.isVisible()) {
        const sectionText = await detailSection.textContent();
        console.log(`Detail section content preview: ${sectionText?.slice(0, 300)}`);
      }
    } else {
      console.log('No market links found! Looking for "View Market Details" links...');
      const viewMarketLinks = page.locator('text=View Market Details');
      const viewCount = await viewMarketLinks.count();
      console.log(`Found ${viewCount} "View Market Details" links`);
    }
  });

  test('check URL parameter handling on Markets page', async ({ page }) => {
    // Go directly to markets with a conditionId
    const testConditionId = '0xf2cea45ec282af4f302d2ab85ede73678cd692ebf8c3ab6d52bfa5e19f44c553';
    await page.goto(`/markets?conditionId=${testConditionId}`);
    await page.waitForTimeout(3000);

    // Take screenshot
    await page.screenshot({ path: 'test-results/markets-direct-link.png', fullPage: true });

    // Check the URL
    const currentUrl = page.url();
    console.log(`Current URL: ${currentUrl}`);

    // Check if detail panel is showing
    const pageText = await page.textContent('body');
    console.log(`Has "Selected Market": ${pageText?.includes('Selected Market')}`);
    console.log(`Has "Market Detail": ${pageText?.includes('Market Detail')}`);

    // Look for any indication that a market is selected
    const detailPanel = page.locator('.space-y-4.text-sm');
    const detailCount = await detailPanel.count();
    console.log(`Detail panel sections: ${detailCount}`);

    if (detailCount > 0) {
      const firstDetail = await detailPanel.first().textContent();
      console.log(`First detail section: ${firstDetail?.slice(0, 200)}`);
    }
  });
});
