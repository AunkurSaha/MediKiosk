import { expect, test } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';

async function createSessionWithConsent(request: APIRequestContext) {
  const id = randomUUID();
  const token = `DOC-${id.slice(0, 8)}`;
  const res = await request.post('/api/sessions', {
    data: {
      id,
      patient: { name: 'E2E Document Patient' },
      hospital_token: token,
      language: 'en',
    },
  });
  expect(res.status()).toBe(201);

  const consentRes = await request.put(`/api/sessions/${id}/consent`, {
    data: {
      share_with_doctor: true,
      document_processing: true,
      voice_processing: false,
    },
  });
  expect(consentRes.ok()).toBeTruthy();

  return { id, token };
}

test.describe('Document Upload and Extraction End-to-End Pipeline', () => {
  test('Prescription and Lab Report upload, extraction, and doctor view linkage', async ({
    page,
    request,
  }) => {
    // Generous timeout for real OCR processing
    test.setTimeout(90000);

    const { id } = await createSessionWithConsent(request);

    // 1. Visit Kiosk with this session active in sessionStorage
    await page.goto('/kiosk/language');
    await page.evaluate(
      ({ sessionId }) => {
        sessionStorage.setItem('medikiosk.session', sessionId);
      },
      { sessionId: id }
    );

    // 2. Pre-seed the first 4 answers so we are at the final question
    const answers = [
      { question_id: 'chief_complaint', field: 'chief_complaint', value: 'Chest discomfort', raw_value: 'Chest discomfort', source: 'typed', language: 'en' },
      { question_id: 'onset_duration', field: 'onset_duration', value: 'Since yesterday', raw_value: 'Since yesterday', source: 'typed', language: 'en' },
      { question_id: 'medications', field: 'medications', value: 'None reported', raw_value: 'None reported', source: 'typed', language: 'en' },
      { question_id: 'allergies', field: 'allergies', value: 'No known allergies', raw_value: 'No known allergies', source: 'typed', language: 'en' },
    ];
    for (const ans of answers) {
      await request.post(`/api/sessions/${id}/answers`, { data: ans });
    }

    // Navigate to Kiosk interview and answer question 5 interactively
    await page.goto('/kiosk/interview');
    await expect(page.getByLabel('Your answer', { exact: true })).toBeVisible({ timeout: 15000 });
    await page.getByLabel('Your answer', { exact: true }).fill('None reported');
    await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

    // After question 5 is saved, the summary view with DocumentUploader is visible
    await expect(page.getByTestId('document-uploader')).toBeVisible({ timeout: 15000 });

    // 3. Upload prescription.png fixture
    const prescriptionPath = resolve('..', 'ai', 'document_fixtures', 'prescription.png');
    const fileInput = page.getByTestId('document-file-input');
    await fileInput.setInputFiles(prescriptionPath);

    // 4. Verify extraction completed in Kiosk UI
    await expect(page.locator('.uploaded-documents-list')).toBeVisible({ timeout: 25000 });
    await expect(page.getByText('prescription.png', { exact: true })).toBeVisible();
    await expect(page.locator('.doc-badge').filter({ hasText: /completed|mock_fixture/ }).first()).toBeVisible({ timeout: 20000 });

    // 5. Verify extracted medications appear in DocumentUploader
    await expect(page.locator('.extracted-meds-list')).toBeVisible();
    await expect(page.locator('.extracted-meds-list')).toContainText('Paracetamol');
    await expect(page.locator('.extracted-meds-list')).toContainText('Amoxicillin');
    await expect(page.locator('.badge-unverified').first()).toBeVisible();

    // 6. Verify medical facts in backend
    const medFactsRes = await request.get(`/api/doctor/sessions/${id}/medical-facts`, {
      headers: { 'X-Demo-Doctor': 'true' },
    });
    expect(medFactsRes.ok()).toBeTruthy();
    const facts = await medFactsRes.json();
    expect(facts.medications.length).toBeGreaterThanOrEqual(3);
    const paracetamol = facts.medications.find(
      (m: { current: { name: string } }) => m.current.name.toLowerCase().includes('paracetamol')
    );
    expect(paracetamol).toBeDefined();
    expect(paracetamol.verification_status).toBe('unverified');

    // 7. Upload lab_report.png fixture
    await page.locator('#doc-type-select').selectOption('lab_report');
    const labPath = resolve('..', 'ai', 'document_fixtures', 'lab_report.png');
    await fileInput.setInputFiles(labPath);

    // Wait for lab report extraction to complete
    await expect(page.locator('.uploaded-documents-list')).toContainText('lab_report.png', { timeout: 25000 });
    await expect(page.locator('.extracted-labs-list')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('.extracted-labs-list')).toContainText('Hemoglobin');

    // Take screenshot of Kiosk Document Uploader with live Sarvam extractions
    await page.screenshot({ path: '../.runtime/screenshots/kiosk-document-uploader-sarvam.png', fullPage: true });

    // 8. Open Doctor document view
    await page.goto(`/doctor/sessions/${id}`);
    const viewerPanel = page.getByTestId('document-viewer-panel');
    await expect(viewerPanel).toBeVisible({ timeout: 15000 });

    // Verify source document viewer displays document tabs and content
    await expect(viewerPanel.getByRole('button', { name: /prescription\.png/ })).toBeVisible();
    await expect(viewerPanel.getByRole('button', { name: /lab_report\.png/ })).toBeVisible();
    await expect(viewerPanel).toContainText('Auxiliary Ingestion');

    // Verify medical facts section contains the unverified medications
    const factsSection = page
      .getByRole('heading', { name: 'Medical facts' })
      .locator('xpath=ancestor::section');
    await expect(factsSection).toContainText('Paracetamol');

    // Take screenshot of Doctor Workspace with Document Viewer & Medical Facts
    await page.screenshot({ path: '../.runtime/screenshots/doctor-document-viewer-sarvam.png', fullPage: true });
  });
});
