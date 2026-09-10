import { test, expect } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';

for (const fixture of ['prescription', 'lab_missing_flag']) {
  test(`Phase 7 ${fixture}: upload, persisted source facts and doctor display`, async ({
    page,
    request,
  }) => {
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
    expect(
      (
        await request.put(`/api/sessions/${id}/interview/flow`, { data: { flow_id: 'chest_pain' } })
      ).ok(),
    ).toBeTruthy();
    const bytes = await readFile(`../ai/document_fixtures/${fixture}.png`);
    const response = await request.post(`/api/sessions/${id}/documents`, {
      multipart: { file: { name: 'synthetic-source.png', mimeType: 'image/png', buffer: bytes } },
    });
    expect(response.status()).toBe(201);
    const doc = await response.json();
    expect(doc.processing_status).toBe('mock_fixture');
    const result = await promisify(execFile)(
      resolve('../backend/.venv/Scripts/python.exe'),
      [resolve('../scripts/verify-phase7-record.py'), id, doc.id],
      { cwd: resolve('../backend') },
    );
    expect(JSON.parse(result.stdout)).toMatchObject({ source_preserved: true, unverified: true });
    await page.goto(`/doctor/sessions/${id}`);
    const panel = page.getByTestId('document-viewer-panel');
    await expect(panel).toContainText('Synthetic mock output');
    await expect(panel).toContainText(fixture === 'prescription' ? 'Paracetamol' : 'Hemoglobin');
    expect((await request.get(`/api/sessions/${id}/documents`)).status()).toBe(401);
  });
}
