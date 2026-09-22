import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('on-site fever intake skips MediRoute and reaches the assigned doctor queue', async ({
  browser,
}) => {
  test.setTimeout(process.env.MEDIKIOSK_SUPABASE_DEMO_QA === '1' ? 300_000 : 120_000);
  const patient = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const page = await patient.newPage();
  await page.goto('/login');
  await page.getByRole('button', { name: 'Use Demo Patient' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Already at a hospital/ }).click();
  await page.getByRole('button', { name: /MediKiosk City Hospital/ }).click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByTestId('consent-document-checkbox').check();
  await page.getByRole('button', { name: /Start/ }).click();
  await page.getByRole('button', { name: 'Fever', exact: true }).click();
  await page.getByLabel('Answer').fill('38');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: /Continue with this hospital/ }).click();

  await expect(page).toHaveURL(/\/kiosk\/doctor/);
  await expect(page.getByLabel('Locality')).toHaveCount(0);
  await expect(page.getByTestId('on-site-facility-context')).toContainText(
    'MediKiosk City Hospital',
  );
  await expect(page.getByTestId('on-site-facility-context')).toContainText(
    'hospital search skipped',
  );
  const selectedDoctor = page.locator('article').filter({ hasText: 'Dr. Ishan Gupta' });
  await selectedDoctor.getByRole('button', { name: 'Select Doctor' }).click();

  const prescription = await readFile('../ai/document_fixtures/metformin_prescription.png');
  await page.getByTestId('document-file-input').setInputFiles({
    name: 'metformin_prescription.png',
    mimeType: 'image/png',
    buffer: prescription,
  });
  await expect(page.getByText('Metformin', { exact: true })).toBeVisible({ timeout: 60000 });
  await page.getByRole('textbox', { name: 'Your answer' }).fill('Fever since yesterday.');
  await page.getByRole('button', { name: /Save and continue/ }).click();
  await page.getByLabel('Yes').check();
  await page.getByRole('button', { name: /Save and continue/ }).click();
  await expect(page.getByTestId('medication-history-optimized')).toBeVisible();

  const sessionId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  expect(sessionId).not.toBeNull();
  let interview = await (await page.request.get(`/api/sessions/${sessionId}/interview`)).json();
  for (let turn = 0; !interview.is_complete && turn < 30; turn += 1) {
    const response = await page.request.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: interview.revision,
        question_id: interview.question.question_id,
        status: 'not_reported',
        value: null,
        raw_value: 'Prefer not to report',
        source: 'touch',
        language: 'en',
      },
    });
    expect(response.ok()).toBeTruthy();
    interview = await response.json();
  }
  expect(interview.is_complete).toBe(true);
  await page.reload();
  await page.getByRole('button', { name: /Finish/ }).click();
  await expect(page.getByRole('heading', { name: 'Your hospital intake is ready' })).toBeVisible();
  await expect(page.getByLabel('Visit queue reservation')).toContainText(/MK-[A-Z]+-\d{3}/);

  const doctor = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const doctorPage = await doctor.newPage();
  expect(
    (
      await doctorPage.request.post('/api/auth/staff-login', {
        data: {
          identifier: '9876500012',
          password: 'Doctor@123',
          hospital_id: '10000000-0000-4000-8000-000000000001',
          specialty: 'GENERAL_MEDICINE',
        },
      })
    ).ok(),
  ).toBeTruthy();
  await doctorPage.goto('/doctor');
  await doctorPage.locator(`a[href="/doctor/sessions/${sessionId}"]`).click();
  await expect(doctorPage.getByTestId('journey-mode-badge')).toHaveText('On-site');
  await expect(doctorPage.getByLabel('Pre-Consultation Brief')).toContainText('Metformin');
  await doctor.close();
  await patient.close();
});
