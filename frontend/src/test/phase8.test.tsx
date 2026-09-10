import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SummaryWorkspace from '../components/doctor/SummaryWorkspace';
import { api } from '../api/client';
import type { Summary, SummaryRevisionRecord, EvidenceReference } from '../api/client';

describe('Phase 8 SummaryWorkspace Component', () => {
  const sessionId = 'session-phase8-001';

  const mockEvidence: EvidenceReference[] = [
    {
      statement_id: 'ev-1',
      section: 'patient_info',
      statement_text: 'Patient Rajesh Kumar (Token: HOSP-001)',
      source_type: 'patient_answer',
      source_id: 'pat-1',
      source_text: 'Rajesh Kumar',
      source_metadata: { token: 'HOSP-001' },
    },
    {
      statement_id: 'ev-2',
      section: 'investigations_labs',
      statement_text: 'Troponin I: 0.8 ng/mL [Flag: high]',
      source_type: 'medical_fact',
      source_id: 'fact-1',
      source_text: '0.8',
      source_metadata: { test_name: 'Troponin I' },
    },
    {
      statement_id: 'ev-3',
      section: 'safety_alerts',
      statement_text: 'RF-CARD-001: Severe chest pain',
      source_type: 'alert',
      source_id: 'alert-1',
      source_text: 'RF-CARD-001',
      source_metadata: { priority: 'CRITICAL' },
    },
  ];

  const mockRevisions: SummaryRevisionRecord[] = [
    {
      id: 'rev-1',
      summary_id: 'sum-1',
      version: 1,
      revision_type: 'initial_draft',
      actor_type: 'SYSTEM',
      actor_user_id: null,
      actor_name: 'System Synthesizer',
      reviewed_text: 'Initial deterministic draft',
      review_notes: 'Generated from intake answers',
      structured_snapshot: null,
      created_at: '2026-09-10T10:00:00Z',
    },
    {
      id: 'rev-2',
      summary_id: 'sum-1',
      version: 2,
      revision_type: 'edit',
      actor_type: 'DOCTOR',
      actor_user_id: 'doc-001',
      actor_name: 'Dr. Demo',
      reviewed_text: 'Doctor revised draft text',
      review_notes: 'Corrected duration and symptoms',
      structured_snapshot: null,
      created_at: '2026-09-10T10:15:00Z',
    },
  ];

  const initialSummary: Summary = {
    id: 'sum-1',
    session_id: sessionId,
    generated_text: '## 1. Patient Information\nPatient Name: Rajesh Kumar\n\n## 2. Chief Complaint\nChest pain',
    reviewed_text: '## 1. Patient Information\nPatient Name: Rajesh Kumar\n\n## 2. Chief Complaint\nChest pain',
    status: 'generated',
    draft_provider: 'deterministic',
    draft_version: 1,
    version: 1,
    confirmed_by: null,
    confirmed_at: null,
    evidence: mockEvidence,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders summary editor with draft content and metadata badges', () => {
    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={initialSummary}
        onSummaryUpdated={vi.fn()}
      />,
    );

    expect(screen.getByTestId('summary-workspace')).toBeInTheDocument();
    expect(screen.getByText('Generated Draft')).toBeInTheDocument();
    expect(screen.getByText('v1 (Draft v1)')).toBeInTheDocument();
    const textarea = screen.getByLabelText('Reviewed summary');
    expect(textarea).toHaveValue(initialSummary.reviewed_text);
    expect(screen.getByRole('button', { name: 'Save review' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regenerate Draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm reviewed record' })).toBeDisabled();
  });

  it('allows editing working draft, inputting revision notes, and saving', async () => {
    const onUpdated = vi.fn();
    const savedSummary: Summary = {
      ...initialSummary,
      reviewed_text: 'Doctor amended text',
      status: 'reviewed',
      version: 2,
    };
    vi.spyOn(api, 'saveSummary').mockResolvedValue(savedSummary);

    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={initialSummary}
        onSummaryUpdated={onUpdated}
      />,
    );

    const textarea = screen.getByLabelText('Reviewed summary');
    fireEvent.change(textarea, { target: { value: 'Doctor amended text' } });
    const notesInput = screen.getByPlaceholderText('Brief clinical rationale for changes...');
    fireEvent.change(notesInput, { target: { value: 'Verified cardiac history' } });

    const saveBtn = screen.getByRole('button', { name: 'Save review' });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.saveSummary).toHaveBeenCalledWith(
        sessionId,
        'Doctor amended text',
        1,
        'Verified cardiac history',
      );
      expect(onUpdated).toHaveBeenCalledWith(savedSummary);
      expect(screen.getByText('Review saved.')).toBeInTheDocument();
    });
  });

  it('switches to evidence attribution view and displays source links', async () => {
    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={initialSummary}
        onSummaryUpdated={vi.fn()}
      />,
    );

    const evidenceTabBtn = screen.getByRole('button', { name: /Evidence Attribution/i });
    fireEvent.click(evidenceTabBtn);

    expect(screen.getByText('Patient Rajesh Kumar (Token: HOSP-001)')).toBeInTheDocument();
    expect(screen.getByText('Troponin I: 0.8 ng/mL [Flag: high]')).toBeInTheDocument();
    expect(screen.getByText('RF-CARD-001: Severe chest pain')).toBeInTheDocument();
    expect(screen.getByText('Source: medical_fact')).toBeInTheDocument();
    expect(screen.getByText('Source: alert')).toBeInTheDocument();
  });

  it('switches to revision history view and loads revisions from API', async () => {
    vi.spyOn(api, 'getSummaryRevisions').mockResolvedValue(mockRevisions);

    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={initialSummary}
        onSummaryUpdated={vi.fn()}
      />,
    );

    const revisionsTabBtn = screen.getByRole('button', { name: 'Revision History' });
    fireEvent.click(revisionsTabBtn);

    await waitFor(() => {
      expect(api.getSummaryRevisions).toHaveBeenCalledWith(sessionId);
      expect(screen.getByText('initial draft')).toBeInTheDocument();
      expect(screen.getByText('edit')).toBeInTheDocument();
      expect(screen.getByText('Notes: "Corrected duration and symptoms"')).toBeInTheDocument();
    });
  });

  it('handles draft regeneration and confirms replacement when manual edits exist', async () => {
    const onUpdated = vi.fn();
    const error409 = { code: 'CONFIRM_REPLACEMENT_REQUIRED' };
    vi.spyOn(api, 'regenerateSummary')
      .mockRejectedValueOnce(error409)
      .mockResolvedValueOnce({
        ...initialSummary,
        draft_version: 2,
        version: 3,
        reviewed_text: 'Freshly regenerated draft text',
      });

    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={initialSummary}
        onSummaryUpdated={onUpdated}
      />,
    );

    const regenBtn = screen.getByRole('button', { name: 'Regenerate Draft' });
    fireEvent.click(regenBtn);

    // Modal dialog pops up
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Confirm Draft Regeneration')).toBeInTheDocument();
    });

    const replaceBtn = screen.getByRole('button', { name: 'Replace Draft' });
    fireEvent.click(replaceBtn);

    await waitFor(() => {
      expect(api.regenerateSummary).toHaveBeenCalledWith(
        sessionId,
        1,
        undefined,
        true,
      );
      expect(screen.getByText('Draft regenerated from latest clinical facts.')).toBeInTheDocument();
    });
  });

  it('locks editor and displays confirmed banner in read-only confirmed state', async () => {
    const confirmedSummary: Summary = {
      ...initialSummary,
      status: 'confirmed',
      version: 3,
      confirmed_text: 'Final signed-off summary text.',
      reviewed_text: 'Final signed-off summary text.',
      confirmed_by: 'doc_verified_001',
      confirmed_at: '2026-09-10T12:00:00Z',
    };

    render(
      <SummaryWorkspace
        sessionId={sessionId}
        initialSummary={confirmedSummary}
        onSummaryUpdated={vi.fn()}
      />,
    );

    expect(screen.getByText(/Confirmed by/i)).toBeInTheDocument();
    expect(screen.getByText(/doc_verified_001/i)).toBeInTheDocument();
    const textarea = screen.getByLabelText('Reviewed summary');
    expect(textarea).toHaveAttribute('readonly');
    expect(screen.queryByRole('button', { name: 'Save review' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Regenerate Draft' })).not.toBeInTheDocument();
  });
});
