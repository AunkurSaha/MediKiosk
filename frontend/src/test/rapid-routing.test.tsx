import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import RapidRouting from '../components/kiosk/RapidRouting';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    api: Object.fromEntries(Object.keys(actual.api).map((key) => [key, vi.fn()])),
  };
});

const initial = {
  phase: 'chief_complaint' as const,
  revision: 0,
  questions_asked: [],
  questions_skipped: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.rapidRouting).mockResolvedValue(initial);
});

it('shows multilingual symptom cards and requires complaint confirmation', async () => {
  const user = userEvent.setup();
  vi.mocked(api.mapComplaint).mockResolvedValue({
    phase: 'confirm_complaint',
    revision: 1,
    questions_asked: [],
    questions_skipped: [],
    mapping: {
      original_text: 'My chest hurts',
      language: 'en',
      source: 'typed',
      candidate_category: 'CHEST_DISCOMFORT',
      mapping_provider: 'deterministic_keyword_v1',
      patient_confirmed: false,
    },
  });
  vi.mocked(api.confirmComplaint).mockResolvedValue({
    phase: 'rapid_interview',
    revision: 2,
    chief_complaint: 'CHEST_DISCOMFORT',
    questions_asked: [],
    questions_skipped: [],
    question: {
      question_id: 'rapid.chest.severity',
      concept_code: 'SYMPTOM_SEVERITY',
      target_field: 'hpi.severity',
      prompt: { en: 'How severe?', bn: 'কতটা তীব্র?', hi: 'कितना गंभीर?' },
      input_type: 'severity',
      options: [],
      required_for_safety: true,
      required_for_routing: true,
      equivalent_fields: [],
      version: '1.0.0',
    },
  });
  render(
    <RapidRouting sessionId="session-1" language="en" voiceConsent={false} onContinue={vi.fn()} />,
  );
  expect(await screen.findByRole('heading', { name: 'What brings you here today?' })).toBeVisible();
  await user.type(screen.getByLabelText('Describe it in your own words'), 'My chest hurts');
  await user.click(screen.getByRole('button', { name: 'Understand my concern' }));
  expect(await screen.findByText('We understood: Chest discomfort')).toBeVisible();
  expect(api.confirmComplaint).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: 'Yes, continue' }));
  expect(api.confirmComplaint).toHaveBeenCalledWith('session-1', 'CHEST_DISCOMFORT', 1);
  expect(await screen.findByText('How severe?')).toBeVisible();
});

it('emergency result has no normal-flow call to action', async () => {
  vi.mocked(api.rapidRouting).mockResolvedValue({
    phase: 'result',
    revision: 4,
    chief_complaint: 'CHEST_DISCOMFORT',
    questions_asked: [],
    questions_skipped: [],
    result: {
      id: 'r1',
      session_id: 's1',
      chief_complaint: 'CHEST_DISCOMFORT',
      routing_state: 'EMERGENCY',
      suggested_specialty: 'EMERGENCY',
      triggered_red_flags: ['RF-CHEST-001'],
      supporting_evidence_ids: ['e1'],
      questions_asked: [],
      questions_skipped: [],
      completed_at: '2026-09-18T00:00:00Z',
      routing_protocol_version: '1.0.0',
    },
  });
  render(<RapidRouting sessionId="s1" language="en" voiceConsent={false} onContinue={vi.fn()} />);
  expect(await screen.findByText('Potential emergency symptoms detected.')).toBeVisible();
  expect(screen.getByText(/Immediate clinical assessment recommended/)).toBeVisible();
  expect(screen.getByRole('heading', { name: 'How was this detected?' })).toBeVisible();
  expect(screen.getByText(/predefined deterministic clinical safety rule/)).toBeVisible();
  expect(screen.getByText('Clinical safety alert recorded for triage.')).toBeVisible();
  expect(
    screen.getByText(/Routine doctor matching and the normal queue pathway are paused/),
  ).toBeVisible();
  expect(screen.queryByText(/diagnosis:|heart attack|treatment ready/i)).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /Find a suitable facility/i }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
});
