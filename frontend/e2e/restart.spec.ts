import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('retained adaptive interview resumes from PostgreSQL', async ({ page }) => {
  const saved = JSON.parse(await readFile('../.runtime/phase2-resume.json', 'utf8'));
  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), saved.sessionId);
  await page.goto('/kiosk/interview');
  await expect(page.getByRole('heading', { name: saved.text })).toBeVisible();
  const response = await page.request.get(`/api/sessions/${saved.sessionId}/interview`);
  const current = await response.json();
  expect(current.question.question_id).toBe(saved.questionId);
  expect(current.revision).toBe(saved.revision);
  expect(current.active_answers).toHaveLength(2);
});

test('normalized source and adaptive cursor resume together from PostgreSQL', async ({ page }) => {
  const saved = JSON.parse(await readFile('../.runtime/phase3a-resume.json', 'utf8'));
  await page.goto('/kiosk/language');
  await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), saved.sessionId);
  await page.goto('/kiosk/interview');
  await expect(page.getByRole('heading', { name: saved.text })).toBeVisible();
  const response = await page.request.get(`/api/sessions/${saved.sessionId}/interview`);
  const current = await response.json();
  expect(current.question.question_id).toBe(saved.questionId);
  expect(current.revision).toBe(saved.revision);
  expect(current.active_answers[0].normalization.id).toBe(saved.normalizationId);
  expect(current.active_answers[0].normalization.facts[0].normalized_concept).toBe('CHEST_PAIN');
  expect(current.flow_id).toBe('fever');
});
