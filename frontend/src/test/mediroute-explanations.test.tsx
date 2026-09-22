import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import CareLocation from '../components/kiosk/CareLocation';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      routingLocation: vi.fn(),
      saveRoutingLocation: vi.fn(),
      mediroute: vi.fn(),
      selectFacility: vi.fn(),
    },
  };
});

const route = {
  id: 'route-private-id',
  session_id: 'session-1',
  clinical_routing_result_id: 'clinical-private-id',
  status: 'COMPLETED',
  routing_state: 'ROUTINE_OPD',
  suggested_specialty: 'GENERAL_MEDICINE',
  directory_version: 'directory-private-version',
  protocol_version: '1.0.0',
  required_specialty: 'GENERAL_MEDICINE',
  required_capabilities: [],
  preferred_capabilities: ['LAB'],
  generated_at: '2026-09-21T00:00:00Z',
  recommendations: [
    {
      facility_id: 'facility-private-id',
      facility_name: 'MediKiosk Central Hospital',
      rank: 1,
      distance_km: 3.2,
      eligibility_reasons: ['ACTIVE_FACILITY', 'REQUIRED_SPECIALTY_AVAILABLE'],
      ranking_reasons: ['OPEN', 'CLOSER_ELIGIBLE_OPTION'],
      capabilities: ['GENERAL_MEDICINE', 'LAB'],
      emergency_available: true,
    },
  ],
};

beforeEach(() => vi.clearAllMocks());

it('explains a supported facility match and preserves selection', async () => {
  const selected = vi.fn();
  vi.mocked(api.routingLocation).mockResolvedValue(null);
  vi.mocked(api.saveRoutingLocation).mockResolvedValue({} as never);
  vi.mocked(api.mediroute).mockResolvedValue(route);
  vi.mocked(api.selectFacility).mockResolvedValue({} as never);
  render(<CareLocation sessionId="session-1" onSelected={selected} />);

  fireEvent.change(await screen.findByLabelText('Locality'), { target: { value: 'Kolkata' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search by locality' }));
  const card = await screen.findByRole('article');
  expect(card).toHaveTextContent('Recommended for this care pathway');
  expect(card).toHaveTextContent('GENERAL MEDICINE available');
  expect(card).toHaveTextContent('Matches your search near Kolkata');
  fireEvent.click(within(card).getByText('Why this facility?'));
  expect(card).toHaveTextContent('Required specialty is available');
  expect(card).toHaveTextContent('Facility passed eligibility checks');
  expect(card).toHaveTextContent('Matches the selected location and distance criteria');
  expect(card).not.toHaveTextContent('EMERGENCY_CAPABLE');
  expect(card).not.toHaveTextContent('facility-private-id');
  expect(card).not.toHaveTextContent('score');

  fireEvent.click(within(card).getByRole('button', { name: 'Select facility' }));
  await waitFor(() =>
    expect(api.selectFacility).toHaveBeenCalledWith('session-1', 'facility-private-id'),
  );
  expect(selected).toHaveBeenCalledWith(false);
});

it('keeps the existing no-eligible-facility state', async () => {
  vi.mocked(api.routingLocation).mockResolvedValue(null);
  vi.mocked(api.saveRoutingLocation).mockResolvedValue({} as never);
  vi.mocked(api.mediroute).mockResolvedValue({
    ...route,
    status: 'NO_ELIGIBLE_FACILITY',
    recommendations: [],
  });
  render(<CareLocation sessionId="session-1" onSelected={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText('Locality'), { target: { value: 'Kolkata' } });
  fireEvent.click(screen.getByRole('button', { name: 'Search by locality' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'No eligible facility in the current demo directory',
  );
  expect(screen.queryByText('Why this facility?')).not.toBeInTheDocument();
});
