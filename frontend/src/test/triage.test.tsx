import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AlertItem } from '../api/triage';
import AlertCard from '../components/triage/AlertCard';
import Interview from '../components/kiosk/Interview';
import Triage from '../routes/triage';
import { triageApi } from '../api/triage';
import { api } from '../api/client';
import type { InterviewState } from '../api/interview';

vi.mock('../api/triage', async (original) => {
  const actual = await original<typeof import('../api/triage')>();
  return {
    ...actual,
    triageApi: {
      getAlerts: vi.fn(),
      acknowledgeAlert: vi.fn(),
      getSessionAlerts: vi.fn(),
      getWebSocketUrl: vi.fn(() => 'ws://localhost/mock-ws'),
    },
  };
});

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      interview: vi.fn(),
      interviewAnswer: vi.fn(),
      selectFlow: vi.fn(),
      doctorDetail: vi.fn(),
    },
  };
});

const mockAlert: AlertItem = {
  id: 'alert-123',
  session_id: 'session-456',
  rule_id: 'RF-CHEST-001',
  rule_version: '1.0.0',
  priority: 'emergency',
  category: 'cardiovascular',
  reason: 'Severe radiating chest pain (potential acute coronary syndrome).',
  triggering_facts: [
    {
      question_id: 'hpi_severity',
      field: 'hpi.severity',
      value: 9,
      raw_value: '9',
      label: 'Severity',
    },
    {
      question_id: 'hpi_radiation',
      field: 'hpi.radiation',
      value: true,
      raw_value: 'yes',
      label: 'Radiation',
    },
  ],
  status: 'new',
  acknowledged_at: null,
  acknowledged_by: null,
  acknowledgement_note: null,
  created_at: '2026-09-09T12:00:00Z',
  updated_at: null,
  hospital_token: 'DEMO-999',
  patient_name: 'Fatima Begum',
};

describe('AlertCard', () => {
  it('renders alert card with emergency badge, token, reason, and triggering facts', () => {
    const onAcknowledge = vi.fn();
    render(<AlertCard alert={mockAlert} onAcknowledge={onAcknowledge} />);

    expect(screen.getByText('EMERGENCY')).toBeInTheDocument();
    expect(screen.getByText('DEMO-999')).toBeInTheDocument();
    expect(screen.getByText('Fatima Begum')).toBeInTheDocument();
    expect(screen.getByText('RF-CHEST-001')).toBeInTheDocument();
    expect(
      screen.getByText('Severe radiating chest pain (potential acute coronary syndrome).')
    ).toBeInTheDocument();
    expect(screen.getByText('hpi.severity:')).toBeInTheDocument();
    expect(screen.getByText('Acknowledge Alert')).toBeInTheDocument();
  });

  it('submits acknowledgement form with staff name and note', async () => {
    const onAcknowledge = vi.fn().mockResolvedValue(undefined);
    render(<AlertCard alert={mockAlert} onAcknowledge={onAcknowledge} />);

    // Click acknowledge button to show form
    fireEvent.click(screen.getByText('Acknowledge Alert'));

    const nameInput = screen.getByPlaceholderText(/Staff member name/i);
    const noteInput = screen.getByPlaceholderText(/Action taken note/i);

    fireEvent.change(nameInput, { target: { value: 'Nurse Joy' } });
    fireEvent.change(noteInput, { target: { value: 'Patient taken to triage bay' } });

    fireEvent.click(screen.getByText('Confirm Acknowledgement'));

    await waitFor(() => {
      expect(onAcknowledge).toHaveBeenCalledWith(
        'alert-123',
        'Nurse Joy',
        'Patient taken to triage bay'
      );
    });
  });

  it('renders acknowledged state with staff name', () => {
    const acknowledgedAlert: AlertItem = {
      ...mockAlert,
      status: 'acknowledged',
      acknowledged_by: 'Dr. John',
      acknowledged_at: '2026-09-09T12:05:00Z',
      acknowledgement_note: 'Assessment underway',
    };
    render(<AlertCard alert={acknowledgedAlert} onAcknowledge={vi.fn()} />);

    expect(screen.getByText(/Dr\. John/)).toBeInTheDocument();
    expect(screen.getByText(/"Assessment underway"/)).toBeInTheDocument();
    expect(screen.queryByText('Acknowledge Alert')).not.toBeInTheDocument();
  });
});

describe('Triage Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads and displays alerts and metrics', async () => {
    vi.mocked(triageApi.getAlerts).mockResolvedValue({
      items: [mockAlert],
      total: 1,
      emergency_count: 1,
      urgent_count: 0,
      acknowledged_count: 0,
    });

    render(<Triage />);

    await waitFor(() => {
      expect(screen.getByText('Staff Triage & Safety Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Fatima Begum')).toBeInTheDocument();
      expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('Kiosk Safety Advisory in Interview', () => {
  it('renders calm patient advisory when red_flag_alert is present in interview state', async () => {
    const stateWithAlert: InterviewState = {
      selection_required: false,
      flows: [],
      flow_id: 'chest_pain',
      flow_version: '1.0.0',
      namespace: 'standard',
      revision: 3,
      section: { en: 'History', bn: 'ইতিহাস', hi: 'इतिहास' },
      question: {
        question_id: 'hpi.severity',
        field: 'hpi.severity',
        type: 'severity',
        text: { en: 'Rate your pain', bn: 'ব্যথা নির্ধারণ করুন', hi: 'दर्द का स्तर बताएं' },
        required: true,
        allow_unknown: false,
        options: [],
        constraints: { minimum: 0, maximum: 10, max_length: 10, integer: true },
      },
      current_answer: null,
      previous_question_id: 'hpi.onset',
      active_answers: [],
      inactive_question_ids: [],
      missing_required: [],
      progress: { addressed: 2, applicable: 5, position: 2 },
      is_complete: false,
      history: null,
      red_flag_alert: {
        id: 'alert-123',
        rule_id: 'RF-CHEST-001',
        priority: 'emergency',
        category: 'cardiovascular',
        reason: 'Severe radiating chest pain.',
        created_at: '2026-09-09T12:00:00Z',
      },
    };

    vi.mocked(api.interview).mockResolvedValue(stateWithAlert);

    render(
      <Interview
        sessionId="sess-1"
        language="en"
        onComplete={vi.fn()}
      />
    );

    await waitFor(() => {
      const advisory = screen.getByTestId('kiosk-safety-advisory');
      expect(advisory).toBeInTheDocument();
      expect(screen.getByText('Staff Assessment Recommended')).toBeInTheDocument();
      expect(
        screen.getByText('Potential emergency symptoms were detected. Medical staff should assess you promptly.')
      ).toBeInTheDocument();
      expect(screen.getByText('Medical staff have been notified.')).toBeInTheDocument();
    });
  });
});
