/**
 * Screenshot all pages for visual review
 */
import { test, expect } from '@playwright/test';

const pages = [
  { path: '/', name: 'overview' },
  { path: '/positions', name: 'positions' },
  { path: '/markets', name: 'markets' },
  { path: '/pipeline', name: 'pipeline' },
  { path: '/strategy', name: 'strategy' },
  { path: '/performance', name: 'performance' },
  { path: '/risk', name: 'risk' },
  { path: '/activity', name: 'activity' },
  { path: '/system', name: 'system' },
  { path: '/settings', name: 'settings' },
];

test.describe('Screenshot All Pages', () => {
  for (const page of pages) {
    test(`capture ${page.name} page`, async ({ page: p }) => {
      await p.goto(page.path);
      await p.waitForLoadState('networkidle');
      await p.waitForTimeout(1000);

      // Disable animations for consistent screenshots
      await p.addStyleTag({
        content: `*, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
        }`
      });
      await p.waitForTimeout(100);

      await p.screenshot({
        path: `/tmp/dashboard-${page.name}.png`,
        fullPage: false
      });
    });
  }
});
