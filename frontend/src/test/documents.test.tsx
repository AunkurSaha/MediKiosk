import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from '../api/client';
import DocumentUploader from '../components/kiosk/DocumentUploader';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      uploadDocument: vi.fn(),
      documents: vi.fn().mockResolvedValue({
        documents: [
          {
            id: 'fixture',
            original_filename: 'historical-mock.png',
            document_type: 'lab_report',
            processing_status: 'completed',
            extractions: [
              {
                id: 'extraction',
                extractor: 'mock',
                confidence: 0.95,
                verification_status: 'unverified',
                structured_json: {
                  observations: [{ test_name: 'Hemoglobin', value: '10.5', flag: null }],
                },
              },
            ],
          },
        ],
      }),
    },
  };
});

it('labels historical mock uploads and never presents invented confidence as extraction evidence', async () => {
  render(<DocumentUploader sessionId="synthetic" language="en" documentConsent />);
  await screen.findByText('Hemoglobin');
  expect(screen.getByText(/Synthetic mock output/)).toBeInTheDocument();
  expect(screen.queryByText(/95%/)).not.toBeInTheDocument();
  expect(screen.getByText('Not reported')).toBeInTheDocument();
});

it('shows fixture extraction immediately after selecting the upload', async () => {
  vi.mocked(api.documents).mockResolvedValueOnce({ documents: [], total: 0 });
  vi.mocked(api.uploadDocument).mockResolvedValueOnce({
    id: 'uploaded-fixture',
    session_id: 'synthetic',
    object_key: 'synthetic/uploaded-fixture/prescription.png',
    original_filename: 'prescription.png',
    document_type: 'prescription',
    processing_status: 'mock_fixture',
    media_type: 'image/png',
    file_size_bytes: 100,
    sha256_hash: 'digest',
    document_date: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    extractions: [
      {
        id: 'uploaded-extraction',
        document_id: 'uploaded-fixture',
        session_id: 'synthetic',
        extractor: 'mock',
        extractor_version: 'explicit-fixture-2.0',
        confidence: null,
        verification_status: 'unverified',
        review_version: 0,
        verified_by: null,
        verified_at: null,
        verification_notes: null,
        raw_text: 'Synthetic fixture',
        structured_json: {
          schema_version: '1.0',
          document_type: 'prescription',
          medications: [
            {
              name: 'Tab Paracetamol',
              dosage: '500mg',
              frequency: null,
              route: null,
              duration: null,
            },
          ],
          observations: [],
        },
        created_at: new Date().toISOString(),
        updated_at: null,
      },
    ],
  });

  render(<DocumentUploader sessionId="synthetic" language="en" documentConsent />);
  const file = new File(['fixture'], 'prescription.png', { type: 'image/png' });
  fireEvent.change(screen.getByTestId('document-file-input'), { target: { files: [file] } });

  await waitFor(() =>
    expect(api.uploadDocument).toHaveBeenCalledWith('synthetic', file, 'prescription'),
  );
  expect(await screen.findByText('Tab Paracetamol')).toBeInTheDocument();
  expect(screen.getByText('mock_fixture')).toBeInTheDocument();
  expect(screen.getByText(/Synthetic mock output/)).toBeInTheDocument();
});

it('explains why a stored arbitrary upload has no extraction or facts', async () => {
  vi.mocked(api.documents).mockResolvedValueOnce({
    documents: [
      {
        id: 'arbitrary',
        session_id: 'synthetic',
        object_key: 'synthetic/arbitrary/other.png',
        original_filename: 'other.png',
        document_type: 'other',
        processing_status: 'unavailable',
        media_type: 'image/png',
        file_size_bytes: 100,
        sha256_hash: 'other-digest',
        document_date: null,
        created_at: new Date().toISOString(),
        updated_at: null,
        extractions: [],
      },
    ],
    total: 1,
  });

  render(<DocumentUploader sessionId="synthetic" language="en" documentConsent />);
  expect(await screen.findByText(/real OCR is not enabled/)).toBeInTheDocument();
});
