/**
 * Flow 3: Login sign-in redirect
 *
 * Verifies that clicking "Sign in" on the /login page triggers a browser
 * navigation to the OAuth endpoint: /api/auth/login.
 *
 * The Login component (src/pages/Login.tsx) uses:
 *   window.location.assign(`${API_BASE_URL}/auth/login`)
 * where API_BASE_URL defaults to "/api". This is a full-browser navigation,
 * not a fetch() call, so it cannot be observed via page.waitForRequest.
 * Instead, we:
 *   1. Register a page.route() handler that fulfills the auth/login request
 *      with a 200 response so the browser does not get a 502.
 *   2. Click the "Sign in" button.
 *   3. Assert the browser URL changes to the auth endpoint.
 *
 * Source verified against:
 *   Login component: src/pages/Login.tsx
 *   API_BASE_URL: src/lib/apiClient.ts (defaults to "/api")
 */

import { test, expect } from '@playwright/test'

const AUTH_LOGIN_URL = 'http://localhost:5173/api/auth/login'

test.describe('Login sign-in redirect', () => {
  test('clicking Sign in navigates to the OAuth endpoint', async ({ page }) => {
    // Route the OAuth endpoint so the browser gets a response instead of 502.
    // In production this would be a redirect to an OAuth provider; here we
    // return 200 to allow waitForURL to resolve without a navigation error.
    await page.route(AUTH_LOGIN_URL, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html><body>OAuth stub</body></html>',
      })
    })

    await page.goto('/login')

    // Login page renders: heading, subtitle, sign-in button.
    await expect(page.getByRole('heading', { name: 'chiliAI' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()

    // Clicking triggers window.location.assign('/api/auth/login').
    await Promise.all([
      page.waitForURL(AUTH_LOGIN_URL),
      page.getByRole('button', { name: 'Sign in' }).click(),
    ])

    // Browser navigated to the OAuth endpoint.
    await expect(page).toHaveURL(AUTH_LOGIN_URL)
  })
})
