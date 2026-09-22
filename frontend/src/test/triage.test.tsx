import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
      getQueue: vi.fn().mockResolvedValue({ items: [] }),
      acknowledgeAlert: vi.fn(),
      getSessionAlerts: vi.fn(),
      getWebSocketUrl: vi.fn(() => 'ws://localhost/mock-ws'),
      websocketTicket: vi.fn().mockResolvedValue({ ticket: 'synthetic-ticket' }),
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
  reason: 'Reported chest pain severity at least 8/10 with radiation.',
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
    expect(screen.getByText('Intake')).toBeInTheDocument();
    expect(screen.queryByText('DEMO-999')).not.toBeInTheDocument();
    expect(screen.getByText('Fatima Begum')).toBeInTheDocument();
    expect(screen.getByText('RF-CHEST-001')).toBeInTheDocument();
    expect(
      screen.getByText('Reported chest pain severity at least 8/10 with radiation.'),
    ).toBeInTheDocument();
    expect(screen.getByText('hpi.severity:')).toBeInTheDocument();
    expect(screen.getByText('Acknowledge Alert')).toBeInTheDocument();
  });

  it('submits acknowledgement form with staff name and note', async () => {
    const onAcknowledge = vi.fn().mockResolvedValue(undefined);
    render(<AlertCard alert={mockAlert} onAcknowledge={onAcknowledge} />);

    // Click acknowledge button to show form
    fireEvent.click(screen.getByText('Acknowledge Alert'));

    expect(screen.queryByPlaceholderText(/Staff member name/i)).not.toBeInTheDocument();
    const noteInput = screen.getByPlaceholderText(/Action taken note/i);

    fireEvent.change(noteInput, { target: { value: 'Patient taken to triage bay' } });

    fireEvent.click(screen.getByText('Confirm Acknowledgement'));

    await waitFor(() => {
      expect(onAcknowledge).toHaveBeenCalledWith('alert-123', 'Patient taken to triage bay');
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
    sessionStorage.setItem(
      'triage_active_hospital',
      JSON.stringify({
        id: 'mock-hosp-1',
        name: 'MediKiosk General Hospital',
        city: 'Kolkata',
        state: 'West Bengal',
        is_active: true,
      }),
    );
    if (api) {
      api.hospitals = vi.fn().mockResolvedValue({
        items: [
          {
            id: 'mock-hosp-1',
            name: 'MediKiosk General Hospital',
            city: 'Kolkata',
            state: 'West Bengal',
            is_active: true,
          },
        ],
      });
    }
  });

  it('shows the live waiting-patient count and queue for the selected hospital', async () => {
    vi.mocked(triageApi.getAlerts).mockResolvedValue({
      items: [],
      total: 0,
      emergency_count: 0,
      urgent_count: 0,
      acknowledged_count: 0,
    });
    vi.mocked(triageApi.getQueue).mockResolvedValue({
      items: [
        {
          id: 'queue-session-1',
          patient_name: 'Synthetic Patient 01-1',
          hospital_token: 'DEMO-Q-0001-1',
          language: 'en',
          status: 'ready_for_review',
          selected_doctor_id: 'doctor-1',
          queue_status: 'WAITING',
          queue_joined_at: '2026-09-13T08:00:00Z',
        },
      ],
    });

    render(<Triage />);

    expect(await screen.findByText('Waiting patient queue (1)')).toBeInTheDocument();
    expect(screen.getByText(/^1\. Patient$/)).toBeInTheDocument();
    expect(screen.queryByText('DEMO-Q-0001-1')).not.toBeInTheDocument();
    expect(triageApi.getQueue).toHaveBeenCalledWith('mock-hosp-1');
  });

  it('does not restore stale active alerts when an older refresh finishes last', async () => {
    let finishOld!: (value: Awaited<ReturnType<typeof triageApi.getAlerts>>) => void;
    const old = new Promise<Awaited<ReturnType<typeof triageApi.getAlerts>>>((resolve) => {
      finishOld = resolve;
    });
    const result = {
      items: [{ ...mockAlert, status: 'resolved' as const, revision: 1 }],
      total: 0,
      emergency_count: 0,
      urgent_count: 0,
      acknowledged_count: 0,
    };
    vi.mocked(triageApi.getAlerts).mockReturnValueOnce(old).mockResolvedValue(result);
    const sockets: { onopen?: () => void }[] = [];
    class TestSocket {
      onopen?: () => void;
      constructor() {
        sockets.push(this);
      }
      close() {}
    }
    vi.stubGlobal('WebSocket', TestSocket);
    try {
      render(<Triage />);
      await waitFor(() => expect(sockets[0]).toBeDefined());
      await act(async () => {
        sockets[0].onopen?.();
      });
      await waitFor(() =>
        expect(
          screen.getByTestId('alert-card-alert-123').querySelector('.status-badge'),
        ).toHaveTextContent('Resolved'),
      );
      await act(async () => {
        finishOld({ ...result, items: [mockAlert] });
      });
      expect(
        screen.getByTestId('alert-card-alert-123').querySelector('.status-badge'),
      ).toHaveTextContent('Resolved');
    } finally {
      vi.unstubAllGlobals();
    }
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

  it('renders both canonical showcase priorities from the initial API response', async () => {
    vi.mocked(triageApi.getAlerts).mockResolvedValue({
      items: [
        { ...mockAlert, patient_name: 'Sunita Sharma (সুমিতা শর্মা)' },
        {
          ...mockAlert,
          id: 'alert-urgent',
          rule_id: 'RF-CHEST-002',
          priority: 'urgent',
          reason: 'Chest pain associated with shortness of breath (dyspnea).',
          triggering_facts: [
            {
              question_id: 'hpi.associated_details',
              field: 'hpi.associated_details',
              value: 'DYSPNEA',
              raw_value: 'শ্বাসকষ্ট',
            },
          ],
          patient_name: 'Sunita Sharma (সুমিতা শর্মা)',
        },
      ],
      total: 2,
      emergency_count: 1,
      urgent_count: 1,
      acknowledged_count: 0,
    });

    render(<Triage />);

    expect(await screen.findByTestId('alert-card-alert-123')).toHaveTextContent('EMERGENCY');
    expect(screen.getByTestId('alert-card-alert-urgent')).toHaveTextContent('URGENT');
    expect(screen.getByTestId('alert-card-alert-123')).toHaveTextContent('RF-CHEST-001');
    expect(screen.getByTestId('alert-card-alert-urgent')).toHaveTextContent('RF-CHEST-002');
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

    render(<Interview sessionId="sess-1" language="en" onComplete={vi.fn()} />);

    await waitFor(() => {
      const advisory = screen.getByTestId('kiosk-safety-advisory');
      expect(advisory).toBeInTheDocument();
      expect(screen.getByText('Staff Assessment Recommended')).toBeInTheDocument();
      expect(
        screen.getByText(
          'Potential emergency symptoms were detected. Medical staff should assess you promptly.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByText(/Please contact medical staff directly/)).toBeInTheDocument();
    });
  });
});
