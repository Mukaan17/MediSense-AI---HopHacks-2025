import { defineConfig } from '@playwright/test';

/**
 * E2E smoke against the production build + real backend (degraded LLM mode).
 *
 * The demo and clinical suites need the backend in different modes, so run
 * them as separate invocations:
 *
 *   npx playwright test e2e/demo
 *   APP_MODE=clinical npx playwright test e2e/clinical
 *
 * Prereq: a build pointing at the local backend -
 *   REACT_APP_API_URL=http://localhost:8000 npm run build
 *
 * The chromium binary is expected at PLAYWRIGHT_BROWSERS_PATH (CI installs
 * it with `npx playwright install chromium`); PW_CHROMIUM_PATH overrides the
 * executable for environments with a pre-provisioned browser.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  retries: 0,
  workers: 1, // one shared backend; keep cases serial
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3080',
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
  webServer: [
    {
      command: 'node e2e/serve-build.js',
      port: 3080,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'bash e2e/start-backend.sh',
      port: 8000,
      timeout: 180_000, // model warm-up on first boot
      reuseExistingServer: false,
    },
  ],
});
