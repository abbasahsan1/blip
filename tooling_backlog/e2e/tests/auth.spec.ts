/**
 * T20: Auth flow E2E test
 *
 * Verifies the complete browser -> gateway -> Keycloak -> token -> protected API path.
 *
 * Prerequisites:
 *   - Cluster running (or BASE_URL pointing to a running instance)
 *   - KEYCLOAK_TEST_USER and KEYCLOAK_TEST_PASSWORD env vars set
 *
 * Run with:
 *   BASE_URL=http://100.122.207.32:8419 \
 *   KEYCLOAK_TEST_USER=testuser@blipp.io \
 *   KEYCLOAK_TEST_PASSWORD=testpassword \
 *   npx playwright test e2e/tests/auth.spec.ts
 */

import { test, expect } from '@playwright/test';

const TEST_USER = process.env.KEYCLOAK_TEST_USER || 'testuser@blipp.io';
const TEST_PASSWORD = process.env.KEYCLOAK_TEST_PASSWORD || 'testpassword';

test.describe('Auth flow', () => {
  test('sign in and access protected feed API', async ({ page, request }) => {
    // 1. Navigate to sign-in page
    await page.goto('/auth/sign-in');
    await expect(page).toHaveTitle(/blipp/i, { timeout: 10000 });

    // 2. Fill credentials
    await page.getByLabel(/email/i).fill(TEST_USER);
    await page.getByLabel(/password/i).fill(TEST_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();

    // 3. Assert redirect to feed (authenticated state)
    await expect(page).toHaveURL(/\/(feed|home|index)?$/, { timeout: 15000 });

    // 4. Extract token from localStorage (set by sessionStore)
    const token = await page.evaluate(() => {
      try {
        const raw = localStorage.getItem('blipp-session') || localStorage.getItem('session');
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed?.state?.tokens?.accessToken || parsed?.state?.accessToken || null;
      } catch {
        return null;
      }
    });

    expect(token, 'Access token should be stored in sessionStore after sign-in').toBeTruthy();

    // 5. Call protected API directly with the token
    const feedResponse = await request.get('/v1/feed', {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(feedResponse.status(), 'Protected feed API should return 200 with valid token').toBe(200);

    const feedData = await feedResponse.json();
    expect(feedData).toHaveProperty('items');
  });

  test('unauthenticated request to protected API returns 401', async ({ request }) => {
    const feedResponse = await request.get('/v1/feed');
    // Should be 401 or 403 — not 200
    expect([401, 403]).toContain(feedResponse.status());
  });
});
