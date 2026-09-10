import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import DocumentUploader from '../components/kiosk/DocumentUploader';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return {
    ...actual,
    api: {
      ...actual.api,
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
