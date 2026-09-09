import { Page, expect } from '@playwright/test';

export const TEST_USER = {
  username: 'testuser',
  password: 'TestPassword123!',
  displayName: 'Test Operator',
};

/**
 * Authenticates with the pre-seeded Keycloak user and verifies session establishment.
 */
export async function loginAsTestUser(page: Page): Promise<void> {
  await page.goto('/auth/sign-in');
  await page.waitForLoadState('domcontentloaded');

  const emailInput = page.locator('#sign-in-email, input[type="email"], input[placeholder*="operator"]');
  await expect(emailInput).toBeVisible({ timeout: 15000 });
  await emailInput.fill(TEST_USER.username);

  const passwordInput = page.locator('#sign-in-password, input[type="password"]');
  await passwordInput.fill(TEST_USER.password);

  const submitButton = page.locator('#sign-in-submit, [aria-label="Sign In"]');
  await expect(submitButton).toBeEnabled();
  await submitButton.click();

  // Wait for redirect away from /auth/sign-in
  await page.waitForURL((url) => !url.pathname.includes('/auth/sign-in'), { timeout: 20000 });
}
