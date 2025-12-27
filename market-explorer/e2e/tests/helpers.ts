import { Locator, Page } from '@playwright/test';

/**
 * Get the main search input on the Markets page.
 * This targets the input with "(press Enter)" in placeholder to avoid
 * confusion with the global search bar in the Layout.
 */
export function getMarketsSearchInput(page: Page): Locator {
  return page.locator('input[placeholder="Search markets... (press Enter)"]');
}

/**
 * Fill a React controlled input.
 * Uses Playwright's fill() which works correctly when targeting the right element.
 */
export async function fillReactInput(locator: Locator, value: string): Promise<void> {
  await locator.fill(value);
}

/**
 * Helper to fill a React input and press Enter
 */
export async function fillAndSubmit(locator: Locator, value: string): Promise<void> {
  await fillReactInput(locator, value);
  await locator.press('Enter');
}

/**
 * Helper to fill a React input and press Tab (for blur-triggered filters)
 */
export async function fillAndBlur(locator: Locator, value: string): Promise<void> {
  await fillReactInput(locator, value);
  await locator.press('Tab');
}
