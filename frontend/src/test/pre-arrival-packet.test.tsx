import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import PreArrivalPacket from '../components/kiosk/PreArrivalPacket';
import Handoff from '../routes/handoff';

vi.mock('qrcode.react', () => ({
  QRCodeSVG: ({ value }: { value: string }) => <div data-testid="qr-payload">{value}</div>,
}));

const metadata = {
  packet_id: 'packet-1',
  session_id: 'session-secret',
  packet_version: '1.0',
  status: 'ACTIVE' as const,
  created_at: '2026-09-20T10:00:00Z',
  expires_at: '2026-09-21T10:00:00Z',
};

describe('secure pre-arrival packet', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('creates once and renders an opaque QR URL without clinical data', async () => {
    vi.spyOn(api, 'createPacket').mockResolvedValue(metadata);
    vi.spyOn(api, 'issueHandoffToken').mockResolvedValue({
      ...metadata,
      handoff_token: 'opaque-random-token',
      handoff_url: '/handoff/p/opaque-random-token',
      handoff_token_expires_at: '2026-09-20T11:00:00Z',
    });
    render(<PreArrivalPacket sessionId="session-secret" />);
    expect(await screen.findByText(/Secure handoff packet ready/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show Secure QR' }));
    const payload = await screen.findByTestId('qr-payload');
    expect(payload.textContent).toContain('/handoff/p/opaque-random-token');
    expect(payload.textContent).not.toContain('session-secret');
    expect(payload.textContent).not.toMatch(/patient|medication|summary|diagnosis|queue/i);
    expect(
      screen.getByText(/medical information is not embedded directly in the QR/i),
    ).toBeVisible();
    expect(screen.getByText('Show this QR to authorized clinical staff.')).toBeVisible();
  });

  it('loads the persisted snapshot for patient summary without creating another packet', async () => {
    vi.spyOn(api, 'createPacket').mockResolvedValue(metadata);
    vi.spyOn(api, 'packet').mockResolvedValue({
      ...metadata,
      snapshot: {
        facility: { name: 'City Hospital' },
        selected_doctor: { name: 'Dr Assigned' },
        chief_complaint: 'Fever',
      },
      live_queue: null,
    });
    render(<PreArrivalPacket sessionId="session-secret" />);
    fireEvent.click(await screen.findByRole('button', { name: 'View Packet Summary' }));
    expect(await screen.findByText('Facility: City Hospital')).toBeInTheDocument();
    expect(api.packet).toHaveBeenCalledWith('session-secret');
    expect(api.createPacket).toHaveBeenCalledTimes(1);
  });

  it('explains only categories present in the persisted packet snapshot', async () => {
    vi.spyOn(api, 'createPacket').mockResolvedValue(metadata);
    vi.spyOn(api, 'packet').mockResolvedValue({
      ...metadata,
      snapshot: {
        chief_complaint: 'Fever',
        structured_history: [{ section: 'chief_complaint' }],
        documents: [{ document_type: 'prescription' }],
        red_flags: [],
        clinical_summary: { evidence_references: [{ statement_id: 'med-1' }] },
      },
      live_queue: null,
    });
    render(<PreArrivalPacket sessionId="session-secret" />);
    const contents = await screen.findByText('What will the doctor receive?');
    expect(contents.closest('details')).toHaveTextContent('Chief complaint');
    expect(contents.closest('details')).toHaveTextContent('Structured patient history');
    expect(contents.closest('details')).toHaveTextContent('Uploaded document references');
    expect(contents.closest('details')).toHaveTextContent('Red-flag status');
    expect(contents.closest('details')).toHaveTextContent('Clinical summary for doctor review');
    expect(contents.closest('details')).toHaveTextContent('Evidence and source information');
    expect(screen.queryByText('session-secret')).not.toBeInTheDocument();
  });

  it('clears the old QR during rotation and keeps a failed rotation from showing a stale link', async () => {
    vi.spyOn(api, 'createPacket').mockResolvedValue(metadata);
    vi.spyOn(api, 'packet').mockResolvedValue({ ...metadata, snapshot: {}, live_queue: null });
    const issue = vi.spyOn(api, 'issueHandoffToken');
    issue.mockResolvedValueOnce({
      ...metadata,
      handoff_token: 'first-token',
      handoff_url: '/handoff/p/first-token',
      handoff_token_expires_at: metadata.expires_at,
    });
    issue.mockRejectedValueOnce(new ApiError('HANDOFF_TOKEN_EXPIRED', 410));
    render(<PreArrivalPacket sessionId="session-secret" />);
    const button = await screen.findByRole('button', { name: 'Show Secure QR' });
    fireEvent.click(button);
    expect(await screen.findByTestId('qr-payload')).toHaveTextContent('first-token');
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByTestId('qr-payload')).not.toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('HANDOFF_TOKEN_EXPIRED');
  });

  it('preserves the intended handoff route when clinician authentication is required', async () => {
    vi.spyOn(api, 'resolveHandoff').mockResolvedValue({ status: 'AUTH_REQUIRED' });
    render(
      <MemoryRouter initialEntries={['/handoff/p/opaque-token']}>
        <Routes>
          <Route path="/handoff/p/:token" element={<Handoff />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = await screen.findByRole('link', { name: 'Sign in as clinician' });
    expect(link).toHaveAttribute('href', '/staff/login?redirect=%2Fhandoff%2Fp%2Fopaque-token');
  });

  it('renders the assigned doctor continuity view with provenance affordance', async () => {
    vi.spyOn(api, 'resolveHandoff').mockResolvedValue({
      ...metadata,
      snapshot: {
        visit_context: { session_id: 'session-secret' },
        facility: { name: 'City Hospital' },
        selected_doctor: { name: 'Dr Assigned' },
        clinical_summary: {
          sections: [
            {
              section_key: 'medications',
              title: 'Current medication',
              content_lines: ['Metformin 500 mg twice daily — Why is this here?'],
            },
          ],
        },
        red_flags: [],
        conflicts: [],
      },
      live_queue: { status: 'WAITING', visit_token: 'MK-GEN-001' },
    });
    render(
      <MemoryRouter initialEntries={['/handoff/p/opaque-token']}>
        <Routes>
          <Route path="/handoff/p/:token" element={<Handoff />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Metformin 500 mg/)).toBeInTheDocument();
    expect(screen.getByText(/MK-GEN-001/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open full clinical workspace' })).toHaveAttribute(
      'href',
      '/doctor/sessions/session-secret',
    );
  });

  it.each([
    ['PACKET_NOT_FOUND', 'This handoff link is invalid.'],
    ['HANDOFF_TOKEN_EXPIRED', 'This handoff link has expired.'],
    ['PACKET_EXPIRED', 'This handoff link has expired.'],
    ['PACKET_REVOKED', 'This handoff link is no longer active.'],
    ['FORBIDDEN', 'You do not have access to this patient handoff.'],
  ])('renders safe %s state', async (code, message) => {
    vi.spyOn(api, 'resolveHandoff').mockRejectedValue(new ApiError(code, 410));
    render(
      <MemoryRouter initialEntries={['/handoff/p/token']}>
        <Routes>
          <Route path="/handoff/p/:token" element={<Handoff />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(message));
  });
});
