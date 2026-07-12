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
  /* Seed the real backend stores once before any spec (full-stack e2e). */
  globalSetup: './e2e/global-setup.ts',
  /* Delete every KB the run created (baseline diff) so e2e can never leave a
     fresh empty KB squatting on newest-ready KB resolution (demo poisoning). */
  globalTeardown: './e2e/global-teardown.ts',
  /* No timeout-based retries in local dev; 2 retries on CI */
  retries: process.env['CI'] ? 2 : 0,
  /*
   * Full-stack e2e runs against ONE shared real backend seeded with a single
   * deterministic scenario (see global-setup.ts). Specs mutate that shared
   * state (promote alert, mark case in review, submit feedback), so they must
   * run serially — parallel execution races on the shared case/alert. This is
   * an intentional trade of wall-clock for determinism, not a port-contention
   * workaround.
   */
  fullyParallel: false,
  workers: 1,
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
