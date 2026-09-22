import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import ClinicalCoveragePanel from '../components/doctor/ClinicalCoveragePanel';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, coverage: vi.fn() } };
});

beforeEach(() => vi.resetAllMocks());

it('shows confirmed, document-supported, conflicted and provenance states', async () => {
  vi.mocked(api.coverage).mockResolvedValue({
    session_id: 'session-1',
    required: 12,
    confirmed: 9,
    document_supported_unconfirmed: 1,
    conflicted: 1,
    missing: 1,
    not_applicable: 0,
    fields: [
      {
        field: 'medications.details',
        label: 'Current medicines',
        required: true,
        applicable: true,
        state: 'DOCUMENT_SUPPORTED_UNCONFIRMED',
        patient_answer_id: null,
        provenance: [
          {
            evidence_id: 'evidence-1',
            source_fact_id: 'fact-1',
            source_document_id: 'document-1',
            document_filename: 'prescription.png',
            page_number: 1,
            original_extracted_value: 'Metformin 500 mg twice daily',
            verification_state: 'UNVERIFIED',
          },
        ],
      },
      {
        field: 'allergies.details',
        label: 'Allergies',
        required: true,
        applicable: true,
        state: 'CONFLICTED',
        patient_answer_id: null,
        provenance: [],
      },
    ],
  });
  render(<ClinicalCoveragePanel sessionId="session-1" />);
  expect(await screen.findByText(/9 \/ 12/)).toBeVisible();
  expect(screen.getByText(/Metformin 500 mg twice daily/).parentElement).toHaveTextContent(
    'Source: prescription.png, page 1',
  );
  expect(screen.getByText(/Allergies/).parentElement).toHaveTextContent('Needs clarification');
});
