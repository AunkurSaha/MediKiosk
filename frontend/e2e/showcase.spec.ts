import { expect, test } from '@playwright/test';

test('seeded showcase is reviewable with safety and source evidence', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Quick Demo Doctor Login' }).click();
  await expect(page).toHaveURL(/\/doctor/);

  const seeded = await page.evaluate(async () => {
    const response = await fetch('/api/doctor/demo/seed-showcase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    return response.ok;
  });
  expect(seeded).toBe(true);
  await page.reload();
  await expect(page.getByTestId('seed-showcase-btn')).toHaveCount(0);
  await expect(page.getByTestId('reset-demo-btn')).toHaveCount(0);
  const showcase = page.locator('.session-card').filter({ hasText: 'সুমিতা শর্মা' });
  await expect(showcase).toBeVisible();
  await showcase.click();

  await expect(page.getByRole('heading', { name: 'সুমিতা শর্মা' })).toBeVisible();
  await expect(page.getByTestId('doctor-alerts-banner')).toContainText('RF-CHEST-001');
  await expect(page.getByTestId('doctor-alerts-banner')).toContainText('RF-CHEST-002');
  await expect(page.getByTestId('summary-workspace')).toBeVisible();
  await expect(page.getByTestId('document-viewer-panel')).toBeVisible();
  await expect(page.getByTestId('document-image-preview')).toBeVisible();
});
