import { expect, test } from '@playwright/test';

test('one-click showcase is complete and reviewable with safety and source evidence', async ({
  page,
}) => {
  await page.goto('/kiosk/language');
  await page.getByTestId('kiosk-load-showcase-btn').click();

  await expect(page).toHaveURL(/\/kiosk\/complete$/);
  await expect(page.getByRole('heading', { name: 'চিকিৎসকের পর্যালোচনার জন্য প্রস্তুত' })).toBeVisible();
  await expect(page.getByText('T-SHOWCASE-101')).toBeVisible();

  await page.goto('/doctor');
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
