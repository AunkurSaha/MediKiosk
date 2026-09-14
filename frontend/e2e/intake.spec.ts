import { test, expect } from '@playwright/test';
import { writeFile, mkdir } from 'node:fs/promises';
import { questions } from '../src/test/legacy-fixture';

test('Phase 1 regression: legacy intake through doctor confirmation persists in PostgreSQL', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  const token = 'E2E-' + Date.now();
  await page.setViewportSize({ width: 1360, height: 1000 });
  await page.goto('/kiosk/language');
  await expect(page.getByRole('heading', { name: /A little preparation/ })).toBeVisible();
  await mkdir('../.runtime/screenshots', { recursive: true });
  await page.screenshot({ path: '../.runtime/screenshots/kiosk-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByLabel('Patient name').fill('Synthetic Browser Patient');
  await page.getByLabel('Gender').selectOption('male');
  await page.getByLabel('Age (years)').fill('44');
  await page.getByLabel('Height (cm)').fill('174');
  await page.getByLabel('Weight (kg)').fill('72');
  await page.getByLabel('Hospital token').fill(token);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Start the interview' })).toBeDisabled();
  await page.getByRole('checkbox', { name: /agree to store/i }).check();
  await page.getByRole('button', { name: 'Start the interview' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your main concern' })).toBeVisible();
  const retainedId = await page.evaluate(() => sessionStorage.getItem('medikiosk.session'));
  // Simulate an existing Phase 1 session, then resume it through the server renderer.
  const seeded = await page.request.post('/api/sessions/' + retainedId + '/answers', {
    data: {
      question_id: 'chief_complaint',
      field: 'chief_complaint',
      value: 'Earlier synthetic wording',
      raw_value: 'Earlier synthetic wording',
      source: 'typed',
      language: 'en',
    },
  });
  expect(seeded.ok()).toBeTruthy();
  const back = await page.request.put('/api/sessions/' + retainedId + '/interview/cursor', {
    data: {
      question_id: 'chief_complaint',
      expected_revision: 0,
    },
  });
  expect(back.ok()).toBeTruthy();
  await page.reload();
  const values = [
    'A fictional concern for testing',
    'Since yesterday',
    'Not sure',
    'None reported',
    'Not sure',
  ];
  for (let i = 0; i < questions.length; i++) {
    await expect(
      page.getByRole('heading', { name: questions[i].text.en, exact: true }),
    ).toBeVisible();
    if (i === 1) {
      await page.reload();
      await expect(
        page.getByRole('heading', { name: questions[i].text.en, exact: true }),
      ).toBeVisible();
    }
    await page.getByLabel('Your answer', { exact: true }).fill(values[i]);
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Finish intake', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your doctor' })).toBeVisible();
  await expect(page.getByText(token, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Start a new intake' }).click();
  await page.getByRole('button', { name: /English/ }).click();
  await expect(page.getByLabel('Patient name')).toHaveValue('');

  await page.getByRole('link', { name: 'Doctor workspace' }).click();
  await page.getByRole('link').filter({ hasText: token }).click();
  const sessionId = page.url().split('/').pop();
  for (const value of new Set(values)) {
    await expect(page.locator('dd').filter({ hasText: value }).first()).toBeVisible();
  }
  const editor = page.getByLabel('Reviewed summary', { exact: true });
  await expect(editor).toContainText(values[0]);
  const reviewed =
    'Patient-reported fictional concern since yesterday. Medicines and past history not known. No allergies reported. Reviewed in a synthetic demonstration.';
  await editor.fill(reviewed);
  await page.getByRole('button', { name: 'Save review', exact: true }).click();
  await expect(page.getByText('Review saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm reviewed record' }).click();
  await expect(page.getByText('Record confirmed.', { exact: true })).toBeVisible();
  await expect(editor).toHaveAttribute('readonly');
  await page.reload();
  await expect(page.getByLabel('Reviewed summary', { exact: true })).toHaveValue(reviewed);
  await expect(page.getByLabel('Reviewed summary', { exact: true })).toHaveAttribute('readonly');
  await page.screenshot({ path: '../.runtime/screenshots/doctor-confirmed.png', fullPage: true });
  await writeFile('../.runtime/last-e2e.json', JSON.stringify({ sessionId, token, reviewed }));
  expect(errors).toEqual([]);
});

test('mobile language choice and localized identity fit the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/kiosk/language');
  await page.getByRole('button', { name: /বাংলা/ }).click();
  await expect(page.getByLabel('রোগীর নাম')).toBeVisible();
  await page.screenshot({
    path: '../.runtime/screenshots/kiosk-bengali-mobile.png',
    fullPage: true,
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
