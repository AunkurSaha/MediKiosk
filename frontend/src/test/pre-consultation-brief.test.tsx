import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { Detail } from '../api/client';
import PreConsultationBrief from '../components/doctor/PreConsultationBrief';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, queueEstimate: vi.fn() } };
});

const detail = {
  session: {
    id: 'session-1',
    patient_id: 'patient-1',
    hospital_token: 'TOKEN-1',
    language: 'en',
    status: 'ready_for_review',
    created_at: '2026-09-21T00:00:00Z',
    completed_at: '2026-09-21T00:05:00Z',
  },
  patient: {
    id: 'patient-1',
    name: 'Demo Patient',
    gender: 'female',
    age_years: 42,
    height_cm: 162,
    weight_kg: 64,
    demo_abha_id: null,
  },
  consent: { share_with_doctor: true, voice_processing: false, document_processing: true },
  answers: [
    {
      id: 'answer-1',
      session_id: 'session-1',
      question_id: 'chief',
      field: 'chief_complaint.description',
      value: 'Fever since yesterday; no breathing difficulty.',
      raw_value: 'Fever since yesterday; no breathing difficulty.',
      language: 'en',
      source: 'typed',
      verification_status: 'patient_reported',
    },
  ],
  history: {
    schema_version: 1,
    flow_id: 'fever',
    flow_version: '1.0.0',
    namespace: 'standard',
    selected_complaint: { en: 'Fever', bn: 'জ্বর', hi: 'बुखार' },
    selection_source: 'patient_selected',
    sections: [
      {
        section_id: 'chief',
        label: { en: 'Current history', bn: 'ইতিহাস', hi: 'इतिहास' },
        facts: [
          {
            answer_id: 'answer-1',
            question_id: 'chief',
            field: 'chief_complaint.description',
            label: { en: 'Main concern', bn: 'মূল উদ্বেগ', hi: 'मुख्य चिंता' },
            status: 'answered',
            value: 'Fever since yesterday; no breathing difficulty.',
            raw_value: 'Fever since yesterday; no breathing difficulty.',
            source: 'typed',
            language: 'en',
            recorded_at: '2026-09-21T00:01:00Z',
          },
        ],
      },
    ],
  },
  alerts: [],
  documents: [
    {
      id: 'document-1',
      session_id: 'session-1',
      object_key: 'private-object-key',
      original_filename: 'prescription.png',
      media_type: 'image/png',
      file_size_bytes: 100,
      sha256_hash: 'private-hash',
      document_type: 'prescription',
      document_date: null,
      processing_status: 'mock_fixture',
      created_at: '2026-09-21T00:02:00Z',
      updated_at: null,
      extractions: [],
    },
  ],
  summary: {
    id: 'summary-1',
    generated_text: 'Structured summary',
    reviewed_text: null,
    status: 'generated',
    version: 1,
    confirmed_by: null,
    confirmed_at: null,
    evidence: [
      {
        statement_id: 'med-1',
        section: 'current_medications',
        statement_text: 'Metformin 500 mg · Twice Daily',
        source_type: 'medical_fact',
        source_id: 'fact-1',
        source_text: 'Metformin 500 mg Twice Daily',
        source_metadata: { document_id: 'document-1' },
        status: 'patient_confirmed',
        badge: 'Patient Confirmed',
      },
    ],
    coverage: {
      session_id: 'session-1',
      required: 6,
      confirmed: 6,
      document_supported_unconfirmed: 0,
      conflicted: 0,
      missing: 0,
      not_applicable: 0,
      fields: [],
    },
    pre_arrival_packet: {
      queue: { visit_token: 'MK-GEN-003', status: 'WAITING' },
      routing: { routing_state: 'ROUTINE_OPD' },
      conflicts: [],
    },
  },
} as unknown as Detail;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.queueEstimate).mockResolvedValue({
    session_id: 'session-1',
    doctor_id: 'doctor-1',
    doctor_name: 'Dr. Ishan Gupta',
    hospital_id: 'hospital-1',
    hospital_name: 'MediKiosk Central Hospital',
    service_date: '2026-09-21',
    visit_token: 'MK-GEN-003',
    status: 'WAITING',
    position: 3,
    patients_ahead: 2,
    estimated_wait_minutes: 20,
    is_estimate: true,
    calculation_basis: '2 patients ahead',
    policy_version: '1.0.0',
  });
});

