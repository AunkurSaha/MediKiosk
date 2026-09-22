import { expect, test, type APIRequestContext } from '@playwright/test';
import { openKiosk, prepare } from './phase4-helpers';

async function finishInterview(api: APIRequestContext, sessionId: string) {
  let state = await (await api.get(`/api/sessions/${sessionId}/interview`)).json();
  for (let turn = 0; !state.is_complete && turn < 120; turn++) {
    const question = state.question;
    expect(question).toBeTruthy();
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

test('patient completion shows the persisted queue token after reload', async ({ page }) => {
  const { sessionId, api, route } = await prepare(page, false);
  const facilityId = route.recommendations[0].facility_id;
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
        data: { facility_id: facilityId },
      })
    ).ok(),
  ).toBeTruthy();
  const match = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/doctor-match/selection`, {
        data: { doctor_id: match.recommendations[0].doctor_id },
      })
    ).ok(),
  ).toBeTruthy();
  await finishInterview(api, sessionId);
  await openKiosk(page, '/kiosk/complete');
  await expect(page.getByLabel('Visit queue reservation')).toBeVisible();
  const tokenLine = page.getByText(/Visit token:/);
  await expect(tokenLine).toContainText(/MK-[A-Z]+-\d{3}/);
  const token = await tokenLine.textContent();
  await page.reload();
  await expect(page.getByText(token ?? '')).toBeVisible();
  await expect(page.getByText(/estimated waiting time and may change/i)).toBeVisible();
});

test('doctor calls, starts, and completes an assigned queue entry', async ({ browser }) => {
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

  await doctorPage.goto('/doctor');
  await doctorPage.getByRole('link', { name: /Synthetic Phase 4 Browser/ }).click();
  await doctorPage.getByRole('button', { name: 'Call patient' }).click();
  await doctorPage.getByRole('button', { name: 'Start consultation' }).click();
  const completionResponse = doctorPage.waitForResponse((response) => {
    const request = response.request();
    return (
      request.method() === 'PUT' &&
      request.url().endsWith(`/api/doctor/sessions/${sessionId}/queue`) &&
      request.postData() === '{"status":"COMPLETED"}'
    );
  });
  await doctorPage.getByRole('button', { name: 'Complete consultation' }).click();
  await completionResponse;
  const queue = await (await api.get(`/api/sessions/${sessionId}/queue-estimate`)).json();
  expect(queue.status).toBe('COMPLETED');
  await patientContext.close();
  await doctorContext.close();
});
