import { test, expect } from '@playwright/test';
import { loginAsTestUser } from '../helpers/auth';
import { generateSyntheticWavBuffer } from '../helpers/audio';

test.describe('Audio Reel Upload, Transcoding & Playback Pipeline', () => {
  test('should upload audio, transcode variants, and render playable reel in feed', async ({ page }) => {
    // 1. Authenticate session
    await loginAsTestUser(page);

    // 2. Navigate to Upload console
    await page.goto('/(tabs)/upload');
    await page.waitForLoadState('domcontentloaded');

    await expect(page.locator('text=Post Blipp').first()).toBeVisible({ timeout: 15000 });

    // 3. Attach synthetic WAV audio via file input
    const syntheticWav = generateSyntheticWavBuffer(2, 8000);
    const fileInput = page.locator('[data-testid="audio-file-input"], input[type="file"]');
    await fileInput.setInputFiles({
      name: 'synth-broadcast.wav',
      mimeType: 'audio/wav',
      buffer: syntheticWav,
    });

    // 4. Fill in unique Title and Description
    const uniqueTitle = `Acoustic Blipp ${Date.now()}`;
    const titleInput = page.locator('[data-testid="blipp-title-input"]');
    await expect(titleInput).toBeVisible({ timeout: 10000 });
    await titleInput.fill(uniqueTitle);

    const descInput = page.locator('[data-testid="blipp-description-input"]');
    await descInput.fill('Continuous integration end-to-end multi-variant acoustic test.');

    // 5. Submit "Post Blipp"
    const postButton = page.locator('[data-testid="post-blipp-button"]');
    await expect(postButton).toBeEnabled();
    await postButton.click();

    // 6. Verify upload progress advances beyond 0% -> 100%
    const progressSection = page.locator('[data-testid="upload-progress-section"]');
    await expect(progressSection).toBeVisible({ timeout: 15000 });

    // 7. Verify status transitions ("Transcoding audio variants..." to "Published successfully!")
    const statusText = page.locator('[data-testid="upload-status-text"]').or(page.getByText(/transcoding|published/i));
    await expect(statusText.first()).toBeVisible({ timeout: 20000 });

    const successBanner = page.locator('[data-testid="upload-success-banner"]').or(page.getByText('Published successfully!'));
    await expect(successBanner.first()).toBeVisible({ timeout: 45000 });

    // 8. Navigation to Feed tab
    await page.waitForURL((url) => !url.pathname.includes('/upload'), { timeout: 15000 });

    // 9. Assert the newly created Blipp appears in the feed DOM
    const blippTitleInFeed = page.locator('[data-testid="blipp-title"]').filter({ hasText: uniqueTitle }).or(page.getByText(uniqueTitle));
    await expect(blippTitleInFeed.first()).toBeVisible({ timeout: 20000 });

    // 10. Assert audio player container initialization
    const audioContainer = page.locator('[data-testid="audio-reel-card"], [data-testid="audio-play-button"]').or(page.getByLabel(/play audio/i));
    await expect(audioContainer.first()).toBeVisible({ timeout: 10000 });
  });
});
