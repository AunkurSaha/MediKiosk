import { expect, test } from '@playwright/test';

test('live emergency alert reaches authenticated triage and can be acknowledged', async ({ browser }) => {
  test.setTimeout(90_000);
  const triageContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175', viewport: { width: 1366, height: 768 } });
  const triagePage = await triageContext.newPage();
  await triagePage.goto('/staff/login');
  await triagePage.getByRole('button', { name: /Triage:.*Sister Priya/ }).click();
  await triagePage.getByRole('button', { name: 'Sign In to Staff Workspace' }).click();
  await expect(triagePage).toHaveURL(/\/triage/);
  await triagePage.getByRole('button', { name: /MediKiosk City Hospital/ }).click();
  await expect(triagePage.locator('.ws-indicator.connected')).toBeVisible();

  const patientContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175', viewport: { width: 1366, height: 768 } });
  const patientPage = await patientContext.newPage();
  await patientPage.goto('/login');
  await patientPage.getByRole('button', { name: 'Use Demo Patient' }).click();
  await patientPage.getByRole('button', { name: /English/ }).click();
  await patientPage.getByRole('button', { name: /Continue/ }).click();
  await patientPage.locator('input[type="checkbox"]').first().check();
  await patientPage.getByRole('button', { name: /Start/ }).click();
  await patientPage.getByRole('button', { name: 'Chest discomfort' }).click();
  await patientPage.getByLabel('Answer').fill('9');
  await patientPage.getByRole('button', { name: 'Continue' }).click();
  await patientPage.getByRole('button', { name: 'No', exact: true }).click();
  await patientPage.getByRole('button', { name: 'Yes', exact: true }).click();
  await expect(patientPage.getByTestId('rapid-routing-result')).toContainText('Potential emergency symptoms detected.');
  const sessionId = await patientPage.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  const state = await patientPage.request.get(`/api/sessions/${sessionId}/rapid-routing`);
  expect((await state.json()).result.triggered_red_flags).toContain('RF-CHEST-001');
  await expect(triagePage.locator('.alert-card').filter({ hasText: 'Demo Patient' })).toBeVisible();
});
