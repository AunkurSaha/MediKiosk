import { expect, test } from '@playwright/test';

export async function prepare(page: import('@playwright/test').Page, emergency: boolean) {
  const api = page.request;
  const config = await (await api.get('/api/config')).json();
  expect(config.local_e2e_mode).toBe(true);
  const login = await api.post('/api/auth/demo-login', { data: { role: 'patient' } });
  expect(login.ok()).toBeTruthy();
  const sessionId = crypto.randomUUID();
  const created = await api.post('/api/sessions', {
    data: {
      id: sessionId,
      patient: {
        name: 'Synthetic Phase 4 Browser',
        gender: 'female',
        age_years: 36,
        height_cm: 163,
        weight_kg: 58,
      },
      hospital_token: `P4-${sessionId.slice(0, 8)}`,
      language: 'en',
    },
  });
  expect(created.status()).toBe(201);
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/consent`, {
        data: { share_with_doctor: true, voice_processing: false, document_processing: false },
      })
    ).ok(),
  ).toBeTruthy();
  const mapped = await (
    await api.post(`/api/sessions/${sessionId}/rapid-routing/complaint/map`, {
      data: { original_text: 'Chest discomfort', language: 'en', source: 'card' },
    })
  ).json();
  let state = await (
    await api.put(`/api/sessions/${sessionId}/rapid-routing/complaint`, {
      data: { category: 'CHEST_DISCOMFORT', confirmed: true, expected_revision: mapped.revision },
    })
  ).json();
  for (let index = 0; state.phase !== 'result' && index < 5; index++) {
    const question = state.question;
    const value =
      question.input_type === 'severity'
        ? emergency
          ? 9
          : 2
        : emergency && question.question_id === 'rapid.chest.radiation';
    const answer = await api.post(`/api/sessions/${sessionId}/rapid-routing/answers`, {
      data: {
        question_id: question.question_id,
        value,
        raw_value: String(value),
        source: typeof value === 'boolean' ? 'touch' : 'typed',
        language: 'en',
        expected_revision: state.revision,
      },
    });
    expect(answer.ok()).toBeTruthy();
    state = await answer.json();
  }
  expect(state.phase).toBe('result');
  expect(state.result.routing_state).toBe(emergency ? 'EMERGENCY' : 'ROUTINE_OPD');
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/routing-location`, {
        data: { source: 'MANUAL_LOCALITY', locality: 'Kolkata' },
      })
    ).ok(),
  ).toBeTruthy();
  const route = await (await api.get(`/api/sessions/${sessionId}/mediroute`)).json();
  expect(route.status).toBe('COMPLETED');
  await page.addInitScript((id) => sessionStorage.setItem('medikiosk.session', id), sessionId);
  return { sessionId, api, route };
}

export async function openKiosk(page: import('@playwright/test').Page, path: string) {
  await page.goto('/kiosk/language');
  await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible();
  await page.goto(path);
}

test('doctor recommendations survive refresh and explicit selection resumes interview', async ({
  page,
}) => {
  const { sessionId, api, route } = await prepare(page, false);
  const facilityId = route.recommendations[0].facility_id;
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
        data: { facility_id: facilityId },
      })
    ).ok(),
  ).toBeTruthy();
  await openKiosk(page, '/kiosk/doctor');
  await expect(
    page.getByRole('heading', { name: 'Choose a clinically suitable doctor' }),
  ).toBeVisible();
  await expect(page.getByText('Dr. Mira Roy')).toHaveCount(0);
  const first = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Choose a clinically suitable doctor' }),
  ).toBeVisible();
  const again = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  expect(again.id).toBe(first.id);
  await page.getByRole('button', { name: 'Select Doctor' }).first().click();
  await expect(page).toHaveURL(/\/kiosk\/interview$/);
  const selected = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  expect(selected.selected_doctor_id).toBeTruthy();
  await page.reload();
  await expect(page).toHaveURL(/\/kiosk\/interview$/);
  await page.goto('/kiosk/doctor');
  await expect(page).toHaveURL(/\/kiosk\/interview$/);
});

test('emergency facility handoff never enters normal doctor recommendations', async ({ page }) => {
  await prepare(page, true);
  await openKiosk(page, '/kiosk/location');
  await expect(
    page.getByText('Suitable emergency-capable facilities in the current demo directory'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Select facility' }).first().click();
  await expect(page).toHaveURL(/\/kiosk\/emergency$/);
  await expect(
    page.getByRole('heading', { name: 'Immediate clinical assessment recommended' }),
  ).toBeVisible();
  await expect(page.getByText(/Normal doctor matching is not used/)).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/kiosk\/emergency$/);
});
