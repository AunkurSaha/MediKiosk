import { expect, test } from '@playwright/test';

test('synthetic chest-pain case follows deterministic emergency pathway', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Continue as patient' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Planning my visit/ }).click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByRole('button', { name: /Start/ }).click();

  await page.getByRole('button', { name: 'Chest discomfort' }).click();
  await page.getByLabel('Answer').fill('9');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: 'Yes', exact: true }).click();

  const result = page.getByTestId('rapid-routing-result');
  await expect(result).toContainText('Potential emergency symptoms detected.');
  await expect(result).toContainText('Immediate clinical assessment recommended');
  await expect(result).toContainText('deterministic clinical safety rule');
  await expect(result).toContainText('Clinical safety alert recorded for triage');
  await expect(result).toContainText(
    'Routine doctor matching and the normal queue pathway are paused',
  );
  await expect(
    result.getByRole('button', { name: 'Find emergency-capable facilities' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Find a suitable facility' })).toHaveCount(0);
  await expect(page.getByText(/visit token|Approx. Waiting Time/i)).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Your pre-consultation intake is ready' }),
  ).toHaveCount(0);
  const sessionId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  expect(sessionId).toBeTruthy();
  const state = await page.request.get(`/api/sessions/${sessionId}/rapid-routing`);
  expect(state.ok()).toBeTruthy();
  expect((await state.json()).result.triggered_red_flags).toContain('RF-CHEST-001');
});
