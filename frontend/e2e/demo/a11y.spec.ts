import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Automated accessibility gate (axe-core) over the main views. Critical
 * violations fail the build; serious ones are reported in the test output
 * so regressions are visible in review.
 */

async function scan(page: import('@playwright/test').Page) {
  return new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
}

test.describe('accessibility', () => {
  test('input view has no critical violations', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Clinical AI Assistant' })).toBeVisible();
    await expect(page.getByText('Select from EHR Patients')).toBeVisible({ timeout: 30_000 });

    const results = await scan(page);
    const critical = results.violations.filter((v) => v.impact === 'critical');
    const serious = results.violations.filter((v) => v.impact === 'serious');
    for (const v of serious) {
      console.log(`[a11y serious] ${v.id}: ${v.help} (${v.nodes.length} nodes)`);
    }
    expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
  });

  test('results view has no critical violations', async ({ page }) => {
    await page.goto('/');
    await page
      .getByLabel('Clinical notes')
      .fill('persistent cough and high fever for three days');
    await page.getByRole('button', { name: /Quick Analysis/ }).click();
    await expect(page.getByRole('heading', { name: 'Clinical Analysis Results' }))
      .toBeVisible({ timeout: 60_000 });

    const results = await scan(page);
    const critical = results.violations.filter((v) => v.impact === 'critical');
    expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
  });
});
