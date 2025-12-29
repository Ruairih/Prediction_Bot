import { test as base, expect, type Page } from '@playwright/test';
import { setupApiMocks } from './mocks';

export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use) => {
    await setupApiMocks(page);
    await use(page);
  },
});

export { expect };
