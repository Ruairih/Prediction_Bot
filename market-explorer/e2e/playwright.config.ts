import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Market Explorer E2E tests.
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],

  use: {
    baseURL: 'http://localhost:3004',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Run local dev server before starting the tests */
  webServer: [
    {
      command: 'cd ../backend && uvicorn src.explorer.api.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/health',
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: 'cd ../frontend && npm run dev',
      url: 'http://localhost:3004',
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],

  /* Test timeout */
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
});
