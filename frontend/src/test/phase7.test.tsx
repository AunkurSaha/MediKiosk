import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ClinicalEvidencePanel from '../components/doctor/ClinicalEvidencePanel';
import { ApiError, api } from '../api/client';
import type { MedicalFactsResponse, MedicationFactRecord } from '../api/client';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    api: Object.fromEntries(Object.keys(actual.api).map((key) => [key, vi.fn()])),
  };
});

const sessionId = '11111111-1111-4111-8111-111111111111';
const medication: MedicationFactRecord = {
  id: '22222222-2222-4222-8222-222222222222',
  fact_type: 'medication',
  original: {
    name: 'Metformin',
    dosage: '500 mg',
    unit: null,
    route: null,
    frequency: 'BD',
    duration: null,
    start_date: null,
    end_date: null,
    instructions: null,
  },
  current: {
    name: 'Metformin',
    dosage: '500 mg',
    unit: null,
    route: null,
    frequency: 'BD',
    duration: null,
    start_date: null,
    end_date: null,
    instructions: null,
  },
  source: {
    source_type: 'document',
    source_id: 'extraction-1',
    document_id: 'document-1',
    extraction_id: 'extraction-1',
    document_filename: 'synthetic-prescription.png',
    raw_text: 'Rx: Metformin 500 mg BD',
    source_location: null,
  },
  verification_status: 'unverified',
  review_version: 0,
  verified_by: null,
  verified_at: null,
  verification_notes: null,
  revisions: [],
};

const facts: MedicalFactsResponse = {
  medications: [medication],
  labs: [],
  rejected_medications: [],
  rejected_labs: [],
  counts: { unverified: 1, verified: 0, rejected: 0 },
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.medicalFacts).mockResolvedValue(facts);
  vi.mocked(api.timeline).mockResolvedValue({
    known_date: [
      {
        id: 'timeline-known',
        event_type: 'document',
        canonical_label: 'Document: prescription',
        event_timestamp: '2026-08-15T00:00:00Z',
        date_status: 'known',
        date_precision: 'day',
        source: medication.source,
        verification_status: 'unverified',
      },
    ],
    unknown_date: [
      {
        id: 'timeline-unknown',
        event_type: 'medication',
        canonical_label: 'Medication: Metformin',
        event_timestamp: null,
        date_status: 'unknown',
        date_precision: 'unknown',
        source: medication.source,
        verification_status: 'unverified',
      },
    ],
  });
  vi.mocked(api.discrepancies).mockResolvedValue({ items: [] });
  vi.mocked(api.reviewMedicationFact).mockResolvedValue({
    ...medication,
    verification_status: 'verified',
    review_version: 1,
  });
});

describe('Phase 7 clinical evidence', () => {
  it('renders known and unknown timeline entries with source and verification badges', async () => {
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(await screen.findByRole('heading', { name: 'Medical facts' })).toBeVisible();
    expect(screen.getByText('Needs verification')).toBeVisible();
    expect(screen.getAllByText('synthetic-prescription.png').length).toBeGreaterThan(0);
    const timeline = screen.getByRole('heading', { name: 'Timeline' }).closest('section')!;
    expect(within(timeline).getByText('Document: prescription')).toBeVisible();
    expect(within(timeline).getByRole('heading', { name: 'Unknown date' })).toBeVisible();
    expect(within(timeline).getByText('Medication: Metformin')).toBeVisible();
    expect(within(timeline).getByText(/Date not reported/)).toBeVisible();
  });

  it('shows an explicit no-discrepancy state without treating missing evidence as agreement', async () => {
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(await screen.findByText(/Missing evidence is not treated as agreement/)).toBeVisible();
  });

  it('renders a possible discrepancy with patient and document sides', async () => {
    vi.mocked(api.discrepancies).mockResolvedValue({
      items: [
        {
          discrepancy_id: 'discrepancy-1',
          type: 'MEDICATION_MISSING_FROM_PATIENT_REPORT',
          workflow_priority: 'routine_review',
          source_a: {
            source_type: 'patient_answer',
            source_id: 'answer-1',
            label: 'Patient-reported medication list',
            displayed_value: 'Aspirin',
            document_id: null,
            extraction_id: null,
            raw_text: 'Aspirin',
          },
          source_b: {
            source_type: 'document_fact',
            source_id: medication.id,
            label: 'Document-derived medication',
            displayed_value: 'Metformin',
            document_id: 'document-1',
            extraction_id: 'extraction-1',
            raw_text: 'Rx: Metformin',
          },
          reason:
            'Patient-reported medication list does not include Metformin found in a prescription document.',
          status: 'open',
          verification_state: 'requires_clinician_review',
        },
      ],
    });
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(
      await screen.findByText('Possible discrepancy — requires clinician review.'),
    ).toBeVisible();
    expect(screen.getByText('Patient-reported medication list')).toBeVisible();
    expect(screen.getByText('Document-derived medication')).toBeVisible();
    expect(screen.queryByText(/non-compliant/i)).not.toBeInTheDocument();
  });

  it('submits an optimistic fact correction while retaining the source display', async () => {
    const user = userEvent.setup();
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    await user.click(await screen.findByRole('button', { name: 'Correct fields' }));
    fireEvent.change(screen.getByLabelText('Dosage'), { target: { value: '750 mg' } });
    await user.click(screen.getByRole('button', { name: 'Verify and save correction' }));
    await waitFor(() =>
      expect(api.reviewMedicationFact).toHaveBeenCalledWith(
        sessionId,
        medication.id,
        0,
        'verified',
        expect.objectContaining({ dosage: '750 mg' }),
        undefined,
      ),
    );
    expect(screen.getAllByText('synthetic-prescription.png').length).toBeGreaterThan(0);
  });

  it('shows loading and recoverable error states, including unauthorized failures', async () => {
    vi.mocked(api.medicalFacts).mockImplementation(() => new Promise(() => undefined));
    const { unmount } = render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading clinical evidence');
    unmount();
    vi.mocked(api.medicalFacts).mockRejectedValue(new ApiError('AUTH_REQUIRED', 401));
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible();
  });

  it('keeps the evidence sections usable in a mobile viewport', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    render(<ClinicalEvidencePanel sessionId={sessionId} locked={false} />);
    expect(await screen.findByRole('heading', { name: 'Medical facts' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Timeline' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Discrepancies' })).toBeVisible();
  });
});
