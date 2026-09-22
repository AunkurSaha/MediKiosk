import { expect, test, type APIRequestContext } from '@playwright/test';
import { openKiosk, prepare } from './phase4-helpers';

async function finishInterview(api: APIRequestContext, sessionId: string) {
  let state = await (await api.get(`/api/sessions/${sessionId}/interview`)).json();
  for (let turn = 0; !state.is_complete && turn < 120; turn++) {
    const question = state.question;
    const chief = question.question_id === 'chief_complaint.description';
    const response = await api.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: state.revision,
        question_id: question.question_id,
        status: chief ? 'answered' : 'unknown',
        value: chief ? 'Fever reported for clinical assessment' : null,
        raw_value: chief ? 'Fever reported for clinical assessment' : 'Not known',
        source: 'typed',
        language: 'en',
      },
    });
    expect(response.ok()).toBeTruthy();
    state = await response.json();
  }
  expect(state.is_complete).toBe(true);
  expect((await api.post(`/api/sessions/${sessionId}/complete`)).ok()).toBeTruthy();
}

test('opaque handoff opens for assigned doctor, rotates, rejects wrong doctor, and revokes', async ({
  browser,
}) => {
  test.setTimeout(120000);
  const patientContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const patientPage = await patientContext.newPage();
  const { sessionId, api, route } = await prepare(patientPage, false);
  const facilityId = route.recommendations[0].facility_id;
  await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
    data: { facility_id: facilityId },
  });

  const doctorContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const doctorPage = await doctorContext.newPage();
  const doctorLogin = await doctorPage.request.post('/api/auth/demo-login', {
    data: { role: 'doctor', hospital_id: facilityId, specialty: 'CARDIOLOGY' },
  });
  const doctorId = (await doctorLogin.json()).user.id;
  const match = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  expect(match.recommendations.map((item: { doctor_id: string }) => item.doctor_id)).toContain(
    doctorId,
  );
  await api.put(`/api/sessions/${sessionId}/doctor-match/selection`, {
    data: { doctor_id: doctorId },
  });
  await finishInterview(api, sessionId);

  await openKiosk(patientPage, '/kiosk/complete');
  await expect(
    patientPage.getByRole('heading', { name: 'Your Pre-Arrival Packet' }),
  ).toBeVisible();
  const issueResponse = patientPage.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/sessions/${sessionId}/packet/handoff-token`) &&
      response.request().method() === 'POST',
  );
  await patientPage.getByRole('button', { name: 'Show Secure QR' }).click();
  const first = await (await issueResponse).json();
  expect(first.handoff_url).not.toContain(sessionId);
  expect(JSON.stringify(first.handoff_url)).not.toMatch(
    /patient|medication|summary|diagnosis|MK-/i,
  );

  await doctorPage.goto(first.handoff_url);
  await expect(doctorPage.getByRole('heading', { name: 'Pre-arrival packet' })).toBeVisible();
  await expect(doctorPage.getByText(/MK-[A-Z]+-\d{3}/)).toBeVisible();
  await expect(
    doctorPage.getByRole('link', { name: 'Open full clinical workspace' }),
  ).toBeVisible();

  const secondResponse = await api.post(`/api/sessions/${sessionId}/packet/handoff-token`);
  const second = await secondResponse.json();
  expect(second.handoff_url).not.toBe(first.handoff_url);
  await doctorPage.goto(first.handoff_url);
  await expect(doctorPage.getByText('This handoff link is invalid.')).toBeVisible();

  const wrongContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const wrongPage = await wrongContext.newPage();
  const wrongLogin = await wrongPage.request.post('/api/auth/staff-login', {
    data: {
      identifier: '9876500011',
      password: 'Doctor@123',
      hospital_id: facilityId,
      specialty: 'CARDIOLOGY',
    },
  });
  expect(wrongLogin.ok()).toBeTruthy();
  expect((await wrongLogin.json()).user.id).not.toBe(doctorId);
  await wrongPage.goto(second.handoff_url);
  await expect(
    wrongPage.getByText('You do not have access to this patient handoff.'),
  ).toBeVisible();

  await doctorPage.goto(second.handoff_url);
  await expect(doctorPage.getByRole('heading', { name: 'Pre-arrival packet' })).toBeVisible();
  expect((await api.post(`/api/sessions/${sessionId}/packet/revoke`)).ok()).toBeTruthy();
  await doctorPage.reload();
  await expect(doctorPage.getByText('This handoff link is no longer active.')).toBeVisible();
  await wrongContext.close();
  await doctorContext.close();
  await patientContext.close();
});
