import { expect, test } from '@playwright/test';

test('on-site chest red flag keeps current hospital and bypasses routine routing', async ({
  page,
}) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Use Demo Patient' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Already at a hospital/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Which hospital are you currently at?' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /MediKiosk City Hospital/ }).click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: /Start/ }).click();

  await page.getByRole('button', { name: 'Chest discomfort', exact: true }).click();
  await page.getByLabel('Answer').fill('9');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(page.getByText('Potential emergency symptoms detected.')).toBeVisible();
  await page.getByRole('button', { name: /Get immediate help at this hospital/ }).click();

  await expect(page).toHaveURL(/\/kiosk\/emergency/);
  await expect(page.getByTestId('on-site-emergency-facility')).toContainText(
    'MediKiosk City Hospital',
  );
  await expect(
    page.getByText(/seek immediate assistance from the clinical or triage team/i),
  ).toBeVisible();
  await expect(page.getByLabel('Locality')).toHaveCount(0);
  await expect(page.getByText(/Choose a clinically suitable doctor/i)).toHaveCount(0);
  await expect(page.getByLabel('Visit queue reservation')).toHaveCount(0);

  const sessionId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  const rapid = await page.request.get(`/api/sessions/${sessionId}/rapid-routing`);
  expect(rapid.ok()).toBeTruthy();
  expect((await rapid.json()).result.triggered_red_flags).toContain('RF-CHEST-001');
});
