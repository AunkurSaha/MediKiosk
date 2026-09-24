import { expect, test, type Browser, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const hospitalId = '10000000-0000-4000-8000-000000000001';

async function startOnSitePatient(browser: Browser, patientName: string) {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:5175',
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  await page.goto('/login');
  await page.getByRole('button', { name: 'Continue as patient' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByRole('button', { name: /Already at a hospital/ }).click();
  await page.getByRole('button', { name: /MediKiosk City Hospital/ }).click();
  await page.getByLabel('Name').fill(patientName);
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('input[type="checkbox"]').first().check();
  await page.getByTestId('consent-document-checkbox').check();
  await page.getByRole('button', { name: /Start/ }).click();
  await page.getByRole('button', { name: 'Fever', exact: true }).click();
  await page.getByLabel('Answer').fill('38');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'No', exact: true }).click();
  await page.getByRole('button', { name: /Continue with this hospital/ }).click();
  const doctor = page.locator('article').filter({ hasText: 'Dr. Ishan Gupta' });
  await doctor.getByRole('button', { name: 'Select Doctor' }).click();
  const sessionId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  expect(sessionId).not.toBeNull();
  return { context, page, sessionId: sessionId! };
}

async function loginAssignedDoctor(browser: Browser) {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:5175',
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  const login = await page.request.post('/api/auth/staff-login', {
    data: {
      identifier: '9876500012',
      password: 'Doctor@123',
      hospital_id: hospitalId,
      specialty: 'GENERAL_MEDICINE',
    },
  });
  expect(login.ok()).toBeTruthy();
  return { context, page };
}

async function completeInterviewThroughPersistedAnswers(
  page: Page,
  sessionId: string,
  overrides: Record<string, { value: unknown; raw: string }> = {},
) {
  let interview = await (await page.request.get(`/api/sessions/${sessionId}/interview`)).json();
  const seen = new Set<string>();
  for (let turn = 0; !interview.is_complete && turn < 100; turn += 1) {
    const question = interview.question;
    expect(question).toBeTruthy();
    seen.add(question.field);
    const override = overrides[question.field];
    const response = await page.request.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: override
        ? {
            request_id: crypto.randomUUID(),
            expected_revision: interview.revision,
            question_id: question.question_id,
            status: 'answered',
            value: override.value,
            raw_value: override.raw,
            source: 'touch',
            language: 'en',
          }
        : {
            request_id: crypto.randomUUID(),
            expected_revision: interview.revision,
            question_id: question.question_id,
            status: 'not_reported',
            value: null,
            raw_value: 'Prefer not to report',
            source: 'touch',
            language: 'en',
          },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    interview = await response.json();
  }
  expect(interview.is_complete).toBe(true);
  return seen;
}

async function searchInDoctorUI(page: Page, sessionId: string, query: string) {
  await page.goto(`/doctor/sessions/${sessionId}`);
  const panel = page.getByLabel('Patient clinical evidence search');
  await expect(panel.getByRole('heading', { name: 'Clinical Evidence Search' })).toBeVisible();
  await panel.getByLabel('Evidence search query').fill(query);
  await panel.getByRole('button', { name: 'Search evidence' }).click();
  await expect(panel.getByTestId('patient-evidence-results')).toBeVisible();
  return panel;
}

test('real Supabase patient intake reaches assigned-doctor evidence search with isolation', async ({
  browser,
}) => {
  test.setTimeout(600_000);

  const patientA = await startOnSitePatient(browser, 'RAG E2E Metformin Patient A');
  const prescription = await readFile('../ai/document_fixtures/metformin_prescription.png');
  await patientA.page.getByTestId('document-file-input').setInputFiles({
    name: 'rag-e2e-metformin-prescription.png',
    mimeType: 'image/png',
    buffer: prescription,
  });
  await expect(patientA.page.getByText('Metformin', { exact: true })).toBeVisible({
    timeout: 60_000,
  });

  const doctor = await loginAssignedDoctor(browser);
  const beforeConfirmation = await doctor.page.request.post(
    `/api/doctor/sessions/${patientA.sessionId}/evidence-search`,
    { data: { query: 'What medications are currently confirmed?', top_k: 10 } },
  );
  expect(beforeConfirmation.ok(), await beforeConfirmation.text()).toBeTruthy();
  const beforeBody = await beforeConfirmation.json();
  expect(beforeBody.answer).toMatch(/Metformin 500 mg twice daily/i);
  expect(beforeBody.answer).toContain('remains unverified');
  expect(
    beforeBody.evidence.some(
      (item: { verification_status: string }) => item.verification_status === 'UNVERIFIED',
    ),
  ).toBeTruthy();

  await patientA.page.getByRole('textbox', { name: 'Your answer' }).fill('Fever since yesterday.');
  await patientA.page.getByRole('button', { name: /Save and continue/ }).click();
  await patientA.page.getByLabel('Yes').check();
  await patientA.page.getByRole('button', { name: /Save and continue/ }).click();
  await expect(patientA.page.getByTestId('medication-history-optimized')).toBeVisible();
  await completeInterviewThroughPersistedAnswers(patientA.page, patientA.sessionId);
  expect(
    (await patientA.page.request.post(`/api/sessions/${patientA.sessionId}/complete`)).ok(),
  ).toBeTruthy();
  await patientA.page.goto('/kiosk/complete');
  await expect(
    patientA.page.getByRole('heading', { name: 'Your hospital intake is ready' }),
  ).toBeVisible();

  const medicationPanel = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    'Show medication evidence',
  );
  await expect(medicationPanel).toContainText(/Metformin 500 mg twice daily/i);
  await expect(medicationPanel).toContainText('patient-confirmed');
  await expect(medicationPanel).toContainText('Supporting Evidence');
  await medicationPanel.getByText('Why is this here?').first().click();
  await expect(medicationPanel).toContainText('Original document evidence');
  await expect(medicationPanel).toContainText('Confirmation source');
  await expect(medicationPanel).not.toContainText('{"');

  const currentPanel = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    'What medications are currently confirmed?',
  );
  await expect(currentPanel).toContainText(/Metformin 500 mg twice daily/i);
  await expect(currentPanel).toContainText('patient-confirmed');

  const documentPanel = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    'What medications were found in uploaded documents?',
  );
  await expect(documentPanel).toContainText(/Metformin 500 mg twice daily/i);
  await expect(documentPanel).toContainText('UNVERIFIED');
  await expect(documentPanel).toContainText('rag-e2e-metformin-prescription.png');

  const complaintPanel = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    "What is the patient's chief complaint?",
  );
  await expect(complaintPanel).toContainText('Fever since yesterday.');

  const allergyPanel = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    'What allergies are recorded?',
  );
  await expect(allergyPanel).toContainText('No supporting patient evidence was found.');
  await expect(allergyPanel).not.toContainText('No known allergies');

  const patientB = await startOnSitePatient(browser, 'RAG E2E Amlodipine Patient B');
  const seenB = await completeInterviewThroughPersistedAnswers(patientB.page, patientB.sessionId, {
    'chief_complaint.description': {
      value: 'Fever since this morning.',
      raw: 'Fever since this morning.',
    },
    'medications.any': { value: true, raw: 'Yes' },
    'medications.details': {
      value: 'Amlodipine 5 mg once daily',
      raw: 'Amlodipine 5 mg once daily',
    },
  });
  expect(seenB.has('medications.details')).toBeTruthy();
  expect(
    (await patientB.page.request.post(`/api/sessions/${patientB.sessionId}/complete`)).ok(),
  ).toBeTruthy();

  const patientBPanel = await searchInDoctorUI(
    doctor.page,
    patientB.sessionId,
    'Show medication evidence',
  );
  await expect(patientBPanel).toContainText('Amlodipine 5 mg once daily');
  await expect(patientBPanel).not.toContainText('Metformin');
  const patientAPanelAgain = await searchInDoctorUI(
    doctor.page,
    patientA.sessionId,
    'Show medication evidence',
  );
  await expect(patientAPanelAgain).toContainText(/Metformin 500 mg twice daily/i);
  await expect(patientAPanelAgain).not.toContainText('Amlodipine');

  const countBefore = (
    await (
      await doctor.page.request.get(
        `/api/doctor/sessions/${patientA.sessionId}/evidence-search/status`,
      )
    ).json()
  ).chunks_total;
  expect(
    (
      await doctor.page.request.post(
        `/api/doctor/sessions/${patientA.sessionId}/evidence-search/reindex`,
      )
    ).ok(),
  ).toBeTruthy();
  const firstReindex = await (
    await doctor.page.request.post(
      `/api/doctor/sessions/${patientA.sessionId}/evidence-search/reindex`,
    )
  ).json();
  expect(firstReindex.chunks_total).toBe(countBefore);

  const unassigned = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const unassignedPage = await unassigned.newPage();
  expect(
    (
      await unassignedPage.request.post('/api/auth/staff-login', {
        data: {
          identifier: '9876500011',
          password: 'Doctor@123',
          hospital_id: hospitalId,
          specialty: 'CARDIOLOGY',
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await unassignedPage.request.post(
        `/api/doctor/sessions/${patientA.sessionId}/evidence-search`,
        { data: { query: 'medications' } },
      )
    ).status(),
  ).toBe(403);

  const triage = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const triagePage = await triage.newPage();
  expect(
    (
      await triagePage.request.post('/api/auth/staff-login', {
        data: { identifier: '9876500002', password: 'Triage@123' },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await triagePage.request.post(`/api/doctor/sessions/${patientA.sessionId}/evidence-search`, {
        data: { query: 'medications' },
      })
    ).status(),
  ).toBe(403);

  expect(
    (
      await patientB.page.request.post(
        `/api/doctor/sessions/${patientA.sessionId}/evidence-search`,
        { data: { query: 'medications' } },
      )
    ).status(),
  ).toBe(403);

  console.log(
    `PATIENT_RAG_E2E_IDS patient_a_session=${patientA.sessionId} patient_b_session=${patientB.sessionId}`,
  );
  await Promise.all([
    patientA.context.close(),
    patientB.context.close(),
    doctor.context.close(),
    unassigned.close(),
    triage.close(),
  ]);
});
