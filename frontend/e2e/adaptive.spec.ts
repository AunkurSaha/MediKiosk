import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import type { InterviewState } from '../src/api/interview';

async function state(page: Page, id: string): Promise<InterviewState> {
  const result = await page.request.get(`/api/sessions/${id}/interview`);
  expect(result.ok()).toBeTruthy();
  return result.json();
}
async function save(page: Page) {
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save and continue', exact: true }).click();
  expect((await response).ok()).toBeTruthy();
}
async function back(page: Page) {
  const response = page.waitForResponse((r) => r.url().endsWith('/interview/cursor'));
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  expect((await response).ok()).toBeTruthy();
}
async function defaultAnswer(page: Page, current: InterviewState) {
  const q = current.question!;
  await expect(page.getByRole('heading', { name: q.text.en, exact: true })).toBeVisible();
  if (!q.required || q.question_id === 'hpi.relieving') {
    const response = page.waitForResponse((r) => r.url().endsWith('/interview/answers'));
    await page
      .getByRole('button', {
        name: !q.required ? 'Skip optional question' : 'Unknown',
        exact: true,
      })
      .click();
    expect((await response).ok()).toBeTruthy();
    return;
  }
  if (q.type === 'boolean') await page.getByLabel('No', { exact: true }).check();
  else if (q.type === 'single_choice' || q.type === 'multiple_choice')
    await page.getByLabel(q.options[0].label.en, { exact: true }).check();
  else
    await page
      .getByLabel('Your answer', { exact: true })
      .fill(q.type === 'short_text' ? 'Synthetic history for browser verification' : '2');
  await save(page);
}

test('adaptive interview persists branch edits, restores history and reaches doctor confirmation', async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('dialog', (d) => d.accept());
  const token = 'PHASE2-' + Date.now();
  await page.goto('/kiosk/language');
  await page.getByRole('button', { name: /English/ }).click();
  await page.getByLabel('Patient name').fill('Synthetic Adaptive Patient');
  await page.getByLabel('Gender').selectOption('prefer_not_to_say');
  await page.getByLabel('Age (years)').fill('39');
  await page.getByLabel('Height (cm)').fill('166');
  await page.getByLabel('Weight (kg)').fill('63');
  await page.getByLabel('Hospital token').fill(token);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.getByRole('checkbox', { name: /agree to store/i }).check();
  await page.getByRole('button', { name: 'Start the interview' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your main concern' })).toBeVisible();
  await mkdir('../.runtime/screenshots', { recursive: true });
  await page.screenshot({ path: '../.runtime/screenshots/phase2-selection.png', fullPage: true });
  await page.getByRole('button', { name: 'Chest pain', exact: true }).click();
  const id = (await page.evaluate(() => sessionStorage.getItem('medikiosk.session')))!;
  let current = await state(page, id);
  for (
    let count = 0;
    count < 30 && current.question?.question_id !== 'past_medical_history.diabetes';
    count++
  ) {
    await defaultAnswer(page, current);
    current = await state(page, id);
  }
  expect(current.question?.question_id).toBe('past_medical_history.diabetes');
  await page.getByLabel('Yes', { exact: true }).check();
  await save(page);
  await page.getByLabel('Your answer', { exact: true }).fill('3');
  await page.getByLabel('Time unit', { exact: true }).selectOption('years');
  await save(page);
  await page.getByLabel('Your answer', { exact: true }).fill('Historical synthetic diabetes care');
  await save(page);
  await back(page);
  await back(page);
  await back(page);
  await page.getByLabel('No', { exact: true }).check();
  await save(page);
  current = await state(page, id);
  expect(current.inactive_question_ids).toContain('past_medical_history.diabetes_duration');
  expect(JSON.stringify(current.history)).not.toContain('Historical synthetic diabetes care');
  await back(page);
  await page.getByLabel('Yes', { exact: true }).check();
  await save(page);
  await expect(page.getByLabel('Your answer', { exact: true })).toHaveValue('3');
  await expect(page.getByLabel('Time unit')).toHaveValue('years');
  await page.reload();
  await expect(page.getByLabel('Your answer', { exact: true })).toHaveValue('3');
  await back(page);
  await page.getByLabel('No', { exact: true }).check();
  await save(page);
  current = await state(page, id);
  for (let count = 0; count < 60 && current.question; count++) {
    await defaultAnswer(page, current);
    current = await state(page, id);
  }
  expect(current.is_complete).toBeTruthy();
  await page.getByRole('button', { name: 'Finish intake', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Ready for your doctor' })).toBeVisible();
  await page.goto(`/doctor/sessions/${id}`);
  await expect(
    page.getByRole('heading', { name: 'Past medical history', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.history')).not.toContainText('Historical synthetic diabetes care');
  await expect(page.locator('.history')).toContainText('Patient reported');
  const reviewed = 'Phase 2 synthetic history reviewed. Inactive branch history excluded.';
  const editor = page.getByLabel('Reviewed summary', { exact: true });
  await editor.fill(reviewed);
  await page.getByRole('button', { name: 'Save review', exact: true }).click();
  await expect(page.getByText('Review saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm reviewed record' }).click();
  await expect(page.getByText('Record confirmed.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(editor).toHaveValue(reviewed);
  await expect(editor).toHaveAttribute('readonly');
  await page.screenshot({ path: '../.runtime/screenshots/phase2-doctor.png', fullPage: true });
  await writeFile(
    '../.runtime/last-phase2-e2e.json',
    JSON.stringify({ sessionId: id, token, reviewed }),
  );
  expect(errors).toEqual([]);
});

test('localized adaptive question fits mobile and leaves a persisted resumable interview', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const id = crypto.randomUUID();
  expect(
    (
      await page.request.post('/api/sessions', {
        data: {
          id,
          patient: { name: 'Synthetic Bengali Resume', demo_abha_id: null },
          hospital_token: 'PHASE2-RESUME',
          language: 'bn',
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await page.request.put(`/api/sessions/${id}/consent`, {
        data: { share_with_doctor: true, voice_processing: false, document_processing: false },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await page.request.put(`/api/sessions/${id}/interview/flow`, { data: { flow_id: 'fever' } })
    ).ok(),
  ).toBeTruthy();
  let current = await state(page, id);
  for (let i = 0; i < 2; i++) {
    const result = await page.request.post(`/api/sessions/${id}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: current.revision,
        question_id: current.question!.question_id,
        value: null,
        status: 'unknown',
        raw_value: 'জানা নেই',
        source: 'touch',
        language: 'bn',
      },
    });
    expect(result.ok()).toBeTruthy();
    current = await result.json();
  }
  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
  await page.goto('/kiosk/interview');
  await expect(page.getByRole('heading', { name: current.question!.text.bn })).toBeVisible();
  await expect(page.getByLabel('হ্যাঁ', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: '../.runtime/screenshots/phase2-bengali-mobile.png',
    fullPage: true,
  });
  await writeFile(
    '../.runtime/phase2-resume.json',
    JSON.stringify({
      sessionId: id,
      questionId: current.question!.question_id,
      revision: current.revision,
      text: current.question!.text.bn,
    }),
  );
});
