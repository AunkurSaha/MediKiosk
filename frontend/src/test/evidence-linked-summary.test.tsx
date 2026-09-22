import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SummaryWorkspace from '../components/doctor/SummaryWorkspace';
import type { EvidenceReference, Summary } from '../api/client';

const evidence: EvidenceReference[] = [
  {
    statement_id: 'med-1',
    section: 'current_medications',
    statement_text: 'Metformin 500 mg twice daily',
    source_type: 'medical_fact',
    source_id: 'fact-1',
    source_text: 'Metformin 500 mg BD',
    source_metadata: {
      document_id: 'doc-1',
      document_filename: 'Prescription.pdf',
      page_number: 1,
    },
    status: 'patient_confirmed',
    badge: 'Patient Confirmed',
    provenance_explanation: [
      'Extracted from Prescription.pdf, page 1.',
      'OCR extracted: "Metformin 500 mg BD"',
      'Patient confirmed current use during intake.',
    ],
  },
  {
    statement_id: 'lab-1',
    section: 'investigations_labs',
    statement_text: 'Fasting glucose 146 mg/dL',
    source_type: 'medical_fact',
    source_id: 'fact-2',
    source_text: 'Fasting glucose 146 mg/dL',
    source_metadata: { document_id: 'doc-2', document_filename: 'Lab.pdf' },
    status: 'document_unverified',
    badge: 'Document — Unverified',
    provenance_explanation: ['Document-derived information has not been clinician verified.'],
  },
  {
    statement_id: 'conflict-1',
    section: 'potential_discrepancies',
    statement_text: 'Patient reports no medicine; prescription lists Metformin.',
    source_type: 'discrepancy',
    source_id: 'disc-1',
    source_text: 'Medication sources differ',
    source_metadata: {},
    status: 'conflicting',
    badge: 'Conflict',
    provenance_explanation: ['Both source values are preserved for clinician clarification.'],
  },
  {
    statement_id: 'alert-1',
    section: 'safety_alerts',
    statement_text: 'Potential emergency symptom detected',
    source_type: 'alert',
    source_id: 'alert-1',
    source_text: 'Reported chest-pain features',
    source_metadata: { rule_id: 'RF-CARD-001' },
    status: 'safety_rule',
    badge: 'Safety Rule',
    provenance_explanation: ['Deterministic safety rule RF-CARD-001 was triggered.'],
  },
];

const summary: Summary = {
  id: 'sum-1',
  generated_text: 'Generated summary',
  reviewed_text: 'Generated summary',
  status: 'generated',
  version: 1,
  confirmed_by: null,
  confirmed_at: null,
  evidence,
  coverage: {
    session_id: 'session-1',
    required: 14,
    confirmed: 10,
    document_supported_unconfirmed: 1,
    conflicted: 1,
    missing: 2,
    not_applicable: 0,
    fields: [],
  },
};

function renderEvidence() {
  render(
    <SummaryWorkspace sessionId="session-1" initialSummary={summary} onSummaryUpdated={vi.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Evidence Attribution/i }));
}

describe('evidence-linked clinical summary', () => {
  it('renders source badges, conflict, safety rule, and coverage without fake confidence', () => {
    renderEvidence();
    expect(screen.getByText('Patient Confirmed')).toBeInTheDocument();
    expect(screen.getAllByText('Document — Unverified').length).toBeGreaterThan(0);
    expect(screen.getByText('Conflict')).toBeInTheDocument();
    expect(screen.getAllByText('Safety Rule').length).toBeGreaterThan(0);
    expect(screen.getByTestId('summary-coverage')).toHaveTextContent('Confirmed: 10');
    expect(screen.getByTestId('summary-workspace')).not.toHaveTextContent('%');
  });

  it('expands deterministic provenance and exposes source-document navigation', () => {
    renderEvidence();
    const medication = screen.getByText('Metformin 500 mg twice daily').closest('.evidence-item');
    expect(medication).not.toBeNull();
    const item = within(medication as HTMLElement);
    fireEvent.click(item.getByText('Why is this here?'));
    expect(item.getByText('Why is Metformin in this summary?')).toBeVisible();
    expect(item.getByText('Uploaded prescription')).toBeVisible();
    expect(item.getByText('Information extracted')).toBeVisible();
    expect(item.getAllByText('Metformin 500 mg BD').length).toBeGreaterThan(0);
    expect(item.getByText('Patient verification')).toBeVisible();
    expect(item.getByText('Patient confirmed current use')).toBeVisible();
    expect(item.getByText('Current medication')).toBeVisible();
    expect(item.getByText('Extracted from Prescription.pdf, page 1.')).toBeVisible();
    expect(item.getByText('Patient confirmed current use during intake.')).toBeVisible();
    expect(item.getByRole('link', { name: /View source for Metformin/i })).toHaveAttribute(
      'href',
      '#document-doc-1',
    );
    expect(screen.queryByText(/Yes, I am still taking/i)).not.toBeInTheDocument();
  });

  it('retains provenance UI while doctor text is edited', () => {
    renderEvidence();
    fireEvent.click(screen.getByRole('button', { name: 'Summary Editor' }));
    fireEvent.change(screen.getByLabelText('Reviewed summary'), {
      target: { value: 'Doctor-edited display text' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Evidence Attribution/i }));
    expect(screen.getByText('Metformin 500 mg twice daily')).toBeInTheDocument();
    expect(screen.getByText('Patient Confirmed')).toBeInTheDocument();
  });
});
