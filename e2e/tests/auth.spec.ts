import { test, expect } from '@playwright/test';
import { loginAsTestUser, TEST_USER } from '../helpers/auth';

test.describe('Authentication & Session Initialization', () => {
  test('should display validation errors or failure on invalid credentials', async ({ page }) => {
    await page.goto('/auth/sign-in');
    await page.waitForLoadState('domcontentloaded');

    const emailInput = page.locator('#sign-in-email');
    await expect(emailInput).toBeVisible({ timeout: 15000 });
    await emailInput.fill(TEST_USER.username);

    const passwordInput = page.locator('#sign-in-password');
    await passwordInput.fill('WrongPassword999!');

    const submitButton = page.locator('#sign-in-submit');
    await submitButton.click();

    // Verify error banner is rendered
    const errorBanner = page.locator('[role="alert"], text=Invalid, text=failed, text=Unauthorized');
    await expect(errorBanner.first()).toBeVisible({ timeout: 10000 });
  });

  test('should sign in successfully with seeded credentials and display profile', async ({ page }) => {
    await loginAsTestUser(page);

    // Verify user is in main app tabs
    await expect(page).toHaveURL(/\/(tabs)?/);

    // Navigate to Profile tab
    const profileTab = page.locator('div[role="tab"]:has-text("Profile"), [aria-label*="Profile"], text=Profile').first();
    await profileTab.click();

    // Verify operator handle / display name appears
    const profileHandle = page.locator('[data-testid="profile-username"], text=@testuser, text=testuser');
    await expect(profileHandle.first()).toBeVisible({ timeout: 10000 });
  });
});
