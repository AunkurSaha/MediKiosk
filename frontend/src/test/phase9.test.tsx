import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FieldVerificationBadge } from '../components/doctor/FieldVerificationBadge';
import { SummaryAmendmentModal } from '../components/doctor/SummaryAmendmentModal';
import { AuditTrailViewer } from '../components/doctor/AuditTrailViewer';
import SummaryWorkspace from '../components/doctor/SummaryWorkspace';
import DocumentViewer from '../components/doctor/DocumentViewer';
import { api } from '../api/client';
import type {
  Summary,
  AuditTrailResponse,
  CrossReferenceResponse,
  DocumentRecord,
} from '../api/client';

describe('Phase 9 Verification Hardening Components', () => {
  const sessionId = 'session-phase9-001';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('FieldVerificationBadge', () => {
    it('renders initial unverified state and updates to verified on action', async () => {
      vi.spyOn(api, 'verifyField').mockResolvedValueOnce({
        id: 'fv-1',
        session_id: sessionId,
        field_type: 'interview_answer',
        field_id: 'chest_pain_onset',
        status: 'verified',
        verified_by: 'doc-001',
        verified_at: '2026-09-10T12:00:00Z',
        notes: 'Confirmed directly with patient',
        version: 1,
        created_at: '2026-09-10T12:00:00Z',
        updated_at: '2026-09-10T12:00:00Z',
        revisions: [],
      });

      const onVerificationChanged = vi.fn();

      render(
        <FieldVerificationBadge
          sessionId={sessionId}
          fieldType="interview_answer"
          fieldId="chest_pain_onset"
          onVerificationChanged={onVerificationChanged}
        />,
      );

      const badge = screen.getByRole('button', { name: /unverified/i });
      expect(badge).toBeInTheDocument();

      // Click to open popover
      fireEvent.click(badge);
      expect(screen.getByText('Clinician Verification')).toBeInTheDocument();

      // Enter notes
      const notesInput = screen.getByPlaceholderText(/verified with patient/i);
      fireEvent.change(notesInput, { target: { value: 'Confirmed directly with patient' } });

      // Click Verify button
      const verifyBtn = screen.getByRole('button', { name: /^verify$/i });
      fireEvent.click(verifyBtn);

      await waitFor(() => {
        expect(api.verifyField).toHaveBeenCalledWith(sessionId, {
          field_type: 'interview_answer',
          field_id: 'chest_pain_onset',
          status: 'verified',
          notes: 'Confirmed directly with patient',
        });
        expect(onVerificationChanged).toHaveBeenCalled();
        expect(screen.getByRole('button', { name: /✓ verified/i })).toBeInTheDocument();
      });
    });

    it('flags a field when flagged button is clicked', async () => {
      vi.spyOn(api, 'verifyField').mockResolvedValueOnce({
        id: 'fv-2',
        session_id: sessionId,
        field_type: 'interview_answer',
        field_id: 'duration',
        status: 'flagged',
        verified_by: 'doc-001',
        verified_at: '2026-09-10T12:00:00Z',
        notes: 'Patient unsure about duration',
        version: 1,
        created_at: '2026-09-10T12:00:00Z',
        updated_at: '2026-09-10T12:00:00Z',
        revisions: [],
      });

      render(
        <FieldVerificationBadge
          sessionId={sessionId}
          fieldType="interview_answer"
          fieldId="duration"
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: /unverified/i }));
      fireEvent.click(screen.getByRole('button', { name: /^flag$/i }));

      await waitFor(() => {
        expect(api.verifyField).toHaveBeenCalledWith(sessionId, {
          field_type: 'interview_answer',
          field_id: 'duration',
          status: 'flagged',
          notes: undefined,
        });
        expect(screen.getByRole('button', { name: /⚠️ flagged/i })).toBeInTheDocument();
      });
    });
  });

  describe('SummaryAmendmentModal & SummaryWorkspace Amendment Flow', () => {
    it('submits amendment with clinical justification notes', async () => {
      const confirmedSummary: Summary = {
        id: 'sum-conf-1',
        session_id: sessionId,
        generated_text: 'Initial generated text',
        reviewed_text: 'Confirmed clinical summary text',
        status: 'confirmed',
        draft_provider: 'deterministic',
        draft_version: 1,
        version: 2,
        confirmed_by: 'Dr. Demo',
        confirmed_at: '2026-09-10T12:00:00Z',
      };

      const amendedSummary: Summary = {
        ...confirmedSummary,
        status: 'amended',
        version: 3,
        amended_text:
          'Confirmed clinical summary text\n\n## Clinical Addendum\nFollow-up ECG normal.',
        amended_by: 'Dr. Demo',
        amended_at: '2026-09-10T12:30:00Z',
        amendment_notes: 'Added post-consultation ECG observation',
      };

      vi.spyOn(api, 'amendSummary').mockResolvedValueOnce(amendedSummary);
      const onAmendmentSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <SummaryAmendmentModal
          isOpen={true}
          onClose={onClose}
          sessionId={sessionId}
          confirmedText={confirmedSummary.reviewed_text!}
          onAmendmentSaved={onAmendmentSaved}
        />,
      );

      expect(screen.getByText('File Clinical Summary Amendment')).toBeInTheDocument();

      // Enter required notes
      const notesInput = screen.getByLabelText(/clinical justification notes/i);
      fireEvent.change(notesInput, {
        target: { value: 'Added post-consultation ECG observation' },
      });

      // Click save
      const submitBtn = screen.getByRole('button', { name: /save clinical amendment/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(api.amendSummary).toHaveBeenCalledWith(
          sessionId,
          expect.stringContaining('Clinical Addendum'),
          'Added post-consultation ECG observation',
        );
        expect(onAmendmentSaved).toHaveBeenCalledWith(amendedSummary);
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('renders amendment card in SummaryWorkspace when summary is amended', () => {
      const amendedSummary: Summary = {
        id: 'sum-conf-2',
        session_id: sessionId,
        generated_text: 'Initial generated text',
        reviewed_text: 'Confirmed summary text',
        status: 'amended',
        draft_provider: 'deterministic',
        draft_version: 1,
        version: 3,
        confirmed_by: 'Dr. Demo',
        confirmed_at: '2026-09-10T12:00:00Z',
        amended_text: 'Confirmed summary text with official addendum note',
        amended_by: 'Dr. Specialist',
        amended_at: '2026-09-10T12:35:00Z',
        amendment_notes: 'Second clinician review addendum',
      };

      render(
        <SummaryWorkspace
          sessionId={sessionId}
          initialSummary={amendedSummary}
          onSummaryUpdated={vi.fn()}
        />,
      );

      expect(screen.getByTestId('file-amendment-button')).toBeInTheDocument();
      expect(screen.getByTestId('amendment-display')).toBeInTheDocument();
      expect(screen.getByText(/Official Clinical Amendment \/ Addendum/i)).toBeInTheDocument();
      expect(screen.getByText(/Amended by Dr. Specialist/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Clinical Reason: "Second clinician review addendum"/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Confirmed summary text with official addendum note/i),
      ).toBeInTheDocument();
    });
  });

  describe('AuditTrailViewer', () => {
    it('renders audit events and supports filtering by actor', async () => {
      const mockAuditData: AuditTrailResponse = {
        session_id: sessionId,
        total: 3,
        items: [
          {
            id: 'audit-1',
            action: 'SESSION_CREATED',
            actor_type: 'PATIENT',
            actor_user_id: null,
            entity_type: 'session',
            entity_id: sessionId,
            timestamp: '2026-09-10T10:00:00Z',
            metadata: { token: 'HOSP-001' },
          },
          {
            id: 'audit-2',
            action: 'VERIFY_FIELD',
            actor_type: 'DOCTOR',
            actor_user_id: 'doc-001',
            entity_type: 'field_verification',
            entity_id: 'fv-1',
            timestamp: '2026-09-10T10:15:00Z',
            metadata: { field_type: 'interview_answer', status: 'verified' },
          },
          {
            id: 'audit-3',
            action: 'SYNTHESIS_COMPLETED',
            actor_type: 'SYSTEM',
            actor_user_id: null,
            entity_type: 'clinical_summary',
            entity_id: 'sum-1',
            timestamp: '2026-09-10T10:10:00Z',
            metadata: { version: 1 },
          },
        ],
      };

      vi.spyOn(api, 'getAuditTrail').mockResolvedValueOnce(mockAuditData);

      render(<AuditTrailViewer sessionId={sessionId} />);

      await waitFor(() => {
        expect(screen.getByTestId('audit-trail-viewer')).toBeInTheDocument();
        expect(screen.getByText(/Session Audit Trail \(3\)/i)).toBeInTheDocument();
        expect(screen.getByText(/SESSION CREATED/i)).toBeInTheDocument();
        expect(screen.getByText(/VERIFY FIELD/i)).toBeInTheDocument();
        expect(screen.getByText(/SYNTHESIS COMPLETED/i)).toBeInTheDocument();
      });

      // Filter by Doctor
      const filterSelect = screen.getByLabelText(/filter actor/i);
      fireEvent.change(filterSelect, { target: { value: 'doctor' } });

      expect(screen.queryByText(/SESSION CREATED/i)).not.toBeInTheDocument();
      expect(screen.getByText(/VERIFY FIELD/i)).toBeInTheDocument();
      expect(screen.queryByText(/SYNTHESIS COMPLETED/i)).not.toBeInTheDocument();
    });
  });

  describe('DocumentViewer Cross-References', () => {
    it('renders linked cross-reference provenance when present', async () => {
      const mockDoc: DocumentRecord = {
        id: 'doc-123',
        session_id: sessionId,
        object_key: 'mock/key/lab_report.jpg',
        original_filename: 'lab_report.jpg',
        media_type: 'image/jpeg',
        file_size_bytes: 204800,
        sha256_hash: 'a'.repeat(64),
        document_type: 'lab_report',
        document_date: '2026-09-01',
        processing_status: 'completed',
        created_at: '2026-09-10T09:00:00Z',
        updated_at: '2026-09-10T09:00:00Z',
        extractions: [],
      };

      const mockCrossReferenceData: CrossReferenceResponse = {
        session_id: sessionId,
        documents: [
          {
            document_id: 'doc-123',
            filename: 'lab_report.jpg',
            document_type: 'lab_report',
            created_at: '2026-09-10T09:00:00Z',
            medications: [
              {
                fact_id: 'med-1',
                fact_type: 'medication',
                label: 'Aspirin',
                verification_status: 'unverified',
              },
            ],
            labs: [
              {
                fact_id: 'lab-1',
                fact_type: 'lab',
                label: 'Troponin T',
                verification_status: 'unverified',
              },
            ],
            discrepancies: [],
            summary_statements: ['stmt-1'],
          },
        ],
        statement_cross_references: {},
      };

      vi.spyOn(api, 'getCrossReferences').mockResolvedValueOnce(mockCrossReferenceData);
      vi.spyOn(api, 'documentFile').mockResolvedValueOnce(
        new Blob(['fake'], { type: 'image/jpeg' }),
      );

      render(<DocumentViewer sessionId={sessionId} documents={[mockDoc]} />);

      await waitFor(() => {
        expect(screen.getByTestId('doc-cross-ref-doc-123')).toBeInTheDocument();
        expect(screen.getByText(/🔗 Cross-Reference Provenance/i)).toBeInTheDocument();
        expect(screen.getByText(/Summary Referenced:/i)).toBeInTheDocument();
        expect(screen.getByText(/✓ Yes/i)).toBeInTheDocument();
        expect(screen.getByText(/Linked Medications:/i)).toBeInTheDocument();
        expect(screen.getByText(/Aspirin/i)).toBeInTheDocument();
        expect(screen.getByText(/Linked Labs:/i)).toBeInTheDocument();
        expect(screen.getByText(/Troponin T/i)).toBeInTheDocument();
      });
    });
  });
});
