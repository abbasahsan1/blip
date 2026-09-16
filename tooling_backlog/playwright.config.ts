import { defineConfig, devices } from '@playwright/test';

// T20: BASE_URL supports three configuration modes:
// 1. Local dev (default):       http://localhost:8419
// 2. LAN/Tailscale (mobile):   set BASE_URL=http://<tailscale-ip>:8419
// 3. CI:                        set BASE_URL=http://<cluster-ingress>
//
// When running dev-mobile.sh, export BASE_URL to the Tailscale/LAN address
// so Playwright tests target the same host as the mobile app.
// Example: BASE_URL=http://100.122.207.32:8419 npx playwright test
const BASE_URL = process.env.BASE_URL || 'http://localhost:8419';

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 60000,
  expect: {
    timeout: 15000,
  },
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
});
