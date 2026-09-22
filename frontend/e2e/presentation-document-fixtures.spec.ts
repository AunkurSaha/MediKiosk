import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';

async function openFeverInterview(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Continue as patient' }).click();
  await expect(page).toHaveURL(/\/kiosk\/language/);

  const id = randomUUID();
  const created = await page.request.post('/api/sessions', {
    data: {
      id,
      patient: { name: 'Recording Patient' },
      hospital_token: `REC-${id.slice(0, 8)}`,
      language: 'en',
      hospital_id: '10000000-0000-4000-8000-000000000001',
    },
  });
  expect(created.status()).toBe(201);
  expect(
    (
      await page.request.put(`/api/sessions/${id}/consent`, {
        data: {
          share_with_doctor: true,
          document_processing: true,
          voice_processing: false,
        },
      })
    ).ok(),
  ).toBeTruthy();
  const flowResponse = await page.request.put(`/api/sessions/${id}/interview/flow`, {
    data: { flow_id: 'fever' },
  });
  expect(flowResponse.ok(), await flowResponse.text()).toBeTruthy();

  await page.goto('/kiosk/language');
  await page.evaluate((sessionId) => sessionStorage.setItem('medikiosk.session', sessionId), id);
  await page.goto('/kiosk/interview');
  await expect(page.getByTestId('document-uploader')).toBeVisible({ timeout: 20_000 });
  return id;
}

test.describe('presentation document fixtures', () => {
  test('uploads both supplied files through the browser and preserves exact extracted facts', async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const sessionId = await openFeverInterview(page);
    const input = page.getByTestId('document-file-input');

    await input.setInputFiles(
      resolve('..', 'ai', 'document_fixtures', 'recording_prescription.png'),
    );
    await expect(page.getByText('Information found in your prescription')).toBeVisible({
      timeout: 25_000,
    });
    const prescription = page
      .getByTestId('uploaded-documents-list')
      .locator('.uploaded-document-card')
      .filter({ hasText: 'recording_prescription.png' });
    await expect(prescription).toContainText('Ankan Bera');
    await expect(prescription).toContainText('Racecadotril');
    await expect(prescription).toContainText('100 mg');
    await expect(prescription).toContainText('Take 1 tablet TDS after food for 3 days.');
    await expect(prescription).toContainText('Azithromycin');
    await expect(prescription).toContainText('Ondansetron');
    await expect(prescription).toContainText('Paracetamol');
    await expect(prescription).toContainText('Probiotic Capsule');

    await page.locator('#doc-type-select').selectOption('lab_report');
    await input.setInputFiles(resolve('..', 'ai', 'document_fixtures', 'recording_lab_report.jpg'));
    const lab = page
      .getByTestId('uploaded-documents-list')
      .locator('.uploaded-document-card')
      .filter({ hasText: 'recording_lab_report.jpg' });
    await expect(lab).toContainText('Master Ayan Bera', { timeout: 25_000 });
    await expect(lab).toContainText('Hemoglobin');
    await expect(lab).toContainText('13.9 g/dL');
    await expect(lab).toContainText('Total Leucocyte Count');
    await expect(lab).toContainText('6.9 thousands/c.mm');
    await expect(lab).toContainText('E.S.R. (Westergren), 1st Hr.');
    await expect(lab).toContainText('20 mm');

    const documentsResponse = await page.request.get(`/api/sessions/${sessionId}/documents`);
    expect(documentsResponse.ok()).toBeTruthy();
    const persisted = await documentsResponse.json();
    const persistedExtractions = persisted.documents.flatMap(
      (document: { extractions: Array<{ structured_json: Record<string, unknown> }> }) =>
        document.extractions.map((extraction) => extraction.structured_json),
    );
    expect(
      persistedExtractions.some((structured: { medications?: Array<{ name: string }> }) =>
        structured.medications?.some((medication) => medication.name === 'Azithromycin'),
      ),
    ).toBeTruthy();
    expect(
      persistedExtractions.some(
        (structured: { observations?: Array<{ test_name: string; value: string }> }) =>
          structured.observations?.some(
            (observation) => observation.test_name === 'Hemoglobin' && observation.value === '13.9',
          ),
      ),
    ).toBeTruthy();

    await page.screenshot({
      path: '../.runtime/screenshots/presentation-document-extraction.png',
      fullPage: true,
    });
  });

  test('offers replace and continue recovery for a non-matching file', async ({ page }) => {
    test.setTimeout(60_000);
    await openFeverInterview(page);
    const fixture = readFileSync(
      resolve('..', 'ai', 'document_fixtures', 'recording_prescription.png'),
    );
    const modified = Buffer.concat([fixture, Buffer.from('modified')]);

    await page.getByTestId('document-file-input').setInputFiles({
      name: 'recording_prescription.png',
      mimeType: 'image/png',
      buffer: modified,
    });
    await expect(page.getByText(/could not extract information/i)).toBeVisible({ timeout: 25_000 });
    await expect(page.getByRole('button', { name: 'Replace file' })).toBeVisible();
    await page.getByRole('button', { name: 'Continue without this document' }).click();
    await expect(page.getByText(/could not extract information/i)).toBeHidden();
  });
});
