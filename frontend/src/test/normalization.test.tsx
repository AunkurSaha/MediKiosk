import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import App from '../App';
import { api } from '../api/client';
import type { Detail } from '../api/client';
import type { Normalization } from '../api/interview';

const raw = 'বুকে ব্যথা';
const result: Normalization = {
  id: 'normalization-id',
  source_answer_id: 'answer-id',
  source_question_id: 'chief_complaint.description',
  canonical_field: 'chief_complaint.description',
  original_language: 'bn',
  original_text: raw,
  status: 'normalized',
  reason: null,
  provider: 'mock',
  provider_version: '1.0.0',
  schema_version: '1.0',
  policy_version: '1.0',
  created_at: '2026-09-09T00:00:00Z',
  facts: [
    {
      normalized_concept: 'CHEST_PAIN',
      normalized_display: 'Chest pain',
      normalized_value: true,
      evidence: raw,
      certainty: 'certain',
      confidence: null,
      verification_status: 'machine_normalized',
    },
  ],
};
function detail(normalization: Normalization | null, confirmed = false): Detail {
  return {
    session: {
      id: 'session',
      patient_id: 'patient',
      hospital_token: 'TEST',
      language: 'bn',
      status: confirmed ? 'confirmed' : 'ready_for_review',
      created_at: '2026-09-09T00:00:00Z',
      completed_at: '2026-09-09T00:00:00Z',
    },
    patient: {
      id: 'patient',
      name: 'Synthetic Patient',
      gender: null,
      age_years: null,
      height_cm: null,
      weight_kg: null,
      demo_abha_id: null,
    },
    consent: { share_with_doctor: true, voice_processing: false, document_processing: false },
    answers: [],
    summary: {
      id: 'summary',
      generated_text: 'Original source draft',
      reviewed_text: confirmed ? 'Reviewed source' : null,
      status: confirmed ? 'confirmed' : 'generated',
      version: 1,
      confirmed_by: confirmed ? 'doctor' : null,
      confirmed_at: confirmed ? '2026-09-09T00:00:00Z' : null,
    },
    history: {
      schema_version: 1,
      flow_id: 'chest_pain',
      flow_version: '1.0.0',
      namespace: 'standard',
      selected_complaint: { en: 'Selected complaint', bn: 'সমস্যা', hi: 'समस्या' },
      selection_source: 'patient_selected',
      sections: [
        {
          section_id: 'chief_complaint',
          label: { en: 'Chief complaint', bn: 'সমস্যা', hi: 'समस्या' },
          facts: [
            {
              answer_id: 'answer-id',
              question_id: result.source_question_id,
              field: result.canonical_field,
              label: { en: 'Original question', bn: 'প্রশ্ন', hi: 'प्रश्न' },
              value: raw,
              raw_value: raw,
              source: 'typed',
              status: 'answered',
              language: 'bn',
              verification_status: 'patient_reported',
              recorded_at: result.created_at!,
              normalization,
            },
          ],
        },
      ],
    },
  };
}
beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem(
    'medikiosk.auth_user',
    JSON.stringify({
      id: '00000000-0000-4000-8000-000000000001',
      name: 'Demo Doctor',
      role: 'doctor',
      phone_number: null,
      phone_verified: false,
    }),
  );
  window.history.replaceState({}, '', '/doctor/sessions/session');
  vi.spyOn(api, 'medicalFacts').mockResolvedValue({
    medications: [],
    labs: [],
    rejected_medications: [],
    rejected_labs: [],
    counts: { unverified: 0, verified: 0, rejected: 0 },
  });
  vi.spyOn(api, 'timeline').mockResolvedValue({ known_date: [], unknown_date: [] });
  vi.spyOn(api, 'discrepancies').mockResolvedValue({ items: [] });
});

