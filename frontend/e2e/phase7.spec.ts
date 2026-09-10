import { expect, test } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

async function createSession(request: APIRequestContext, medication?: string) {
  const id = randomUUID();
  expect(
    (
      await request.post('/api/sessions', {
        data: {
          id,
          patient: { name: 'Synthetic Phase 7 review' },
          hospital_token: `P7-${id.slice(0, 8)}`,
          language: 'en',
        },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await request.put(`/api/sessions/${id}/consent`, {
        data: { share_with_doctor: true, document_processing: true, voice_processing: false },
      })
    ).ok(),
  ).toBeTruthy();
  if (medication) {
    expect(
      (
        await request.post(`/api/sessions/${id}/answers`, {
          data: {
            question_id: 'medications',
            field: 'medications',
            value: medication,
            raw_value: medication,
            source: 'typed',
            language: 'en',
          },
        })
      ).ok(),
    ).toBeTruthy();
  }
  return id;
}

async function upload(request: APIRequestContext, id: string, fixtureName: string) {
  const bytes = await readFile(`../ai/document_fixtures/${fixtureName}.png`);
  const response = await request.post(`/api/sessions/${id}/documents`, {
    multipart: {
      file: { name: 'synthetic-source.png', mimeType: 'image/png', buffer: bytes },
    },
  });
  expect(response.status()).toBe(201);
  const document = await response.json();
  expect(document.processing_status).toBe('mock_fixture');
  return document;
}

test('prescription facts are visible, source-linked, and split across known/unknown timeline dates', async ({
  page,
  request,
}) => {
  const id = await createSession(request);
  await upload(request, id, 'prescription');
  const factsResponse = await request.get(`/api/doctor/sessions/${id}/medical-facts`, {
    headers: { 'X-Demo-Doctor': 'true' },
  });
  expect(factsResponse.ok()).toBeTruthy();
  expect((await factsResponse.json()).medications.length).toBeGreaterThan(0);
  expect((await request.get(`/api/doctor/sessions/${id}/medical-facts`)).status()).toBe(401);
  await page.goto(`/doctor/sessions/${id}`);
  const facts = page
    .getByRole('heading', { name: 'Medical facts' })
    .locator('xpath=ancestor::section');
  await expect(facts).toContainText('Paracetamol');
  await expect(facts).toContainText('Needs verification');
  await facts.getByRole('link', { name: 'View source document' }).first().click();
  await expect(page.getByTestId('document-viewer-panel')).toContainText('synthetic-source.png');
  const timeline = page
    .getByRole('heading', { name: 'Timeline' })
    .locator('xpath=ancestor::section');
  await expect(timeline).toContainText('Document: prescription');
  await expect(timeline.getByRole('heading', { name: 'Unknown date' })).toBeVisible();
  await expect(timeline).toContainText('Medication:');
  await expect(timeline).toContainText('Date not reported');
});

test('lab fixture keeps an absent flag and observation date as not reported on mobile', async ({
  page,
  request,
}) => {
  const id = await createSession(request);
  await upload(request, id, 'lab_missing_flag');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/doctor/sessions/${id}`);
  const facts = page
    .getByRole('heading', { name: 'Medical facts' })
    .locator('xpath=ancestor::section');
  await expect(facts).toContainText('Hemoglobin');
  await expect(facts).toContainText('Source flag');
  await expect(facts).toContainText('Not reported');
  const timeline = page
    .getByRole('heading', { name: 'Timeline' })
    .locator('xpath=ancestor::section');
  await expect(timeline).toContainText('Lab: Hemoglobin');
  await expect(timeline).toContainText('Date not reported');
});

test('patient and prescription mismatch is shown only as a possible discrepancy', async ({
  page,
  request,
}) => {
  const id = await createSession(request, 'Ibuprofen 200 mg');
  await upload(request, id, 'prescription');
  await page.goto(`/doctor/sessions/${id}`);
  const discrepancies = page
    .getByRole('heading', { name: 'Discrepancies' })
    .locator('xpath=ancestor::section');
  await expect(
    discrepancies.getByText('Possible discrepancy — requires clinician review.').first(),
  ).toBeVisible();
  await expect(discrepancies).toContainText('Patient-reported medication list');
  await expect(discrepancies).toContainText('Document-derived medication');
  await expect(discrepancies).not.toContainText(/diagnosis|non-compliant|prescribing error/i);
});

test('fact correction, verification, and rejection preserve the original source', async ({
  page,
  request,
}) => {
  const id = await createSession(request);
  const document = await upload(request, id, 'prescription');
  await page.goto(`/doctor/sessions/${id}`);
  const paracetamol = page.locator('.medical-fact-card').filter({
    has: page.locator('.fact-heading h4').filter({ hasText: 'Paracetamol' }),
  });
  await paracetamol.getByRole('button', { name: 'Correct fields' }).click();
  await paracetamol.getByLabel('Dosage').fill('750 mg');
  await paracetamol.getByRole('button', { name: 'Verify and save correction' }).click();
  await expect(paracetamol).toContainText('Verified');
  await expect(paracetamol).toContainText('750 mg');
  await expect(paracetamol).toContainText('Original extraction retained');
  await paracetamol.getByText('Raw source').click();
  await expect(paracetamol).toContainText('Paracetamol 500mg');

  const amoxicillin = page.locator('.medical-fact-card').filter({
    has: page.locator('.fact-heading h4').filter({ hasText: 'Amoxicillin' }),
  });
  await amoxicillin.getByRole('button', { name: 'Reject' }).click();
  await page.getByText('Rejected facts (1)').click();
  const rejected = page
    .locator('.rejected-facts-grid')
    .locator('.medical-fact-card')
    .filter({
      has: page.locator('.fact-heading h4').filter({ hasText: 'Amoxicillin' }),
    });
  await expect(rejected).toContainText('Rejected');
  await writeFile(
    '../.runtime/phase7-reference.json',
    JSON.stringify({ sessionId: id, documentId: document.id }),
  );
});
