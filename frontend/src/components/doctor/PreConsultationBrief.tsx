import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { Detail, EvidenceReference, PatientQueueEstimate } from '../../api/client';

function isMedicationEvidence(item: EvidenceReference) {
  return (
    item.section === 'current_medications' || /medication|metformin/i.test(item.statement_text)
  );
}

export default function PreConsultationBrief({ detail }: { detail: Detail }) {
  const [queue, setQueue] = useState<PatientQueueEstimate | null>(null);
  const summary = detail.summary;
  const packet = summary?.pre_arrival_packet as
    | {
        queue?: { visit_token?: string | null; status?: string | null } | null;
        routing?: { routing_state?: string | null } | null;
        conflicts?: unknown[];
      }
    | null
    | undefined;

  useEffect(() => {
    let active = true;
    api
      .queueEstimate(detail.session.id)
      .then((result) => {
        if (active) setQueue(result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [detail.session.id]);

  const historyFacts = useMemo(
    () => detail.history?.sections.flatMap((section) => section.facts) || [],
    [detail.history],
  );
  const mainConcern = historyFacts.find((fact) => fact.field === 'chief_complaint.description');
  const medicationEvidence = (summary?.evidence || []).filter(isMedicationEvidence);
  const medication =
    medicationEvidence.find(
      (item) => item.source_type === 'medical_fact' && /metformin/i.test(item.statement_text),
    ) ||
    medicationEvidence.find((item) => item.source_type === 'medical_fact') ||
    medicationEvidence.find((item) => item.status === 'patient_confirmed') ||
    medicationEvidence[0];
  const coverage = summary?.coverage;
  const conflicts = Math.max(coverage?.conflicted || 0, packet?.conflicts?.length || 0);
  const redFlags = detail.alerts || [];
  const documents = detail.documents || [];
  const visitToken = queue?.visit_token || packet?.queue?.visit_token;
  const queueStatus = queue?.status || packet?.queue?.status;
  const routingState = packet?.routing?.routing_state;

  return (
    <section className="card pre-consultation-brief" aria-labelledby="pre-consultation-title">
      <div className="pre-consultation-heading">
        <div>
          <p className="eyebrow">Patient-ready overview</p>
          <h2 id="pre-consultation-title">Pre-Consultation Brief</h2>
        </div>
        {routingState && (
          <span className={`badge brief-urgency ${routingState.toLowerCase()}`}>
            {routingState === 'ROUTINE_OPD'
              ? 'Routine'
              : routingState.replaceAll('_', ' ').toLowerCase()}
          </span>
        )}
      </div>
      {mainConcern?.raw_value && <p className="brief-main-concern">{mainConcern.raw_value}</p>}
      <div className="brief-grid">
        {detail.history?.selected_complaint.en && (
          <div className="brief-item">
            <span>Chief complaint</span>
            <strong>{detail.history.selected_complaint.en}</strong>
          </div>
        )}
        {medication && (
          <div
            className={`brief-item ${medication.status === 'conflicting' ? 'brief-warning' : ''}`}
          >
            <span>Current medication</span>
            <strong>{medication.statement_text}</strong>
            {medication.status === 'patient_confirmed' && (
              <span className="source-badge">✓ Patient confirmed</span>
            )}
            {medication.status === 'conflicting' && (
              <span className="brief-warning-text">⚠ Conflicting information requires review</span>
            )}
          </div>
        )}
        <div className={`brief-item ${redFlags.length > 0 ? 'brief-alert' : ''}`}>
          <span>Red flags</span>
          {redFlags.length === 0 ? (
            <strong>No red flags detected</strong>
          ) : (
            <strong>
              {redFlags.length} safety alert{redFlags.length === 1 ? '' : 's'}{' '}
              {redFlags.length === 1 ? 'requires' : 'require'} review
            </strong>
          )}
        </div>
        {documents.length > 0 && (
          <div className="brief-item">
            <span>Documents</span>
            <strong>
              {documents.length}{' '}
              {documents.length === 1
                ? documents[0].document_type.replaceAll('_', ' ')
                : 'uploaded documents'}
            </strong>
          </div>
        )}
        {coverage && (
          <div
            className={`brief-item ${conflicts > 0 || coverage.missing > 0 ? 'brief-warning' : ''}`}
          >
            <span>History coverage</span>
            {conflicts > 0 ? (
              <strong>
                ⚠ {conflicts} item{conflicts === 1 ? '' : 's'}{' '}
                {conflicts === 1 ? 'requires' : 'require'} review
              </strong>
            ) : coverage.missing === 0 && coverage.document_supported_unconfirmed === 0 ? (
              <strong>✓ Required history complete</strong>
            ) : (
              <strong>
                {coverage.missing} required item{coverage.missing === 1 ? '' : 's'} missing
              </strong>
            )}
          </div>
        )}
        {(visitToken || queueStatus) && (
          <div className="brief-item">
            <span>Queue</span>
            {visitToken && <strong>{visitToken}</strong>}
            {queueStatus && <span>{queueStatus.replaceAll('_', ' ').toLowerCase()}</span>}
            {queue && <span>Approx. waiting time: {queue.estimated_wait_minutes} min</span>}
          </div>
        )}
      </div>
      <div className="brief-sources" aria-label="Information sources">
        <strong>Information sources</strong>
        {detail.answers.length > 0 && <span className="source-badge">Patient answers</span>}
        {documents.some((document) => document.document_type === 'prescription') && (
          <span className="source-badge">Prescription</span>
        )}
        {medication?.status === 'patient_confirmed' && (
          <span className="source-badge">Patient-confirmed evidence</span>
        )}
        {conflicts > 0 && <span className="source-badge warning">Conflict requires review</span>}
      </div>
    </section>
  );
}
