import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import type { InterviewState } from '../src/api/interview';
import requireMock from './require-mock';

test.beforeAll(async () => {
  await requireMock();
});

async function injectMockMediaRecorder(page: Page) {
  await page.addInitScript(() => {
    class MockMediaRecorder {
      state = 'inactive';
      ondataavailable: ((e: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      static isTypeSupported() {
        return true;
      }
      constructor() {}
      start() {
        this.state = 'recording';
      }
      stop() {
        this.state = 'inactive';
        if (this.ondataavailable) {
          this.ondataavailable({
            data: new Blob(['RIFF....WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00data\x00\x00\x00\x00'], {
              type: 'audio/webm',
            }),
          });
        }
        if (this.onstop) {
          this.onstop();
        }
      }
    }
    (window as unknown as { MediaRecorder: unknown }).MediaRecorder = MockMediaRecorder;

    if (!navigator.mediaDevices) {
      (navigator as unknown as { mediaDevices: unknown }).mediaDevices = {};
    }
    navigator.mediaDevices.getUserMedia = async () => {
      return {
        getTracks: () => [{ stop: () => {} }],
      };
    };
  });
}

async function prepare(page: Page, language: 'bn' | 'en') {
  const id = crypto.randomUUID();
  expect(
    (
      await page.request.post('/api/sessions', {
        data: {
          id,
          patient: { name: 'Synthetic Speech Patient', demo_abha_id: null },
          hospital_token: 'PHASE4A-' + Date.now(),
          language,
        },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await page.request.put(`/api/sessions/${id}/consent`, {
        data: { share_with_doctor: true, voice_processing: true, document_processing: false },
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

test.describe('Phase 4A Speech and TTS E2E', () => {
  test('English voice intake journey records, confirms, persists source=voice and triggers normalization', async ({
    page,
  }) => {
    test.setTimeout(60000);
    await injectMockMediaRecorder(page);
    const id = await prepare(page, 'en');

    await page.goto('/kiosk/language');
    await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
    await page.goto('/kiosk/interview');

    // Select primary complaint: "Chest pain"
    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    // Now at short_text question: chief_complaint.description
    await expect(page.getByRole('button', { name: /Speak/i })).toBeVisible();

    // Start voice recording
    await page.getByRole('button', { name: /Speak/i }).click();
    await expect(page.getByRole('button', { name: /Finish speaking/i })).toBeVisible();

    // Stop recording and trigger transcription
    const transcribePromise = page.waitForResponse(
      (r) => r.url().includes('/speech/transcribe') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /Finish speaking/i }).click();
    const transcribeRes = await transcribePromise;
    expect(transcribeRes.ok()).toBeTruthy();

    // Candidate review card appears with candidate transcript
    await expect(page.getByText('You said:')).toBeVisible();
    await expect(page.getByText(/chest pain/i)).toBeVisible();

    // Explicit patient confirmation
    const answerPromise = page.waitForResponse(
      (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /Confirm/i }).click();
    const answerRes = await answerPromise;
    expect(answerRes.ok()).toBeTruthy();

    // Verify interview state persisted source = 'voice'
    const state = await current(page, id);
    const voiceAnswer = state.active_answers.find((a) => a.field === 'chief_complaint.description');
    expect(voiceAnswer).toBeDefined();
    expect(voiceAnswer?.source).toBe('voice');
    expect(voiceAnswer?.raw_value).toBe('chest pain');
    expect(voiceAnswer?.normalization?.status).toBe('normalized');
    expect(voiceAnswer?.normalization?.facts[0].normalized_concept).toBe('CHEST_PAIN');

    await mkdir('../.runtime/screenshots', { recursive: true });
    await page.screenshot({ path: '../.runtime/screenshots/speech-en-confirmed.png', fullPage: true });
  });

  test('Bengali voice intake journey records, confirms, persists source=voice and triggers normalization', async ({
    page,
  }) => {
    test.setTimeout(60000);
    await injectMockMediaRecorder(page);
    const id = await prepare(page, 'bn');

    await page.goto('/kiosk/language');
    await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
    await page.goto('/kiosk/interview');

    // Select primary complaint in Bengali
    await page.getByRole('button', { name: 'বুকে ব্যথা', exact: true }).click();

    // At short_text question: voice button present in Bengali
    await expect(page.getByRole('button', { name: /বলুন/i })).toBeVisible();

    // Start recording
    await page.getByRole('button', { name: /বলুন/i }).click();
    await expect(page.getByRole('button', { name: /বলা শেষ করুন/i })).toBeVisible();

    // Stop recording
    const transcribePromise = page.waitForResponse(
      (r) => r.url().includes('/speech/transcribe') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /বলা শেষ করুন/i }).click();
    const transcribeRes = await transcribePromise;
    expect(transcribeRes.ok()).toBeTruthy();

    // Candidate review card in Bengali
    await expect(page.getByText('আপনি বলেছেন:')).toBeVisible();
    await expect(page.getByText(/বুকে ব্যথা/)).toBeVisible();

    // Explicit confirmation
    const answerPromise = page.waitForResponse(
      (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: /নিশ্চিত করুন/i }).click();
    const answerRes = await answerPromise;
    expect(answerRes.ok()).toBeTruthy();

    // Verify interview state persisted source = 'voice'
    const state = await current(page, id);
    const voiceAnswer = state.active_answers.find((a) => a.field === 'chief_complaint.description');
    expect(voiceAnswer).toBeDefined();
    expect(voiceAnswer?.source).toBe('voice');
    expect(voiceAnswer?.raw_value).toBe('বুকে ব্যথা');
    expect(voiceAnswer?.normalization?.status).toBe('normalized');
    expect(voiceAnswer?.normalization?.facts[0].normalized_concept).toBe('CHEST_PAIN');
  });

  test('ASR failure gracefully falls back to typed answer', async ({ page }) => {
    test.setTimeout(60000);
    await injectMockMediaRecorder(page);
    const id = await prepare(page, 'en');

    await page.goto('/kiosk/language');
    await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
    await page.goto('/kiosk/interview');
    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    // Mock ASR endpoint failure (e.g. 503 service unavailable)
    await page.route('**/speech/transcribe', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Provider unavailable' }),
      });
    });

    await page.getByRole('button', { name: /Speak/i }).click();
    await page.getByRole('button', { name: /Finish speaking/i }).click();

    // Verify graceful degradation error is shown
    await expect(
      page.getByText('Voice input is unavailable. Please type your answer.'),
    ).toBeVisible();

    // Patient types answer instead
    await page.getByLabel('Your answer').fill('Typed fallback after voice failure');
    const answerPromise = page.waitForResponse(
      (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save and continue' }).click();
    expect((await answerPromise).ok()).toBeTruthy();

    const state = await current(page, id);
    const typedAnswer = state.active_answers.find((a) => a.field === 'chief_complaint.description');
    expect(typedAnswer?.source).toBe('typed');
    expect(typedAnswer?.raw_value).toBe('Typed fallback after voice failure');
  });

  test('Patient edits candidate transcript before confirming', async ({ page }) => {
    test.setTimeout(60000);
    await injectMockMediaRecorder(page);
    const id = await prepare(page, 'en');

    await page.goto('/kiosk/language');
    await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
    await page.goto('/kiosk/interview');
    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    await page.getByRole('button', { name: /Speak/i }).click();
    await page.getByRole('button', { name: /Finish speaking/i }).click();

    await expect(page.getByText('You said:')).toBeVisible();

    // Click Edit button
    await page.getByRole('button', { name: /Edit/i }).click();

    // Candidate card disappears, text area is populated with transcript
    await expect(page.getByText('You said:')).not.toBeVisible();
    const textarea = page.getByLabel('Your answer');
    await expect(textarea).toHaveValue('chest pain');

    // Patient edits wording
    await textarea.fill('chest pain since yesterday evening');
    const answerPromise = page.waitForResponse(
      (r) => r.url().endsWith('/interview/answers') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Save and continue' }).click();
    expect((await answerPromise).ok()).toBeTruthy();

    const state = await current(page, id);
    const editedAnswer = state.active_answers.find((a) => a.field === 'chief_complaint.description');
    expect(editedAnswer?.source).toBe('typed');
    expect(editedAnswer?.raw_value).toBe('chest pain since yesterday evening');
  });

  test('TTS playback request synthesizes localized question text', async ({ page }) => {
    test.setTimeout(60000);
    await injectMockMediaRecorder(page);
    const id = await prepare(page, 'en');

    await page.goto('/kiosk/language');
    await page.evaluate((id) => sessionStorage.setItem('medikiosk.session', id), id);
    await page.goto('/kiosk/interview');
    await page.getByRole('button', { name: 'Chest pain', exact: true }).click();

    // Speaker button is visible
    const listenButton = page.getByRole('button', { name: /Listen/i });
    await expect(listenButton).toBeVisible();

    const synthPromise = page.waitForResponse(
      (r) => r.url().includes('/speech/synthesize') && r.request().method() === 'POST',
    );
    await listenButton.click();
    const synthRes = await synthPromise;
    expect(synthRes.ok()).toBeTruthy();

    const synthBody = await synthRes.json();
    expect(synthBody.status).toBe('success');
    expect(synthBody.media_type).toBe('audio/wav');
    expect(synthBody.provider).toBe('mock');
    expect(synthBody.audio_base64).toBeTruthy();

    // Question remains interactive
    await expect(page.getByLabel('Your answer')).toBeVisible();
  });
});
