import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('camera-ready fever journey preserves prescription provenance end to end', async ({
  browser,
}) => {
  test.setTimeout(360_000);
  const patientContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const page = await patientContext.newPage();
  await page.setViewportSize({ width: 1366, height: 768 });

  await page.goto('/login');
  await page.getByRole('button', { name: 'Continue as patient' }).click();
  await expect(page).toHaveURL(/\/kiosk\/language/, { timeout: 30_000 });
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Planning my visit/ }).click();

  await expect(page.getByLabel('Name')).toHaveValue('Patient');
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByTestId('consent-document-checkbox').check();
  await page.getByRole('button', { name: /Start/ }).click();

  await expect(page.getByRole('heading', { name: 'What brings you here today?' })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Fever', exact: true }).click();
  await page.getByLabel('Answer').fill('38');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await expect(page.getByTestId('rapid-routing-result')).toContainText('GENERAL MEDICINE', {
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Find a suitable facility' }).click();

  await page.getByLabel('Locality').fill('Kolkata');
  await page.getByRole('button', { name: 'Search by locality', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recommended facilities' })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText('Why this facility?').first()).toBeVisible();
  await page.getByText('Why this facility?').first().click();
  await expect(page.getByText('Required specialty is available').first()).toBeVisible();
  await expect(page.getByText('Selected search area: Kolkata')).toBeVisible();
  await page.getByRole('button', { name: 'Select facility' }).first().click();

  await expect(
    page.getByRole('heading', { name: 'Choose a clinically suitable doctor' }),
  ).toBeVisible({ timeout: 30_000 });
  const selectedDoctor = page.locator('article').filter({ hasText: 'Dr. Ishan Gupta' });
  await expect(selectedDoctor).toContainText('GENERAL MEDICINE');
  await expect(selectedDoctor).toContainText('AVAILABLE');
  await expect(selectedDoctor.getByText('Why this match?')).toBeVisible();
  await selectedDoctor.getByText('Why this match?').click();
  await expect(selectedDoctor).toContainText('Specialty matches the required care');
  await expect(selectedDoctor).toContainText('Works at the selected facility');
  await expect(selectedDoctor).toContainText('Available for consultation');
  await selectedDoctor.getByRole('button', { name: 'Select Doctor' }).click();
  await expect(page.getByTestId('document-uploader')).toBeVisible({ timeout: 30_000 });

  const prescription = await readFile('ai/document_fixtures/metformin_prescription.png');
  await page.getByTestId('document-file-input').setInputFiles({
    name: 'metformin-prescription.png',
    mimeType: 'image/png',
    buffer: prescription,
  });
  await expect(page.getByText('Information found in your prescription')).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText('Metformin', { exact: true })).toBeVisible();
  await expect(page.getByText('500 mg', { exact: true })).toBeVisible();
  await expect(page.getByText('Twice Daily', { exact: true })).toBeVisible();

  await page
    .getByRole('textbox', { name: 'Your answer' })
    .fill('Fever since yesterday with chills and body ache.');
  await page.getByRole('button', { name: /Save and continue/ }).click();
  await expect(page.getByTestId('document-confirmation-notice')).toBeVisible();
  await expect(page.getByTestId('document-confirmation-notice')).toContainText(/document/i);
  const sessionId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  expect(sessionId).toBeTruthy();
  const confirmationBefore = await (
    await page.request.get(`/api/sessions/${sessionId}/interview`)
  ).json();
  await page.getByLabel('Yes').check();
  await page.getByRole('button', { name: /Save and continue/ }).click();
  let interview = confirmationBefore;
  await expect
    .poll(async () => {
      interview = await (await page.request.get(`/api/sessions/${sessionId}/interview`)).json();
      return interview.revision;
    })
    .toBeGreaterThan(confirmationBefore.revision);
  while (interview.question?.origin === 'document_confirmation') {
    const response = await page.request.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: interview.revision,
        question_id: interview.question.question_id,
        status: 'answered',
        value: 'yes',
        raw_value: 'yes',
        source: 'touch',
        language: 'en',
      },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    interview = await response.json();
  }
  await page.reload();
  const optimizedHistory = page.getByTestId('medication-history-optimized');
  await expect(optimizedHistory).toBeVisible({ timeout: 15_000 });
  await expect(optimizedHistory).toContainText('History optimized');
  await expect(optimizedHistory).toContainText('Medication confirmed by you');
  await expect(optimizedHistory).toContainText('Medication history is covered');

  const visibleQuestions: string[] = [];
  const visibleQuestionIds: string[] = [];
  for (let turn = 0; !interview.is_complete && turn < 30; turn += 1) {
    visibleQuestions.push(interview.question.text.en);
    visibleQuestionIds.push(interview.question.question_id);
    await expect(page.getByRole('heading', { name: interview.question.text.en })).toBeVisible();
    const previousRevision = interview.revision;
    await page.getByRole('button', { name: 'Prefer not to report' }).click();
    await expect
      .poll(async () => {
        interview = await (await page.request.get(`/api/sessions/${sessionId}/interview`)).json();
        return interview.revision;
      })
      .toBeGreaterThan(previousRevision);
  }
  expect(interview.is_complete).toBe(true);
  expect(visibleQuestionIds).toEqual([
    'hpi.onset',
    'hpi.timing',
    'hpi.associated',
    'past_medical_history.conditions',
    'allergies.any',
    'review_of_systems.details',
  ]);
  expect(visibleQuestions).toHaveLength(6);
  expect(visibleQuestions.join(' ')).not.toMatch(/taking any medicines|names, doses/i);
  expect(visibleQuestionIds).not.toContain('hpi.temperature');
  expect(visibleQuestionIds).not.toContain('hpi.associated_details');
  expect(visibleQuestionIds).not.toContain('hpi.gastrointestinal_details');
  expect(visibleQuestionIds).not.toContain('hpi.urinary_details');
  expect(visibleQuestionIds).not.toContain('hpi.rash_details');
  await page.reload();
  await page.getByRole('button', { name: /Finish/ }).click();

  await expect(
    page.getByRole('heading', { name: 'Your pre-consultation intake is ready' }),
  ).toBeVisible();
  await expect(page.getByLabel('Readiness checklist')).toContainText('Intake completed');
  await expect(page.getByLabel('Readiness checklist')).toContainText('Facility selected');
  await expect(page.getByLabel('Readiness checklist')).toContainText('Doctor selected');
  await expect(page.getByLabel('Readiness checklist')).toContainText(
    'Prescription information reviewed with you',
  );
  await expect(page.getByLabel('Visit queue reservation')).toContainText(/MK-[A-Z]+-\d{3}/);
  await expect(page.getByLabel('Visit queue reservation')).toContainText('Approx. Waiting Time');
  await expect(page.getByLabel('Visit queue reservation')).toContainText(
    'Intake reference: INTAKE-',
  );
  await expect(page.getByLabel('Visit queue reservation')).not.toContainText('Hospital token');
  await expect(page.getByLabel('Pre-arrival packet')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Your Pre-Arrival Packet' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Show Secure QR' })).toBeVisible();
  await expect(page.getByText('What will the doctor receive?')).toBeVisible();
  await expect(
    page.getByText(/medical information is not embedded directly in the QR/i),
  ).toBeVisible();
  await expect(page.locator('.completion')).not.toContainText(sessionId!);
  const qrActionBottom = await page
    .getByRole('button', { name: 'Show Secure QR' })
    .evaluate((element) => element.getBoundingClientRect().bottom);
  expect(qrActionBottom).toBeLessThan(768);
  await page.getByRole('button', { name: 'Show Secure QR' }).click();
  await expect(page.getByLabel('Secure handoff QR')).toBeVisible();
  await expect(page.getByText('Show this QR to authorized clinical staff.')).toBeVisible();

  const doctorContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const doctorPage = await doctorContext.newPage();
  const login = await doctorPage.request.post('/api/auth/staff-login', {
    data: {
      identifier: '9876500012',
      password: 'Doctor@123',
      hospital_id: '10000000-0000-4000-8000-000000000001',
      specialty: 'GENERAL_MEDICINE',
    },
  });
  expect(login.ok()).toBeTruthy();
  await doctorPage.goto('/doctor');
  await doctorPage.locator(`a[href="/doctor/sessions/${sessionId}"]`).click();
  await doctorPage.waitForURL(`**/doctor/sessions/${sessionId}`);
  await expect(
    doctorPage.locator('.patient-heading').getByRole('heading', { name: 'Patient' }),
  ).toBeVisible();
  const brief = doctorPage.getByLabel('Pre-Consultation Brief');
  await expect(brief).toBeVisible();
  await expect(brief).toContainText('Fever');
  await expect(brief).toContainText('Azithromycin');
  await expect(brief).toContainText('Patient confirmed');
  await expect(brief).toContainText('No red flags detected');
  await expect(brief).toContainText(/MK-[A-Z]+-\d{3}/);
  await expect(brief).toContainText('Approx. waiting time');
  const medicationCard = doctorPage.locator('.medical-fact-card', {
    has: doctorPage.getByRole('heading', { name: 'Racecadotril', exact: true }),
  });
  await expect(medicationCard).toBeVisible();
  await expect(medicationCard).toContainText('100 mg');
  await expect(medicationCard).toContainText(/TDS/i);
  await expect(doctorPage.getByRole('button', { name: /Evidence Attribution/ })).toBeVisible();
  await doctorPage.getByRole('button', { name: /Evidence Attribution/ }).click();
  const medicationEvidence = doctorPage
    .locator('.evidence-item')
    .filter({ hasText: 'Racecadotril' })
    .filter({ hasText: 'Prescription' });
  await expect(medicationEvidence.first()).toBeVisible();
  await medicationEvidence.first().getByText('Why is this here?').click();
  await expect(medicationEvidence.first()).toContainText('Uploaded prescription');
  await expect(medicationEvidence.first()).toContainText('Information extracted');
  await expect(medicationEvidence.first()).toContainText('Patient verification');
  await expect(medicationEvidence.first()).toContainText('Current medication');
  await expect(medicationEvidence.first()).toContainText(/prescription|document/i);
  await expect(medicationEvidence.first()).toContainText(/patient confirmed|confirmed/i);

  await doctorContext.close();
  await patientContext.close();
});
