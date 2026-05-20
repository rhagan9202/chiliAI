import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright e2e configuration for chiliAI frontend.
 *
 * Tests live in e2e/. The webServer block starts the Vite dev server
 * automatically if it is not already running on :5173.
 *
 * Run: npm run test:e2e
 * UI mode: npm run test:e2e:ui
 */
export default defineConfig({
  testDir: './e2e',
  /* No timeout-based retries in local dev; 2 retries on CI */
  retries: process.env['CI'] ? 2 : 0,
  /* Run tests serially in CI to avoid port contention */
  workers: process.env['CI'] ? 1 : undefined,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://localhost:5173',
    /* Collect trace on first retry so failures are diagnosable in CI */
    trace: 'on-first-retry',
    /* No screenshots by default; turn on for flaky-test investigation */
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  /* Start Vite dev server before tests if nothing is already listening on :5173 */
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
  outputDir: 'test-results',
})
