import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import DoctorSelector from '../components/kiosk/DoctorSelector';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return { ...actual, api: { ...actual.api, matchedDoctors: vi.fn(), selectDoctor: vi.fn() } };
});

describe('doctor routing UI', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders queue order, recommendation, and selects a doctor', async () => {
    vi.mocked(api.matchedDoctors).mockResolvedValue({
      specialty_codes: ['CARDIOLOGY'], fallback_used: false,
      items: [
        { doctor_id: 'a', name: 'Dr A', qualification: 'MD', specialties: ['CARDIOLOGY'], matched_specialty: 'CARDIOLOGY', waiting_count: 2, recommended: true, fallback: false },
        { doctor_id: 'b', name: 'Dr B', qualification: 'MD', specialties: ['CARDIOLOGY'], matched_specialty: 'CARDIOLOGY', waiting_count: 5, recommended: false, fallback: false },
      ],
    });
    vi.mocked(api.selectDoctor).mockResolvedValue({ session_id: 's', hospital_id: 'h', doctor_id: 'a' });
    const selected = vi.fn();
    render(<DoctorSelector sessionId="s" onSelected={selected} />);
    expect(await screen.findByText('2 patients waiting')).toBeInTheDocument();
    expect(screen.getByText('★ Recommended — shortest queue')).toBeInTheDocument();
    expect(screen.queryByText('Wrong Hospital Doctor')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Choose' })[0]);
    await waitFor(() => expect(selected).toHaveBeenCalledWith('a'));
  });

  it('shows the safe empty state and API retry state', async () => {
    vi.mocked(api.matchedDoctors).mockResolvedValue({ specialty_codes: ['CARDIOLOGY'], fallback_used: false, items: [] });
    const view = render(<DoctorSelector sessionId="s" onSelected={vi.fn()} />);
    expect(await screen.findByText(/No suitable doctor/)).toBeInTheDocument();
    view.unmount();
    vi.mocked(api.matchedDoctors).mockRejectedValue(new Error('offline'));
    render(<DoctorSelector sessionId="s" onSelected={vi.fn()} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
