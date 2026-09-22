import { expect, test } from '@playwright/test';

test('joint-pain browser path reaches orthopedics and serves the focused configured interview', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const api = page.request;
  expect((await api.post('/api/auth/demo-login', { data: { role: 'patient' } })).ok()).toBeTruthy();

  const sessionId = crypto.randomUUID();
  const created = await api.post('/api/sessions', {
    data: {
      id: sessionId,
      patient: {
        name: 'Synthetic Joint Pain QA',
        gender: 'female',
        age_years: 44,
        height_cm: 164,
        weight_kg: 66,
        demo_abha_id: null,
      },
      hospital_token: `INTAKE-${sessionId.slice(0, 8)}`,
      language: 'en',
      journey_mode: 'PRE_ARRIVAL',
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
      data: { original_text: 'Joint pain', language: 'en', source: 'card' },
    })
  ).json();
  const routed = await (
    await api.put(`/api/sessions/${sessionId}/rapid-routing/complaint`, {
      data: { category: 'JOINT_PAIN', confirmed: true, expected_revision: mapped.revision },
    })
  ).json();
  expect(routed.phase).toBe('result');
  expect(routed.result.suggested_specialty).toBe('ORTHOPEDICS');

  expect(
    (
      await api.put(`/api/sessions/${sessionId}/routing-location`, {
        data: { source: 'MANUAL_LOCALITY', locality: 'Kolkata' },
      })
    ).ok(),
  ).toBeTruthy();
  const route = await (await api.get(`/api/sessions/${sessionId}/mediroute`)).json();
  expect(route.recommendations.length).toBeGreaterThan(0);

  let selectedDoctor: string | null = null;
  for (const facility of route.recommendations.slice(0, 3)) {
    expect(
      (
        await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
          data: { facility_id: facility.facility_id },
        })
      ).ok(),
    ).toBeTruthy();
    const match = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
    if (match.status === 'COMPLETED' && match.recommendations.length) {
      const recommendation = match.recommendations[0];
      expect(recommendation.primary_specialty).toBe('ORTHOPEDICS');
      selectedDoctor = recommendation.doctor_id;
      const selection = await api.put(`/api/sessions/${sessionId}/doctor-match/selection`, {
        data: { doctor_id: selectedDoctor },
      });
      expect(selection.ok(), await selection.text()).toBeTruthy();
      break;
    }
  }
  expect(selectedDoctor).toBeTruthy();

  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), sessionId);
  await page.goto('/kiosk/interview');
  await expect(page.getByRole('heading', { name: /describe the joint pain/i })).toBeVisible({
    timeout: 30_000,
  });

  let interview = await (await api.get(`/api/sessions/${sessionId}/interview`)).json();
  const questions: string[] = [];
  for (let turn = 0; interview.question && turn < 20; turn += 1) {
    questions.push(interview.question.text.en);
    const answer = await api.post(`/api/sessions/${sessionId}/interview/answers`, {
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
    expect(answer.ok()).toBeTruthy();
    interview = await answer.json();
  }
  expect(interview.is_complete).toBe(true);
  expect(questions).toEqual(
    expect.arrayContaining([
      'Which joint is affected?',
      'When did the pain start?',
      'Did it start suddenly or gradually?',
      'Is there swelling, redness, or warmth?',
      'Was there an injury, fall, or twisting?',
      'Is the pain worse while walking or moving?',
      'Do you have morning stiffness?',
      'Do you have fever along with the joint pain?',
      'Have you had this problem before?',
      'Are you taking any pain medicine currently?',
    ]),
  );
});

test('doctor-empty facility returns to recommendations and allows a valid next hospital', async ({
  page,
}) => {
  test.setTimeout(120_000);
  const api = page.request;
  expect((await api.post('/api/auth/demo-login', { data: { role: 'patient' } })).ok()).toBeTruthy();
  const sessionId = crypto.randomUUID();
  expect(
    (
      await api.post('/api/sessions', {
        data: {
          id: sessionId,
          patient: {
            name: 'Synthetic Facility Fallback QA',
            gender: 'male',
            age_years: 35,
            height_cm: 172,
            weight_kg: 72,
            demo_abha_id: null,
          },
          hospital_token: `INTAKE-${sessionId.slice(0, 8)}`,
          language: 'en',
          journey_mode: 'PRE_ARRIVAL',
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/consent`, {
        data: { share_with_doctor: true, voice_processing: false, document_processing: false },
      })
    ).ok(),
  ).toBeTruthy();
  const mapped = await (
    await api.post(`/api/sessions/${sessionId}/rapid-routing/complaint/map`, {
      data: { original_text: 'Fever', language: 'en', source: 'card' },
    })
  ).json();
  let routing = await (
    await api.put(`/api/sessions/${sessionId}/rapid-routing/complaint`, {
      data: { category: 'FEVER', confirmed: true, expected_revision: mapped.revision },
    })
  ).json();
  while (routing.phase !== 'result') {
    const question = routing.question;
    const value = question.input_type === 'number' ? 38 : false;
    routing = await (
      await api.post(`/api/sessions/${sessionId}/rapid-routing/answers`, {
        data: {
          question_id: question.question_id,
          value,
          raw_value: String(value),
          source: question.input_type === 'number' ? 'typed' : 'touch',
          language: 'en',
          expected_revision: routing.revision,
        },
      })
    ).json();
  }
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/routing-location`, {
        data: { source: 'MANUAL_LOCALITY', locality: 'Kolkata' },
      })
    ).ok(),
  ).toBeTruthy();
  const route = await (await api.get(`/api/sessions/${sessionId}/mediroute`)).json();
  const emptyFacility = route.recommendations.find(
    (item: { facility_id: string }) => item.facility_id === '10000000-0000-4000-8000-000000000005',
  );
  expect(emptyFacility).toBeTruthy();
  expect(
    (
      await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
        data: { facility_id: emptyFacility.facility_id },
      })
    ).ok(),
  ).toBeTruthy();

  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), sessionId);
  await page.goto('/kiosk/doctor');
  await expect(page.getByText(/No suitable doctor is currently available/i)).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'View next recommended facility' }).click();
  await expect(page.getByRole('heading', { name: 'Recommended facilities' })).toBeVisible();
  const cityHospital = page.locator('article').filter({ hasText: 'MediKiosk City Hospital' });
  await cityHospital.getByRole('button', { name: 'Select facility' }).click();
  await expect(
    page.getByRole('heading', { name: 'Choose a clinically suitable doctor' }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('Dr. Ishan Gupta')).toBeVisible();
});

test('patient and doctor desktop shells have no horizontal overflow at 1920x1080', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'MediKiosk' })).toBeVisible();
  await expect(page.getByText('Patient Login')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  expect(
    (await page.request.post('/api/auth/demo-login', { data: { role: 'patient' } })).ok(),
  ).toBeTruthy();
  await page.goto('/kiosk/language');
  await expect(
    page.getByRole('heading', { name: 'A little preparation. More time with your doctor.' }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  expect(
    (await page.request.post('/api/auth/demo-login', { data: { role: 'doctor' } })).ok(),
  ).toBeTruthy();
  await page.goto('/doctor');
  await expect(page.getByRole('heading', { name: 'Ready to review' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