it('shows original Bengali wording, canonical label and unverified provenance separately', async () => {
  vi.spyOn(api, 'doctorDetail').mockResolvedValue(detail(result));
  render(<App />);
  expect(await screen.findByText(raw)).toHaveAttribute('lang', 'bn');
  const panel = screen.getByLabelText('Machine normalization');
  expect(within(panel).getByText('Chest pain')).toBeVisible();
  expect(within(panel).getByText('Machine output — not clinician verified')).toBeVisible();
  expect(panel.querySelector('.success')).toBeNull();
  fireEvent.click(within(panel).getByText('Normalization source'));
  expect(within(panel).getByText(/mock 1.0.0/)).toBeVisible();
  expect(within(panel).getByText(/answer-id/)).toBeVisible();
});

it.each(['unavailable', 'unrecognized', 'unknown'] as const)(
  'shows %s without hiding patient wording or inventing a concept',
  async (status) => {
    vi.spyOn(api, 'doctorDetail').mockResolvedValue(
      detail({
        ...result,
        status,
        facts: [],
        reason: status === 'unknown' ? 'explicit_unknown' : 'no_match',
      }),
    );
    render(<App />);
    expect(await screen.findByText(raw)).toBeVisible();
    const panel = screen.getByLabelText('Machine normalization');
    expect(within(panel).queryByText('Chest pain')).not.toBeInTheDocument();
    expect(
      within(panel).getByText(
        status === 'unknown' ? /no concept assigned/ : /unavailable — needs verification/,
      ),
    ).toBeVisible();
  },
);

it('summary confirmation does not relabel machine facts as clinician verified', async () => {
  vi.spyOn(api, 'doctorDetail').mockResolvedValue(detail(result, true));
  render(<App />);
  expect(await screen.findByLabelText('Reviewed summary')).toHaveAttribute('readonly');
  expect(
    within(screen.getByLabelText('Machine normalization')).getByText(
      'Machine output — not clinician verified',
    ),
  ).toBeVisible();
});

it('does not show normalization controls for deterministic typed facts', async () => {
  vi.spyOn(api, 'doctorDetail').mockResolvedValue(detail(null));
  render(<App />);
  await screen.findByText(raw);
  expect(screen.queryByLabelText('Machine normalization')).not.toBeInTheDocument();
});

it.each(['present', 'absent'] as const)(
  'shows NVIDIA provenance and %s polarity without clinical verification',
  async (polarity) => {
    const live: Normalization = {
      ...result,
      provider: 'nvidia',
      model: 'google/gemma-4-31b-it',
      prompt_version: 'nvidia-1.0',
      schema_version: '1.1',
      facts: [
        { ...result.facts[0], polarity, normalized_value: polarity === 'absent' ? false : true },
      ],
    };
    vi.spyOn(api, 'doctorDetail').mockResolvedValue(detail(live, true));
    render(<App />);
    const panel = await screen.findByLabelText('Machine normalization');
    expect(
      within(panel).getByText(
        polarity === 'absent' ? /Absent \/ denied/ : /Present \(see certainty\)/,
      ),
    ).toBeVisible();
    fireEvent.click(within(panel).getByText('Normalization source'));
    expect(within(panel).getByText(/google\/gemma-4-31b-it/)).toBeVisible();
    expect(within(panel).getByText(/nvidia-1.0/)).toBeVisible();
    expect(within(panel).getByText('Machine output — not clinician verified')).toBeVisible();
    expect(await screen.findByText(raw)).toBeVisible();
  },
);

it('keeps uncertain NVIDIA facts visibly uncertain with no invented probability', async () => {
  vi.spyOn(api, 'doctorDetail').mockResolvedValue(
    detail({
      ...result,
      provider: 'nvidia',
      facts: [
        {
          ...result.facts[0],
          certainty: 'uncertain',
          normalized_value: null,
          verification_status: 'needs_verification',
        },
      ],
    }),
  );
  render(<App />);
  const panel = await screen.findByLabelText('Machine normalization');
  expect(within(panel).getByText(/Reported certainty: uncertain/)).toBeVisible();
  expect(within(panel).queryByText(/Provider confidence/)).not.toBeInTheDocument();
});
