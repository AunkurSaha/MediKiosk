import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import type { InterviewState } from '../src/api/interview';

const staff = { 'X-Demo-Doctor': 'true' };

test('a missing source lab flag remains null in the API and Not reported in doctor UI', async ({
  page,
  request,
}) => {
  const { id } = await create(request);
  const bytes = await readFile('../ai/document_fixtures/lab_missing_flag.png');
  const uploaded = await request.post(`/api/sessions/${id}/documents`, {
    multipart: {
      file: { name: 'synthetic-missing-flag.png', mimeType: 'image/png', buffer: bytes },
    },
  });
  expect(uploaded.status()).toBe(201);
  const document = await uploaded.json();
  expect(document.extractions[0].structured_json.observations[0].flag).toBeNull();
  await page.goto(`/doctor/sessions/${id}`);
  const row = page.getByRole('row').filter({ hasText: 'Hemoglobin' });
  await expect(row).toContainText('Not reported');
  await expect(row).not.toContainText('Normal');
});

test('real WebSocket transport rejects missing credentials and reused admission tickets', async ({
  page,
  request,
}) => {
  await page.goto('/kiosk/language');
  const connect = (protocols: string[]) =>
    page.evaluate(
      (values) =>
        new Promise<string>((resolve) => {
          const socket = new WebSocket(
            `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/triage/ws`,
            values,
          );
          const timeout = setTimeout(() => {
            socket.close();
            resolve('timeout');
          }, 5000);
          socket.onopen = () => {
            clearTimeout(timeout);
            socket.close();
            resolve('opened');
          };
          socket.onerror = () => {
            clearTimeout(timeout);
            resolve('rejected');
          };
        }),
      protocols,
    );
  expect(await connect([])).toBe('rejected');
  expect((await request.post('/api/triage/ws-ticket')).status()).toBe(401);
  const response = await request.post('/api/triage/ws-ticket', { headers: staff });
  expect(response.ok()).toBeTruthy();
  const { ticket } = await response.json();
  expect(await connect(['medikiosk', ticket])).toBe('opened');
  expect(await connect(['medikiosk', ticket])).toBe('rejected');
});
async function create(request: APIRequestContext, flow = 'chest_pain', language = 'en') {
  const id = randomUUID();
  expect(
    (
      await request.post('/api/sessions', {
        data: {
          id,
          patient: { name: 'Synthetic stabilization patient' },
          hospital_token: `STAB-${id.slice(0, 8)}`,
          language,
        },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await request.put(`/api/sessions/${id}/consent`, {
        data: { share_with_doctor: true, document_processing: true, voice_processing: true },
      })
    ).ok(),
  ).toBeTruthy();
  const response = await request.put(`/api/sessions/${id}/interview/flow`, {
    data: { flow_id: flow },
  });
  expect(response.ok()).toBeTruthy();
  return { id, state: (await response.json()) as InterviewState };
}
async function submit(
  request: APIRequestContext,
  id: string,
  state: InterviewState,
  value: unknown = null,
  language = 'en',
) {
  const response = await request.post(`/api/sessions/${id}/interview/answers`, {
    data: {
      request_id: randomUUID(),
      expected_revision: state.revision,
      question_id: state.question!.question_id,
      status: value === null ? 'unknown' : 'answered',
      value,
      raw_value: value === null ? 'Unknown' : String(value),
      source: 'typed',
      language,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json() as Promise<InterviewState>;
}
async function until(
  request: APIRequestContext,
  id: string,
  state: InterviewState,
  field: string,
  language = 'en',
) {
  for (let i = 0; i < 80 && state.question?.question_id !== field; i++)
    state = await submit(request, id, state, null, language);
  expect(state.question?.question_id).toBe(field);
  return state;
}
async function openIntake(page: Page, id: string) {
  await page.goto('/kiosk/language');
  await page.evaluate((sid) => {
    sessionStorage.setItem('medikiosk.session', sid);
    sessionStorage.setItem('medikiosk.language', 'en');
  }, id);
  await page.goto('/kiosk/interview');
}

test('authorized open dashboard receives creation, resolution and reactivation without reload', async ({
  page,
  request,
}) => {
  const { id, state: initial } = await create(request, 'fever');
  let state = await until(request, id, initial, 'hpi.measured');
  state = await submit(request, id, state, true);
  await page.goto('/triage');
  await expect(page.getByText('Live Triage Feed Connected', { exact: true })).toBeVisible();
  state = await submit(request, id, state, 40);
  const record = (
    await (await request.get(`/api/sessions/${id}/alerts`, { headers: staff })).json()
  )[0];
  const card = page.getByTestId(`alert-card-${record.id}`);
  await expect(card).toContainText('RF-FEV-001');
  expect((await request.get('/api/triage/alerts')).status()).toBe(401);
  expect(
    (
      await request.post(`/api/triage/alerts/${record.id}/acknowledge`, {
        headers: staff,
        data: { acknowledged_by: 'Forged' },
      })
    ).status(),
  ).toBe(422);
  await card.getByRole('button', { name: 'Acknowledge Alert', exact: true }).click();
  await card.getByRole('button', { name: 'Confirm Acknowledgement', exact: true }).click();
  await expect(card.locator('.status-badge')).toHaveText('Acknowledged');
  expect(
    (
      await request.post(`/api/triage/alerts/${record.id}/acknowledge`, {
        headers: staff,
        data: {},
      })
    ).ok(),
  ).toBeTruthy();
  const cursor = await request.put(`/api/sessions/${id}/interview/cursor`, {
    data: { question_id: 'hpi.temperature', expected_revision: state.revision },
  });
  state = await submit(request, id, await cursor.json(), 37);
  await expect(card.locator('.status-badge')).toHaveText('Resolved');
  const resolved = (
    await (await request.get(`/api/sessions/${id}/alerts`, { headers: staff })).json()
  )[0];
  expect(resolved.trigger_active).toBe(false);
  expect(resolved.acknowledgement_state).toBe('acknowledged');
  const again = await request.put(`/api/sessions/${id}/interview/cursor`, {
    data: { question_id: 'hpi.temperature', expected_revision: state.revision },
  });
  await submit(request, id, await again.json(), 40);
  await expect(card.locator('.status-badge')).toHaveText('New');
  expect(
    (
      await request.post(`/api/triage/alerts/${record.id}/acknowledge`, {
        headers: staff,
        data: { expected_revision: 0 },
      })
    ).status(),
  ).toBe(409);
  const current = await (await request.get(`/api/sessions/${id}/interview`)).json();
  const updateCursor = await request.put(`/api/sessions/${id}/interview/cursor`, {
    data: { question_id: 'hpi.temperature', expected_revision: current.revision },
  });
  await submit(request, id, await updateCursor.json(), 41);
  await expect(card).toContainText('41');
  const updated = (
    await (await request.get(`/api/sessions/${id}/alerts`, { headers: staff })).json()
  )[0];
  expect(updated.triggering_facts.some((fact: { value: unknown }) => fact.value === 41)).toBe(true);
  expect(updated.revision).toBeGreaterThan(2);
  await writeFile(
    '../.runtime/stabilization-alert-reference.json',
    JSON.stringify({ sessionId: id }),
  );
});

for (const [language, denial] of [
  ['en', 'no blood in my sputum'],
  ['bn', 'আমার কফে রক্ত নেই'],
  ['hi', 'बलगम में खून नहीं है'],
  ['en', 'tired'],
]) {
  test(`negation/context preserved through API and doctor browser: ${denial}`, async ({
    page,
    request,
  }) => {
    const { id, state: initial } = await create(request, 'cough_breathlessness', language);
    let state = await until(request, id, initial, 'hpi.sputum', language);
    state = await submit(request, id, state, true, language);
    state = await submit(request, id, state, denial, language);
    expect(state.red_flag_alert).toBeNull();
    await page.goto(`/doctor/sessions/${id}`);
    await expect(page.locator('.history')).toContainText(denial);
    await expect(page.getByTestId('doctor-alerts-banner')).not.toBeVisible();
  });
}

test('document content, staff access, lab display, original preview and review lock', async ({
  page,
  request,
}) => {
  page.on('dialog', (dialog) => dialog.accept());
  const { id, state: initial } = await create(request);
  const url = `/api/sessions/${id}/documents`;
  expect(
    (
      await request.post(url, {
        multipart: {
          file: { name: 'report.png', mimeType: 'image/png', buffer: Buffer.from('not an image') },
        },
      })
    ).status(),
  ).toBe(422);
  const bytes = await readFile('../ai/document_fixtures/lab_report.png');
  expect(
    (
      await request.post(url, {
        multipart: {
          document_type: 'invalid',
          file: { name: 'report.png', mimeType: 'image/png', buffer: bytes },
        },
      })
    ).status(),
  ).toBe(422);
  const upload = await request.post(url, {
    multipart: { file: { name: 'synthetic-lab.png', mimeType: 'image/png', buffer: bytes } },
  });
  expect(upload.status()).toBe(201);
  const doc = await upload.json();
  expect(doc.processing_status).toBe('mock_fixture');
  expect(doc.extractions[0].confidence).toBeNull();
  expect((await request.get(url)).status()).toBe(401);
  expect((await request.get(`${url}/${doc.id}/file`)).status()).toBe(401);
  const verify = `${url}/${doc.id}/extractions/${doc.extractions[0].id}/verify`;
  expect((await request.post(verify, { data: { status: 'verified' } })).status()).toBe(401);
  expect(
    (
      await request.post(verify, {
        headers: staff,
        data: { status: 'verified', verified_by: 'Forged' },
      })
    ).status(),
  ).toBe(422);
  await page.goto(`/doctor/sessions/${id}`);
  const panel = page.getByTestId('document-viewer-panel');
  await expect(panel.getByRole('table')).toBeVisible();
  await expect(panel).toContainText('Hemoglobin');
  await expect(panel).toContainText('Synthetic mock output');
  await expect(panel).not.toContainText('95%');
  await expect
    .poll(() =>
      page
        .getByTestId('document-image-preview')
        .evaluate((img: HTMLImageElement) => img.naturalWidth),
    )
    .toBeGreaterThan(0);
  await panel.getByTestId(`btn-verify-${doc.extractions[0].id}`).click();
  await expect(panel).toContainText('00000000-0000-4000-8000-000000000001');
  let state = initial;
  for (let i = 0; i < 80 && state.question; i++) state = await submit(request, id, state);
  expect((await request.post(`/api/sessions/${id}/complete`)).ok()).toBeTruthy();
  await page.reload();
  await page
    .getByLabel('Reviewed summary', { exact: true })
    .fill('Synthetic stabilization review. Mock document remains separate from patient report.');
  await page.getByRole('button', { name: 'Save review', exact: true }).click();
  await expect(page.getByText('Review saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm reviewed record' }).click();
  await expect(page.getByText('Record confirmed.', { exact: true })).toBeVisible();
  expect(
    (
      await request.post(verify, {
        headers: staff,
        data: { status: 'rejected', expected_status: 'verified', expected_version: 1 },
      })
    ).status(),
  ).toBe(409);
  await page.screenshot({
    path: '../.runtime/screenshots/stabilization-document.png',
    fullPage: true,
  });
  await writeFile(
    '../.runtime/stabilization-document-reference.json',
    JSON.stringify({ sessionId: id, documentId: doc.id }),
  );
});

test('voice consent and forged candidate bypass fail through real API and kiosk stays usable', async ({
  page,
  request,
}) => {
  const { id, state } = await create(request);
  const payload = {
    request_id: randomUUID(),
    expected_revision: state.revision,
    question_id: state.question!.question_id,
    value: 'forged voice',
    raw_value: 'forged voice',
    source: 'voice',
    language: 'en',
  };
  expect(
    (await request.post(`/api/sessions/${id}/interview/answers`, { data: payload })).status(),
  ).toBe(422);
  await request.put(`/api/sessions/${id}/consent`, {
    data: { share_with_doctor: true, voice_processing: false, document_processing: false },
  });
  expect(
    (await request.post(`/api/sessions/${id}/interview/answers`, { data: payload })).status(),
  ).toBe(403);
  await openIntake(page, id);
  await expect(page.getByTestId('voice-recorder')).not.toBeVisible();
  await page.getByLabel('Your answer', { exact: true }).fill('typed synthetic answer');
  await page.getByRole('button', { name: 'Save and continue', exact: true }).click();
  await expect
    .poll(async () => {
      const saved = await (await request.get(`/api/sessions/${id}/interview`)).json();
      return saved.active_answers[0]?.source;
    })
    .toBe('typed');
});

test('fixture uploads visibly flow from kiosk extraction to doctor facts timeline and preview', async ({
  page,
  request,
}) => {
  const { id, state: initial } = await create(request);
  let state = initial;
  for (let index = 0; index < 80 && state.question; index++) {
    state = await submit(request, id, state);
  }
  expect(state.is_complete).toBe(true);
  await openIntake(page, id);

  const input = page.getByTestId('document-file-input');
  await input.setInputFiles('../ai/document_fixtures/prescription.png');
  await expect(page.getByTestId('uploaded-documents-list')).toContainText('Tab Paracetamol');
  await page.getByLabel('Document Type').selectOption('lab_report');
  await input.setInputFiles('../ai/document_fixtures/lab_report.png');
  await expect(page.getByTestId('uploaded-documents-list')).toContainText('Hemoglobin');
  await expect(page.getByTestId('uploaded-documents-list')).toContainText('mock_fixture');

  await page.getByRole('button', { name: 'Finish intake', exact: true }).click();
  await expect(page).toHaveURL(/\/kiosk\/complete$/);
  await page.goto(`/doctor/sessions/${id}`);
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();
  await expect(page.getByText('Medication: Tab Paracetamol', { exact: true })).toBeVisible();
  await expect(page.getByText('Lab: Hemoglobin', { exact: true })).toBeVisible();
  await expect(page.getByTestId('document-viewer-panel')).toBeVisible();
  await expect(page.getByTestId('document-image-preview')).toBeVisible();
  await expect(page.getByTestId('summary-workspace')).toBeVisible();
});