it('renders the golden brief from loaded clinical, document, coverage, and queue data', async () => {
  render(<PreConsultationBrief detail={detail} />);
  expect(screen.getByRole('heading', { name: 'Pre-Consultation Brief' })).toBeVisible();
  expect(screen.getByText('Fever')).toBeVisible();
  expect(screen.getByText('Fever since yesterday; no breathing difficulty.')).toBeVisible();
  expect(screen.getByText('Metformin 500 mg · Twice Daily')).toBeVisible();
  expect(screen.getByText('✓ Patient confirmed')).toBeVisible();
  expect(screen.getByText('No red flags detected')).toBeVisible();
  expect(screen.getByText('1 prescription')).toBeVisible();
  expect(screen.getByText('✓ Required history complete')).toBeVisible();
  expect(screen.getByText('MK-GEN-003')).toBeVisible();
  await waitFor(() => expect(screen.getByText('Approx. waiting time: 20 min')).toBeVisible());
  expect(screen.getByText('Patient answers')).toBeVisible();
  expect(screen.getByText('Prescription')).toBeVisible();
  expect(screen.getByText('Patient-confirmed evidence')).toBeVisible();
  expect(
    screen.queryByText(/diagnosis|treatment|patient is safe|no risk/i),
  ).not.toBeInTheDocument();
});

it('does not claim confirmation or completeness when the evidence conflicts', () => {
  const conflicting = {
    ...detail,
    summary: {
      ...detail.summary!,
      evidence: detail.summary!.evidence!.map((item) => ({
        ...item,
        status: 'conflicting' as const,
      })),
      coverage: { ...detail.summary!.coverage!, confirmed: 4, conflicted: 1, missing: 1 },
      pre_arrival_packet: {
        queue: { visit_token: 'MK-GEN-003', status: 'WAITING' },
        routing: { routing_state: 'ROUTINE_OPD' },
        conflicts: [{ conflict_id: 'conflict-1' }],
      },
    },
    alerts: [
      {
        id: 'alert-1',
        session_id: 'session-1',
        hospital_token: 'TOKEN-1',
        patient_name: 'Demo Patient',
        rule_id: 'RF-1',
        rule_version: '1',
        priority: 'urgent',
        category: 'safety',
        reason: 'Potential emergency symptoms detected.',
        triggering_facts: [],
        status: 'new',
        revision: 1,
        acknowledged_at: null,
        acknowledged_by: null,
        acknowledgement_note: null,
        created_at: '2026-09-21T00:00:00Z',
        updated_at: null,
      },
    ],
  } as Detail;
  render(<PreConsultationBrief detail={conflicting} />);
  expect(screen.queryByText('✓ Patient confirmed')).not.toBeInTheDocument();
  expect(screen.queryByText('No red flags detected')).not.toBeInTheDocument();
  expect(screen.getByText('1 safety alert requires review')).toBeVisible();
  expect(screen.getByText('⚠ 1 item requires review')).toBeVisible();
  expect(screen.getByText('Conflict requires review')).toBeVisible();
  expect(screen.queryByText('✓ Required history complete')).not.toBeInTheDocument();
});

it('gracefully omits unavailable medication, document, and queue information', () => {
  const sparse = {
    ...detail,
    answers: [],
    documents: [],
    summary: null,
    history: null,
  } as Detail;
  vi.mocked(api.queueEstimate).mockRejectedValue(new Error('not available'));
  render(<PreConsultationBrief detail={sparse} />);
  expect(screen.getByRole('heading', { name: 'Pre-Consultation Brief' })).toBeVisible();
  expect(screen.queryByText('Current medication')).not.toBeInTheDocument();
  expect(screen.queryByText('Documents')).not.toBeInTheDocument();
  expect(screen.queryByText('Queue')).not.toBeInTheDocument();
  expect(screen.queryByText('Patient confirmed')).not.toBeInTheDocument();
});
