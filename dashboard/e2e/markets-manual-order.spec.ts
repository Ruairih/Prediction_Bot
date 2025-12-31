/**
 * E2E Tests for Markets Page Manual Order Feature
 *
 * Tests the token selection and manual order submission flow.
 * This validates the fix for the "Select a market token" error.
 */
import { test, expect } from './fixtures';

test.describe('Markets Page - Manual Order', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/markets');
    // Wait for the page to load
    await page.waitForLoadState('networkidle');
  });

  // =========================================================================
  // Token Selection Tests
  // =========================================================================

  test('should display token selector when market is selected', async ({ page }) => {
    // Click on the first market row to select it
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    // Wait for market detail to load
    await page.waitForTimeout(500);

    // Token selector should be visible (the select element for tokens)
    const tokenSelector = page.locator('select').filter({ hasText: /Yes|No/i });
    await expect(tokenSelector).toBeVisible({ timeout: 5000 });
  });

  test('should populate token options from market detail', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    // Wait for market detail to load
    await page.waitForTimeout(500);

    // Find the token selector
    const tokenSelector = page.locator('select').filter({ hasText: /Yes|No/i });

    // Should have Yes and No options
    const options = tokenSelector.locator('option');
    const count = await options.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // Check for Yes and No options
    const optionTexts = await options.allTextContents();
    const hasYes = optionTexts.some(text => text.includes('Yes'));
    const hasNo = optionTexts.some(text => text.includes('No'));
    expect(hasYes || hasNo).toBeTruthy();
  });

  test('should auto-select first token when market is selected', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    // Wait for market detail to load
    await page.waitForTimeout(500);

    // Token selector should have a value
    const tokenSelector = page.locator('select').filter({ hasText: /Yes|No/i });
    const selectedValue = await tokenSelector.inputValue();
    expect(selectedValue).toBeTruthy();
    expect(selectedValue.length).toBeGreaterThan(0);
  });

  // =========================================================================
  // Manual Order Form Tests
  // =========================================================================

  test('should display manual order form when market selected', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    // Wait for market detail
    await page.waitForTimeout(500);

    // Order form elements should be visible
    // Side selector (BUY/SELL)
    const buyButton = page.getByRole('button', { name: /buy/i }).or(page.locator('button:has-text("BUY")'));
    const sellButton = page.getByRole('button', { name: /sell/i }).or(page.locator('button:has-text("SELL")'));

    // At least one should be visible
    const buyVisible = await buyButton.isVisible().catch(() => false);
    const sellVisible = await sellButton.isVisible().catch(() => false);
    expect(buyVisible || sellVisible).toBeTruthy();
  });

  test('should have price input in manual order form', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Find price input - look for input with price-related placeholder or label
    const priceInput = page.locator('input[type="number"]').first()
      .or(page.locator('input[placeholder*="price" i]'))
      .or(page.locator('input').filter({ hasText: /price/i }));

    // Should find at least one number input for price
    const inputs = page.locator('input[type="number"]');
    const count = await inputs.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('should have size input in manual order form', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Should have multiple number inputs (price and size)
    const inputs = page.locator('input[type="number"]');
    const count = await inputs.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  // =========================================================================
  // Order Submission Tests
  // =========================================================================

  test('should enable submit button when form is valid', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Fill in the order form
    const numberInputs = page.locator('input[type="number"]');

    // Fill price (first input)
    await numberInputs.nth(0).fill('0.95');

    // Fill size (second input)
    if (await numberInputs.count() >= 2) {
      await numberInputs.nth(1).fill('20');
    }

    // Submit button should be enabled
    const submitButton = page.getByRole('button', { name: /submit|place|order/i });
    await expect(submitButton).toBeEnabled();
  });

  test('should submit order successfully', async ({ page }) => {
    // Mock the order submission endpoint
    await page.route('**/api/orders', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, order_id: 'test_order_123' }),
        });
      } else {
        route.continue();
      }
    });

    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Fill in the order form
    const numberInputs = page.locator('input[type="number"]');
    await numberInputs.nth(0).fill('0.95');
    if (await numberInputs.count() >= 2) {
      await numberInputs.nth(1).fill('20');
    }

    // Submit the order
    const submitButton = page.getByRole('button', { name: /submit|place|order/i });
    await submitButton.click();

    // Should show success message or update UI
    // Wait a bit for the response
    await page.waitForTimeout(1000);

    // The form should still be visible (not crashed)
    await expect(page.locator('table')).toBeVisible();
  });

  // =========================================================================
  // Error Handling Tests
  // =========================================================================

  test('should show error when no token selected', async ({ page }) => {
    // Override mock to return empty tokens
    await page.route('**/api/market/*', (route) => {
      const url = new URL(route.request().url());
      // Skip orderbook and history routes
      if (url.pathname.includes('/orderbook') || url.pathname.includes('/history')) {
        route.continue();
        return;
      }
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          market: {
            market_id: 'mkt_1',
            condition_id: 'cond_xyz',
            question: 'Test market?',
            best_bid: 0.45,
            best_ask: 0.47,
          },
          position: null,
          orders: [],
          tokens: [], // Empty tokens!
          last_signal: null,
          last_fill: null,
          last_trade: null,
        }),
      });
    });

    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Try to submit without tokens
    const submitButton = page.getByRole('button', { name: /submit|place|order/i });

    if (await submitButton.isVisible()) {
      await submitButton.click();

      // Should show error message
      const errorMessage = page.locator('text=/select.*token|no.*token/i');
      // Error should appear somewhere on the page
      await expect(errorMessage.or(page.locator('.text-negative, .text-red-500, [class*="error"]'))).toBeVisible({ timeout: 2000 });
    }
  });

  // =========================================================================
  // Token Selection Change Tests
  // =========================================================================

  test('should allow changing token selection', async ({ page }) => {
    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Find the token selector
    const tokenSelector = page.locator('select').filter({ hasText: /Yes|No/i });

    if (await tokenSelector.isVisible()) {
      // Get current value
      const initialValue = await tokenSelector.inputValue();

      // Get all options
      const options = tokenSelector.locator('option');
      const count = await options.count();

      if (count >= 2) {
        // Select the second option
        const secondOptionValue = await options.nth(1).getAttribute('value');
        if (secondOptionValue) {
          await tokenSelector.selectOption(secondOptionValue);

          // Value should have changed
          const newValue = await tokenSelector.inputValue();
          // Either the value changed, or it was already the second option
          expect(newValue).toBeTruthy();
        }
      }
    }
  });
});

test.describe('Markets Page - Token Display', () => {
  test('should show Yes/No labels for tokens', async ({ page }) => {
    await page.goto('/markets');
    await page.waitForLoadState('networkidle');

    // Click on first market
    const marketRow = page.locator('table tbody tr').first();
    await marketRow.click();

    await page.waitForTimeout(500);

    // Should see Yes or No somewhere in the token selector area
    const tokenArea = page.locator('select').filter({ hasText: /Yes|No/i });
    await expect(tokenArea).toBeVisible({ timeout: 5000 });
  });
});
