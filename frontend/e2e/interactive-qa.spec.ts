import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('hands-on golden fever and doctor QA', async ({ browser }) => {
  test.setTimeout(180_000);
  const patientContext = await browser.newContext({
    baseURL: 'http://127.0.0.1:5175',
    viewport: { width: 1366, height: 768 },
  });
  const page = await patientContext.newPage();
  const errors: string[] = [];
  const unauthorized: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    if (response.status() === 401) unauthorized.push(response.url());
  });
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().includes('401 (Unauthorized)'))
      errors.push(message.text());
  });

  await page.goto('/login');
  await page.getByRole('button', { name: 'Use Demo Patient' }).click();
  await expect(page).toHaveURL(/\/kiosk\/language/);
  await page.reload();
  await page.getByRole('button', { name: /English/ }).click();
  await expect(page.getByLabel('Name')).toHaveValue('Demo Patient');
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByTestId('consent-document-checkbox').check();
  await page.getByRole('button', { name: /Start/ }).click();
  await page.getByRole('button', { name: 'Fever', exact: true }).click();
  await page.getByLabel('Answer').fill('38');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: 'Find a suitable facility' }).click();
  await expect(page.getByRole('button', { name: 'Search by locality' })).toBeDisabled();
  await page.getByLabel('Locality').fill('Kolkata');
  await page.getByRole('button', { name: 'Search by locality' }).click();
  await page.getByText('Why this facility?').first().click();
  await expect(page.getByText('Required specialty is available').first()).toBeVisible();
  await page.getByRole('button', { name: 'Select facility' }).first().click();
  const doctor = page.locator('article').filter({ hasText: 'Dr. Ishan Gupta' });
  await doctor.getByText('Why this match?').click();
  await expect(doctor).toContainText('Specialty matches the required care');
  await doctor.getByRole('button', { name: 'Select Doctor' }).click();
  const prescription = await readFile('../ai/document_fixtures/metformin_prescription.png');
  await page
    .getByTestId('document-file-input')
    .setInputFiles({
      name: 'synthetic-metformin-prescription.png',
      mimeType: 'image/png',
      buffer: prescription,
    });
  await expect(page.getByText('Information found in your prescription')).toBeVisible();
  await expect(page.getByText('Metformin', { exact: true })).toBeVisible();
  await expect(page.getByText(/Dose: 500 mg/i)).toBeVisible();
  await expect(page.getByText(/Frequency: twice daily/i)).toBeVisible();
  await page
    .getByRole('textbox', { name: 'Your answer' })
    .fill('Fever since yesterday; no breathing difficulty.');
  await page.getByRole('button', { name: /Save and continue/ }).click();
  await page.getByLabel('Yes').check();
  await page.getByRole('button', { name: /Save and continue/ }).click();
  await expect(page.getByTestId('medication-history-optimized')).toBeVisible();
  const focused: string[] = [];
  for (let turn = 0; turn < 8; turn += 1) {
    const finish = page.getByRole('button', { name: /Save and finish|Finish intake/ });
    const question = page.locator('.question-header h1');
    await expect
      .poll(async () => (await finish.isVisible()) || (await question.isVisible()))
      .toBeTruthy();
    if (await finish.isVisible().catch(() => false)) break;
    await expect(question).toBeVisible();
    focused.push((await question.textContent()) || '');
    expect(focused.at(-1)).not.toMatch(/taking any medicines|names, doses/i);
    const fieldset = page.locator('.question-fields');
    await expect(fieldset).toBeEnabled();
    const number = fieldset.locator('input[type="number"]');
    const textarea = fieldset.locator('textarea');
    const radio = fieldset.locator('input[type="radio"]');
    const checkbox = fieldset.locator('input[type="checkbox"]');
    if (await number.count()) await number.fill('1');
    else if (await textarea.count()) await textarea.fill('No additional concerns.');
    else if (await radio.count()) await radio.first().check();
    else if (await checkbox.count()) await checkbox.first().check();
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes('/interview/answers') && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /Save and continue/ }).click(),
    ]);
  }
  expect(focused).toHaveLength(4);
  expect(focused.join(' ')).not.toMatch(/taking any medicines|names, doses/i);
  await expect(page.getByRole('button', { name: /Save and finish|Finish intake/ })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /Save and finish|Finish intake/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Your pre-consultation intake is ready' }),
  ).toBeVisible();
  await expect(page.getByLabel('Visit queue reservation')).toContainText('Dr. Ishan Gupta');
  await expect(page.getByLabel('Visit queue reservation')).toContainText('Approx. Waiting Time');
  await expect(page.getByLabel('Visit queue reservation')).toContainText(
    'Intake reference: DEMO-FEVER',
  );
  await expect(page.getByLabel('Pre-arrival packet')).toContainText(
    'What will the doctor receive?',
  );
  await page.getByRole('button', { name: 'Show Secure QR' }).click();
  await expect(page.getByLabel('Secure handoff QR')).toBeVisible();
  await expect(page.getByText('Show this QR to authorized clinical staff.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Visit queue reservation')).toContainText(/MK-[A-Z]+-\d{3}/);

  const doctorContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const doctorPage = await doctorContext.newPage();
  doctorPage.on('pageerror', (error) => errors.push(error.message));
  doctorPage.on('response', (response) => {
    if (response.status() === 401) unauthorized.push(response.url());
  });
  await doctorPage.goto('/staff/login');
  await doctorPage
    .getByLabel(/Hospital \/ Facility/)
    .selectOption('10000000-0000-4000-8000-000000000001');
  await doctorPage.getByLabel(/Clinical Specialisation/).selectOption('GENERAL_MEDICINE');
  await doctorPage.getByLabel('Phone Number or Staff ID').fill('9876500012');
  await doctorPage.locator('#staff-password').fill('Doctor@123');
  await doctorPage
    .locator('form')
    .first()
    .getByRole('button', { name: /Sign In|Login|Log In/i })
    .click();
  await expect(doctorPage).toHaveURL(/\/doctor/);
  await doctorPage.getByRole('link', { name: /Demo Patient/ }).click();
  const brief = doctorPage.getByLabel('Pre-Consultation Brief');
  await expect(brief).toContainText('Fever');
  await expect(brief).toContainText('Metformin');
  await expect(brief).toContainText('Patient confirmed');
  await expect(brief).toContainText('No red flags detected');
  await doctorPage.getByRole('button', { name: /Evidence Attribution/ }).click();
  const medication = doctorPage.locator('.evidence-item').filter({ hasText: 'Metformin' }).first();
  await medication.getByText('Why is this here?').click();
  await expect(medication).toContainText('Uploaded prescription');
  await expect(medication).toContainText('Patient verification');
  await doctorPage.reload();
  await expect(doctorPage.getByLabel('Pre-Consultation Brief')).toContainText('Metformin');
  expect(unauthorized.every((url) => url.endsWith('/auth/me'))).toBeTruthy();
  expect(errors).toEqual([]);
  await patientContext.close();
  await doctorContext.close();
});
