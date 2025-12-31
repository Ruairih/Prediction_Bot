import { chromium } from '@playwright/test';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  await page.goto('http://localhost:3000');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  // Take screenshot of overview
  await page.screenshot({ path: '/tmp/theme-current.png', fullPage: false });
  console.log('Screenshot saved: /tmp/theme-current.png');

  // Go to settings
  await page.click('text=Settings');
  await page.waitForTimeout(1000);

  // Click on each theme and take screenshots
  const themeLabels = ['Midnight Pro', 'Aurora', 'Cyber', 'Obsidian', 'Daylight'];
  const themeNames = ['midnight-pro', 'aurora', 'cyber', 'obsidian', 'daylight'];

  for (let i = 0; i < themeLabels.length; i++) {
    const themeCard = page.locator(`button:has-text("${themeLabels[i]}")`).first();
    if (await themeCard.isVisible()) {
      await themeCard.click();
      await page.waitForTimeout(800);

      // Navigate to overview
      await page.click('text=Mission');
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `/tmp/theme-${themeNames[i]}.png`, fullPage: false });
      console.log(`Screenshot saved: /tmp/theme-${themeNames[i]}.png`);

      // Go back to settings
      await page.click('text=Settings');
      await page.waitForTimeout(500);
    }
  }

  await browser.close();
  console.log('Done!');
}

main().catch(console.error);
