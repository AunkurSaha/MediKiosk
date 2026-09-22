import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { prepare } from './phase4-helpers';

test('document context adds confirmation and avoids repeating the generic medication question', async ({
  page,
}) => {
  const { sessionId, api, route } = await prepare(page, false);
  await api.put(`/api/sessions/${sessionId}/consent`, {
    data: { share_with_doctor: true, voice_processing: false, document_processing: true },
  });
  const facilityId = route.recommendations[0].facility_id;
  await api.put(`/api/sessions/${sessionId}/mediroute/facility`, {
    data: { facility_id: facilityId },
  });
  const match = await (await api.get(`/api/sessions/${sessionId}/doctor-match`)).json();
  await api.put(`/api/sessions/${sessionId}/doctor-match/selection`, {
    data: { doctor_id: match.recommendations[0].doctor_id },
  });

  const bytes = await readFile('../ai/document_fixtures/metformin_prescription.png');
  const uploaded = await api.post(`/api/sessions/${sessionId}/documents`, {
    multipart: {
      file: { name: 'golden-prescription.png', mimeType: 'image/png', buffer: bytes },
    },
  });
  expect(uploaded.status()).toBe(201);
  const labBytes = await readFile('../ai/document_fixtures/fasting_glucose_lab.png');
  const labUploaded = await api.post(`/api/sessions/${sessionId}/documents`, {
    multipart: {
      file: { name: 'golden-lab.png', mimeType: 'image/png', buffer: labBytes },
    },
  });
  expect(labUploaded.status()).toBe(201);

  let state = await (await api.get(`/api/sessions/${sessionId}/interview`)).json();
  expect(state.question.question_id).toBe('chief_complaint.description');
  state = await (
    await api.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: state.revision,
        question_id: state.question.question_id,
        status: 'answered',
        value: 'Chest discomfort for clinical assessment',
        raw_value: 'Chest discomfort for clinical assessment',
        source: 'typed',
        language: 'en',
      },
    })
  ).json();
  expect(state.question.origin).toBe('document_confirmation');
  expect(state.document_confirmation.question_source).toBe('DOCUMENT_CONFIRMATION');

  state = await (
    await api.post(`/api/sessions/${sessionId}/interview/answers`, {
      data: {
        request_id: crypto.randomUUID(),
        expected_revision: state.revision,
        question_id: state.question.question_id,
        status: 'answered',
        value: 'yes',
        raw_value: 'Yes',
        source: 'touch',
        language: 'en',
      },
    })
  ).json();
  expect(state.question?.field).not.toBe('medications.any');
  expect(state.question?.field).not.toBe('medications.details');

  const coverage = await (await api.get(`/api/sessions/${sessionId}/coverage`)).json();
  expect(
    coverage.fields.find((field: { field: string }) => field.field === 'medications.any').state,
  ).toBe('CONFIRMED');
  const metrics = await (await api.get(`/api/sessions/${sessionId}/coverage/demo-metrics`)).json();
  expect(metrics.questions_avoided).toBeGreaterThan(0);
  expect(metrics.confirmation_questions_added).toBe(1);
});
