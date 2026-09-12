import { expect, test } from '@playwright/test';

test('one-click showcase is complete and reviewable with safety and source evidence', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Quick Demo Doctor Login' }).click();
  await expect(page).toHaveURL(/\/doctor/);

  const seedBtn = page.getByTestId('seed-showcase-btn');
  await expect(seedBtn).toBeVisible();
  await seedBtn.click();
  await expect(page.getByText(/Showcase patient.*seeded successfully/)).toBeVisible();
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
