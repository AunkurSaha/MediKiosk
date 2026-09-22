import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import DoctorRecommendations from '../components/kiosk/DoctorRecommendations';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return {
    ...actual,
    api: { ...actual.api, doctorMatch: vi.fn(), selectDoctorMatch: vi.fn() },
  };
});

const match = {
  id: 'match-private-id',
  session_id: 'session-1',
  facility_id: 'facility-private-id',
  required_specialty: 'GENERAL_MEDICINE',
  directory_version: 'directory-private-version',
  protocol_version: '1.0.0',
  status: 'COMPLETED' as const,
  selected_doctor_id: null,
  generated_at: '2026-09-21T00:00:00Z',
  recommendations: [
    {
      doctor_id: 'doctor-private-id',
      name: 'Dr. Ishan Gupta',
      qualification: 'MD',
      primary_specialty: 'GENERAL_MEDICINE',
      expertise_tags: ['FEVER'],
      languages: ['en'],
      availability_status: 'AVAILABLE',
      years_of_experience: 12,
      rank: 1,
      recommended: true,
      eligibility_reasons: [
        'FACILITY_MATCH',
        'ACTIVE',
        'ACCEPTING_PATIENTS',
        'CONSULTATION_TYPE_MATCH',
        'SPECIALTY_MATCH',
      ],
      ranking_reasons: ['RELEVANT_EXPERTISE', 'AVAILABLE_FOR_CONSULTATION', 'EXPERIENCE_RELEVANT'],
    },
  ],
};

beforeEach(() => vi.clearAllMocks());

it('separates grounded doctor eligibility from ranking and preserves selection', async () => {
  const selected = vi.fn();
  vi.mocked(api.doctorMatch).mockResolvedValue(match);
  vi.mocked(api.selectDoctorMatch).mockResolvedValue({} as never);
  render(
    <DoctorRecommendations
      sessionId="session-1"
      onSelected={selected}
      onChooseFacility={vi.fn()}
    />,
  );

  const card = await screen.findByRole('article');
  expect(card).toHaveTextContent('Recommended');
  fireEvent.click(within(card).getByText('Why this match?'));
  expect(card).toHaveTextContent('Eligibility');
  expect(card).toHaveTextContent('Specialty matches the required care');
  expect(card).toHaveTextContent('Works at the selected facility');
  expect(card).toHaveTextContent('Ranking factors');
  expect(card).toHaveTextContent('Available for consultation');
  expect(card).toHaveTextContent('Relevant expertise for the reported concern');
  expect(card).not.toHaveTextContent('Previously involved in your confirmed care');
  expect(card).not.toHaveTextContent('Speaks your selected language');
  expect(card).not.toHaveTextContent('doctor-private-id');
  expect(screen.queryByText(/cardiology/i)).not.toBeInTheDocument();

  fireEvent.click(within(card).getByRole('button', { name: 'Select Doctor' }));
  await waitFor(() =>
    expect(api.selectDoctorMatch).toHaveBeenCalledWith('session-1', 'doctor-private-id'),
  );
  expect(selected).toHaveBeenCalledWith('doctor-private-id');
});

it('offers a clear facility recovery action when no eligible doctor is available', async () => {
  const chooseFacility = vi.fn();
  vi.mocked(api.doctorMatch).mockResolvedValue({
    ...match,
    status: 'NO_ELIGIBLE_DOCTOR',
    recommendations: [],
  });
  render(
    <DoctorRecommendations
      sessionId="session-1"
      onSelected={vi.fn()}
      onChooseFacility={chooseFacility}
    />,
  );
  expect(await screen.findByText(/No suitable doctor is currently available/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'View next recommended facility' }));
  expect(chooseFacility).toHaveBeenCalledOnce();
  expect(screen.queryByText('Why this match?')).not.toBeInTheDocument();
});
