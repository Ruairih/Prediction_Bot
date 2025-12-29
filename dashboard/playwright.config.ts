import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Test Configuration
 *
 * Run with: npm run test:e2e
 * Visual UI: npm run test:e2e:ui
 */
const enableMobile = process.env.PLAYWRIGHT_MOBILE === 'true';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    ...(enableMobile
      ? [
          {
            name: 'mobile',
            use: { ...devices['iPhone 13'] },
          },
        ]
      : []),
  ],

  // Run dev server before tests
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
    env: {
      VITE_HOST: '127.0.0.1',
    },
  },
});
