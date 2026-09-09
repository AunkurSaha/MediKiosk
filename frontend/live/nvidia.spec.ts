import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';

test('doctor shows actual persisted NVIDIA smoke outcomes and raw wording honestly', async ({
  page,
}) => {
  const report = JSON.parse(
    await readFile(
      existsSync('../.runtime/nvidia-live-smoke.json')
        ? '../.runtime/nvidia-live-smoke.json'
        : '../.runtime/nvidia-live-evaluation.json',
      'utf8',
    ),
  );
  const cases = report.cases.filter((item: { case: string }) => item.case.startsWith('smoke_'));
  expect(cases).toHaveLength(5);
  for (const item of cases) {
    await page.goto(`/doctor/sessions/${item.session_id}`);
    await expect(
      page.locator('dd').filter({ hasText: item.normalization.original_text }).first(),
    ).toBeVisible();
    const panel = page.locator('.normalization-panel').first();
    await expect(panel).toContainText('Machine output — not clinician verified');
    if (item.status === 'normalized') {
      for (const fact of item.normalization.facts) {
        await expect(panel).toContainText(fact.normalized_display);
        await expect(panel).toContainText(
          fact.polarity === 'absent' ? 'Absent / denied' : 'Present (see certainty)',
        );
        await expect(panel).toContainText(`Reported certainty: ${fact.certainty}`);
      }
    } else {
      await expect(panel).toContainText('Normalization unavailable — needs verification');
    }
    await panel.getByText('Normalization source', { exact: true }).click();
    await expect(panel).toContainText('nvidia');
    await expect(panel).toContainText('google/gemma-4-31b-it');
    await expect(panel).toContainText('nvidia-1.0');
    expect(await panel.locator('.success').count()).toBe(0);
    if (item.case === 'smoke_en') {
      await expect(page.getByLabel('Reviewed summary', { exact: true })).toHaveAttribute(
        'readonly',
      );
      await panel.screenshot({ path: '../.runtime/screenshots/phase3b-nvidia.png' });
    }
  }
});

test('actual NVIDIA result and cursor resume without another inference call', async ({ page }) => {
  const saved = JSON.parse(await readFile('../.runtime/phase3b-resume.json', 'utf8'));
  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), saved.sessionId);
  await page.goto('/kiosk/interview');
  await expect(page.getByRole('heading', { name: saved.text })).toBeVisible();
  const response = await page.request.get(`/api/sessions/${saved.sessionId}/interview`);
  expect(response.ok()).toBeTruthy();
  const state = await response.json();
  expect(state.question.question_id).toBe(saved.questionId);
  expect(state.revision).toBe(saved.revision);
  expect(state.active_answers[0].normalization.id).toBe(saved.normalizationId);
  expect(state.active_answers[0].normalization.provider).toBe('nvidia');
});
