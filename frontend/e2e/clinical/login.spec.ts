import { test, expect } from '@playwright/test';

// Run with: APP_MODE=clinical npx playwright test e2e/clinical
// (start-backend.sh provisions the e2edoc/E2e-pass-123 test user)

test.describe('clinical mode', () => {
  test('forces login, rejects bad credentials, accepts good ones', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Clinical mode requires authentication.')).toBeVisible({
      timeout: 30_000,
    });

    // Demo-only toggles must be hidden in clinical posture
    await expect(page.getByText('Demo mode · synthetic data')).toHaveCount(0);

    await page.getByPlaceholder('Username').fill('e2edoc');
    await page.getByPlaceholder('Password').fill('wrong-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    // Modal stays up on failure
    await expect(page.getByText('Clinical mode requires authentication.')).toBeVisible();

    await page.getByPlaceholder('Password').fill('E2e-pass-123');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Clinical mode requires authentication.')).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.getByText('Clinical mode', { exact: true })).toBeVisible();

    // Cookie sessions: no token may ever land in localStorage (XSS surface).
    const storedToken = await page.evaluate(() => localStorage.getItem('medisense_token'));
    expect(storedToken).toBeNull();
    const cookies = await page.context().cookies();
    const session = cookies.find((c) => c.name === 'medisense_session');
    expect(session?.httpOnly).toBe(true);

    // The session survives a reload without re-login.
    await page.reload();
    await expect(page.getByText('Clinical mode', { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Clinical mode requires authentication.')).toHaveCount(0);
  });
});
