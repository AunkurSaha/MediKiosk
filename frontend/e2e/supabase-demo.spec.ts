import { expect, test } from '@playwright/test';

test('Supabase recording backend is explicit and retains the assigned patient after refresh', async ({
  browser,
}) => {
  test.skip(
    process.env.MEDIKIOSK_SUPABASE_DEMO_QA !== '1',
    'Set MEDIKIOSK_SUPABASE_DEMO_QA=1 only after preparing the synthetic Supabase demo.',
  );

  const patientContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const config = await patientContext.request.get('/api/config');
  expect(config.ok()).toBeTruthy();
  expect(await config.json()).toMatchObject({ app_env: 'demo', local_e2e_mode: false });

  const doctorContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5175' });
  const login = await doctorContext.request.post('/api/auth/staff-login', {
    data: {
      identifier: '9876500012',
      password: 'Doctor@123',
      hospital_id: '10000000-0000-4000-8000-000000000001',
      specialty: 'GENERAL_MEDICINE',
    },
  });
  expect(login.ok()).toBeTruthy();

  const page = await doctorContext.newPage();
  await page.goto('/doctor');
  const demoPatient = page.getByRole('link', { name: /Demo Patient/ }).first();
  await expect(demoPatient).toBeVisible();
  const detailHref = await demoPatient.getAttribute('href');
  expect(detailHref).toMatch(/^\/doctor\/sessions\//);
  await page.goto(detailHref!);
  await expect(page.getByLabel('Pre-Consultation Brief')).toBeVisible();

  await page.getByLabel('Evidence search query').fill('Show medication evidence');
  await page.getByRole('button', { name: 'Search evidence' }).click();
  const results = page.getByTestId('patient-evidence-results');
  await expect(results).toContainText('Metformin');
  await expect(results).toContainText('500 mg');
  await expect(results).toContainText(/Twice Daily/i);
  await expect(results).toContainText(/prescription/i);

  await page.reload();
  await expect(page.getByLabel('Pre-Consultation Brief')).toBeVisible();
  await page.goto('/doctor');
  await expect(page.getByRole('link', { name: /Demo Patient/ }).first()).toBeVisible();

  await patientContext.close();
  await doctorContext.close();
});
