import { test, expect } from '@playwright/test';
import { loginAsTestUser, TEST_USER } from '../helpers/auth';

test.describe('Authentication & Session Initialization', () => {
  test('should display validation errors or failure on invalid credentials', async ({ page }) => {
    await page.goto('/auth/sign-in');
    await page.waitForLoadState('domcontentloaded');

    const emailInput = page.locator('#sign-in-email, input[type="email"], input[placeholder*="operator"]');
    await expect(emailInput.first()).toBeVisible({ timeout: 15000 });
    await emailInput.first().fill(TEST_USER.username);

    const passwordInput = page.locator('#sign-in-password, input[type="password"]');
    await passwordInput.first().fill('WrongPassword999!');

    const submitButton = page.locator('#sign-in-submit, [aria-label="Sign In"]');
    await submitButton.first().click();

    // Verify error banner is rendered
    const errorBanner = page.locator('[role="alert"]').or(page.getByText(/invalid|failed|unauthorized/i));
    await expect(errorBanner.first()).toBeVisible({ timeout: 10000 });
  });

  test('should sign in successfully with seeded credentials and display profile', async ({ page }) => {
    await loginAsTestUser(page);

    // Verify user is in main app tabs
    await expect(page).toHaveURL(/\/(tabs)?/);

    // Navigate to Profile tab
    const profileTab = page.locator('div[role="tab"], a[role="tab"]').filter({ hasText: /profile/i }).or(page.getByLabel(/profile/i));
    await profileTab.first().click();

    // Verify operator handle / display name appears
    const profileHandle = page.locator('[data-testid="profile-username"]').or(page.getByText('@testuser')).or(page.getByText('testuser'));
    await expect(profileHandle.first()).toBeVisible({ timeout: 10000 });
  });
});
