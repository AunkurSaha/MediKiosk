import { expect, test } from '@playwright/test';

test('low-severity chest discomfort stays on the routine path', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Use Demo Patient' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: /Start/ }).click();
  await page.getByRole('button', { name: 'Chest discomfort' }).click();
  await page.getByLabel('Answer').fill('2');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  const result = page.getByTestId('rapid-routing-result');
  await expect(result).not.toContainText('Potential emergency symptoms detected');
  await expect(result.getByRole('button', { name: 'Find a suitable facility' })).toBeVisible();
  await expect(
    result.getByRole('button', { name: 'Find emergency-capable facilities' }),
  ).toHaveCount(0);
});
