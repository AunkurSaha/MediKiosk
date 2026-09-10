import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import type { InterviewState } from '../src/api/interview';

async function prepare(page: Page, language: 'bn' | 'en') {
  const id = crypto.randomUUID();
  expect(
    (
      await page.request.post('/api/sessions', {
        data: {
          id,
          patient: { name: 'Synthetic Normalization Patient', demo_abha_id: null },
          hospital_token: 'PHASE3A-' + Date.now(),
          language,
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
  return id;
}
async function current(page: Page, id: string): Promise<InterviewState> {
  const response = await page.request.get(`/api/sessions/${id}/interview`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function clickSave(page: Page, label: string) {
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: label, exact: true }).click();
  expect((await response).ok()).toBeTruthy();
}

test('Bengali source edit, mock normalization, unavailable text and doctor confirmation', async ({
  page,
}) => {
  test.setTimeout(120000);
  page.on('dialog', (d) => d.accept());
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const id = await prepare(page, 'bn');
  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
  await page.goto('/kiosk/interview');
  await page.getByRole('button', { name: 'বুকে ব্যথা', exact: true }).click();
  await page.getByLabel('আপনার উত্তর', { exact: true }).fill('বুকে ব্যথা');
  await clickSave(page, 'সংরক্ষণ করে এগিয়ে যান');
  let state = await current(page, id);
  const old = state.active_answers[0].normalization!;
  expect(old.facts[0].normalized_concept).toBe('CHEST_PAIN');
  await page.getByRole('button', { name: 'ফিরে যান', exact: true }).click();
  await expect(page.getByLabel('আপনার উত্তর', { exact: true })).toHaveValue('বুকে ব্যথা');
  await page.getByLabel('আপনার উত্তর', { exact: true }).fill('শ্বাসকষ্ট');
  await clickSave(page, 'সংরক্ষণ করে এগিয়ে যান');
  await page.reload();
  state = await current(page, id);
  const latest = state.active_answers[0].normalization!;
  expect(latest.source_answer_id).not.toBe(old.source_answer_id);
  expect(latest.facts[0].normalized_concept).toBe('DYSPNEA');
  expect(state.flow_id).toBe('chest_pain');
  for (let i = 0; i < 60 && state.question; i++) {
    await expect(
      page.getByRole('heading', { name: state.question.text.bn, exact: true }),
    ).toBeVisible();
    if (state.question.question_id === 'hpi.site') {
      await page.getByLabel('আপনার উত্তর', { exact: true }).fill('বুকের মধ্যে অদ্ভুত চাপ লাগছে');
      await clickSave(page, 'সংরক্ষণ করে এগিয়ে যান');
    } else await clickSave(page, 'জানা নেই');
    state = await current(page, id);
  }
  expect(state.is_complete).toBeTruthy();
  await page.getByRole('button', { name: 'তথ্য সংগ্রহ শেষ করুন', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'চিকিৎসকের পর্যালোচনার জন্য প্রস্তুত' }),
  ).toBeVisible();
  await page.goto(`/doctor/sessions/${id}`);
  await expect(
    page.locator('dd[lang="bn"]').filter({ hasText: 'শ্বাসকষ্ট' }).first(),
  ).toBeVisible();
  await expect(
    page.locator('.normalization-panel').getByText('Breathlessness', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Normalization unavailable — needs verification', { exact: true }),
  ).toBeVisible();
  expect(await page.locator('.normalization-panel .success').count()).toBe(0);
  const reviewed = 'Synthetic multilingual history reviewed; machine facts remain unverified.';
  await page.getByLabel('Reviewed summary', { exact: true }).fill(reviewed);
  await page.getByRole('button', { name: 'Save review', exact: true }).click();
  await expect(page.getByText('Review saved.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm reviewed record' }).click();
  await expect(page.getByText('Record confirmed.', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Reviewed summary', { exact: true })).toHaveAttribute('readonly');
  await expect(page.locator('.normalization-panel').first()).toContainText(
    'not clinician verified',
  );
  await mkdir('../.runtime/screenshots', { recursive: true });
  await page
    .locator('.normalization-panel')
    .first()
    .screenshot({ path: '../.runtime/screenshots/phase3a-normalization.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  const overflowers = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth)
      .map((element) => ({
        tag: element.tagName,
        className: element.className,
        parentClassName: element.parentElement?.className ?? '',
        text: element.textContent?.trim().slice(0, 60) ?? '',
        right: Math.round(element.getBoundingClientRect().right),
        width: Math.round(element.getBoundingClientRect().width),
      }))
      .slice(0, 20),
  );
  expect(overflowers, JSON.stringify(overflowers, null, 2)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await writeFile(
    '../.runtime/last-phase3a-e2e.json',
    JSON.stringify({ sessionId: id, reviewed, normalizationId: latest.id }),
  );

  const resumeId = await prepare(page, 'en');
  expect(
    (
      await page.request.put(`/api/sessions/${resumeId}/interview/flow`, {
        data: { flow_id: 'fever' },
      })
    ).ok(),
  ).toBeTruthy();
  const pending = await current(page, resumeId);
  const saved = await page.request.post(`/api/sessions/${resumeId}/interview/answers`, {
    data: {
      request_id: crypto.randomUUID(),
      expected_revision: pending.revision,
      question_id: pending.question!.question_id,
      value: 'chest pain',
      raw_value: 'chest pain',
      status: 'answered',
      source: 'typed',
      language: 'en',
    },
  });
  expect(saved.ok()).toBeTruthy();
  const resumable: InterviewState = await saved.json();
  await writeFile(
    '../.runtime/phase3a-resume.json',
    JSON.stringify({
      sessionId: resumeId,
      questionId: resumable.question!.question_id,
      revision: resumable.revision,
      text: resumable.question!.text.en,
      normalizationId: resumable.active_answers[0].normalization!.id,
    }),
  );
  expect(errors).toEqual([]);
});
