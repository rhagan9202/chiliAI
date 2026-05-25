import { test, expect } from '@playwright/test'

/**
 * Smoke tests — verify the app shell renders and the unauthenticated
 * redirect path works correctly. These tests exercise the static React
 * bundle; they do NOT require the backend API to be running.
 *
 * The unauthenticated flow: any protected route -> redirect to /login.
 * The login page renders purely from static HTML/CSS/JS.
 */

const AUTH_ME_URL = 'http://localhost:5173/api/auth/me'

test.describe('App smoke', () => {
  test('root redirects unauthenticated users to /login', async ({ page }) => {
    // Force unauthenticated: intercept /auth/me and return 401 so the test
    // is deterministic whether or not a real backend is running on :8000.
    // Without this, the AuthGuard sees a real authenticated session and
    // never redirects to /login.
    await page.route(AUTH_ME_URL, (route) => {
      void route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: '{"detail":"Unauthorized"}',
      })
    })

    await page.goto('/')

    // AuthGuard detects unauthenticated session and redirects to /login.
    // Wait for navigation to settle.
    await expect(page).toHaveURL('/login')
  })

  test('login page renders the sign-in card with expected elements', async ({ page }) => {
    await page.goto('/login')

    // The Login component renders a <main class="login-page"> containing
    // an h1 with the product name and a sign-in button.
    await expect(page.getByRole('heading', { name: 'chiliAI' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByText('Please sign in to continue.')).toBeVisible()
  })
})
