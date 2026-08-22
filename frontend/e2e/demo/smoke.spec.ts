import { test, expect } from '@playwright/test';

test.describe('demo mode', () => {
  test('boots with the demo banner and EHR patients', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Clinical AI Assistant' })).toBeVisible();
    await expect(page.getByText('Demo mode · synthetic data')).toBeVisible();
    // This environment has no LLM keys: degradation must be visible, not silent.
    await expect(page.getByText(/AI assistance degraded/)).toBeVisible({ timeout: 15_000 });
    // Truth-in-UI: the app must never claim sources the deployment lacks.
    await expect(page.getByText('UpToDate')).toHaveCount(0);
    // EHR selector proves the frontend reached the backend and demo data loaded
    await expect(page.getByText('Select from EHR Patients')).toBeVisible({ timeout: 30_000 });
    const options = page.locator('select.input-field option');
    await expect
      .poll(async () => options.count(), { timeout: 15_000 })
      .toBeGreaterThan(1);
  });

  test('quick analysis produces a results view (degraded LLM)', async ({ page }) => {
    await page.goto('/');
    await page
      .getByPlaceholder('Enter patient symptoms, history, or clinical findings...')
      .fill('persistent cough and high fever for three days\nshortness of breath at night');
    const analyze = page.getByRole('button', { name: /Quick Analysis/ });
    await expect(analyze).toBeEnabled();
    await analyze.click();
    // Degraded mode (no LLM keys): retrieval + fusion still produce a report.
    await expect(page.getByRole('heading', { name: 'Clinical Analysis Results' }))
      .toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole('heading', { name: 'Recommendations' })).toBeVisible();
    // Back to a clean input view
    await page.getByRole('button', { name: 'New Case' }).click();
    await expect(page.getByRole('button', { name: /Quick Analysis/ })).toBeVisible();
  });
});
