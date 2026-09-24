import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from '../api/client';
import PatientEvidenceSearch from '../components/doctor/PatientEvidenceSearch';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, searchPatientEvidence: vi.fn() } };
});

it('renders a structured answer and inspectable source cards', async () => {
  vi.mocked(api.searchPatientEvidence).mockResolvedValue({
    answer: 'Metformin 500 mg twice daily is recorded as patient-confirmed medication evidence.',
    evidence: [
      {
        chunk_id: 'chunk-1',
        text: 'Medication: Metformin\nStrength: 500 mg\nFrequency: twice daily',
        source_type: 'PRESCRIPTION',
        source_record_id: 'evidence-1',
        session_id: 'session-1',
        document_id: 'document-1',
        source_filename: 'prescription.png',
        page_number: 1,
        verification_status: 'PATIENT_CONFIRMED',
        timestamp: '2026-09-22T10:00:00Z',
        similarity: 0.9,
        score: 1.2,
        clinician_verified: false,
        is_current: true,
        is_conflicted: false,
        provenance: { extractor: 'mock', document_extraction_id: 'extraction-1' },
        metadata: { evidence_type: 'medication', document_evidence_id: 'original-evidence-1' },
      },
    ],
    patient_id: 'patient-1',
    query: 'Show medication evidence',
    intent: 'MEDICATION',
    retrieval_strategy: 'patient_scoped_hybrid',
    embedding_provider: 'mock',
    embedding_model: 'mock',
    index_latency_ms: 2,
    embedding_latency_ms: 1,
    retrieval_latency_ms: 3,
    generation_latency_ms: 0,
    total_latency_ms: 6,
    retrieval_mode: 'deterministic_patient_scoped',
    fallback_used: true,
    disclaimer: 'Retrieved patient evidence only. No diagnosis or treatment recommendation.',
    results: [],
  });

  render(<PatientEvidenceSearch sessionId="session-1" />);
  fireEvent.click(screen.getByRole('button', { name: 'Search evidence' }));

  await waitFor(() =>
    expect(api.searchPatientEvidence).toHaveBeenCalledWith('session-1', 'Show medication evidence'),
  );
  expect(screen.getByText(/patient-confirmed medication evidence/i)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Supporting Evidence' })).toBeInTheDocument();
  expect(screen.getByText('prescription.png', { exact: false })).toBeInTheDocument();
  expect(screen.getByText('Why is this here?')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Why is this here?'));
  expect(screen.getByText('Document extraction')).toBeInTheDocument();
  expect(screen.getByText('extraction-1')).toBeInTheDocument();
  expect(screen.getByText('Original document evidence')).toBeInTheDocument();
  expect(screen.getByText('original-evidence-1')).toBeInTheDocument();
  expect(screen.queryByText(/\{"extractor"/)).not.toBeInTheDocument();
});

it('shows a safe failure state without inventing evidence', async () => {
  vi.mocked(api.searchPatientEvidence).mockRejectedValue(new Error('offline'));
  render(<PatientEvidenceSearch sessionId="session-2" />);
  fireEvent.click(screen.getByRole('button', { name: 'Search evidence' }));
  expect(
    await screen.findByText('Evidence search is temporarily unavailable.'),
  ).toBeInTheDocument();
  expect(screen.queryByText('Supporting Evidence')).not.toBeInTheDocument();
});
