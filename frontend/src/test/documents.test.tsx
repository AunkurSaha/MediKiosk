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

it('presents extracted clinical content without exposing fixture internals or invented confidence', async () => {
  render(<DocumentUploader sessionId="synthetic" language="en" documentConsent />);
  await screen.findByText('Hemoglobin');
  expect(screen.getByText('Information extracted')).toBeInTheDocument();
  expect(screen.queryByText(/Synthetic mock output|mock_fixture/)).not.toBeInTheDocument();
  expect(screen.queryByText(/95%/)).not.toBeInTheDocument();
  expect(screen.getByText('10.5')).toBeInTheDocument();
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
  expect(screen.getByText('Information extracted')).toBeInTheDocument();
  expect(screen.queryByText(/Synthetic mock output|mock_fixture/)).not.toBeInTheDocument();
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
  expect(await screen.findByText(/could not extract information/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Replace file' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Continue without this document' }));
  expect(screen.queryByText('other.png')).not.toBeInTheDocument();
});

it('attaches the granted camera stream after rendering and captures a ready frame', async () => {
  vi.mocked(api.documents).mockResolvedValueOnce({ documents: [], total: 0 });
  vi.mocked(api.uploadDocument).mockImplementationOnce(() => new Promise(() => undefined));

  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
  const drawImage = vi.fn();
  const getContext = vi
    .spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
  const toBlob = vi
    .spyOn(HTMLCanvasElement.prototype, 'toBlob')
    .mockImplementation((callback) => callback(new Blob(['photo'], { type: 'image/jpeg' })));

  const { unmount } = render(
    <DocumentUploader sessionId="synthetic" language="en" documentConsent />,
  );
  fireEvent.click(screen.getByTestId('open-camera-btn'));

  const video = await screen
    .findByRole('button', { name: 'Starting camera…' })
    .then(() => document.querySelector('video') as HTMLVideoElement);
  await waitFor(() => expect(video.srcObject).toBe(stream));
  expect(play).toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Starting camera…' })).toBeDisabled();

  Object.defineProperties(video, {
    videoWidth: { configurable: true, value: 1280 },
    videoHeight: { configurable: true, value: 720 },
  });
  fireEvent.loadedMetadata(video);
  fireEvent.click(screen.getByRole('button', { name: '📸 Capture Image' }));

  await waitFor(() => expect(api.uploadDocument).toHaveBeenCalled());
  const capturedFile = vi.mocked(api.uploadDocument).mock.calls.at(-1)?.[1];
  expect(capturedFile).toBeInstanceOf(File);
  expect(capturedFile?.type).toBe('image/jpeg');
  expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 1280, 720);
  expect(toBlob).toHaveBeenCalled();
  expect(stop).toHaveBeenCalled();

  unmount();
  play.mockRestore();
  getContext.mockRestore();
  toBlob.mockRestore();
});
