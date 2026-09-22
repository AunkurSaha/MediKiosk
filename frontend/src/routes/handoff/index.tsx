import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import type { PacketView } from '../../api/client';

export default function Handoff() {
  const { token = '' } = useParams();
  const [packet, setPacket] = useState<PacketView | null>(null);
  const [state, setState] = useState('Loading secure handoff…');
  useEffect(() => {
    api
      .resolveHandoff(token)
      .then((result) => {
        if ('status' in result && result.status === 'AUTH_REQUIRED') setState('AUTH_REQUIRED');
        else {
          setPacket(result as PacketView);
          setState('READY');
        }
      })
      .catch((err) => setState(err instanceof ApiError ? err.code : 'NETWORK_ERROR'));
  }, [token]);
  const safeMessage: Record<string, string> = {
    PACKET_NOT_FOUND: 'This handoff link is invalid.',
    HANDOFF_TOKEN_EXPIRED: 'This handoff link has expired.',
    PACKET_EXPIRED: 'This handoff link has expired.',
    PACKET_REVOKED: 'This handoff link is no longer active.',
    FORBIDDEN: 'You do not have access to this patient handoff.',
    NETWORK_ERROR: 'The handoff could not be loaded. Please try again.',
  };
  if (state === 'AUTH_REQUIRED')
    return (
      <section className="card">
        <h1>Clinician sign-in required</h1>
        <p>This secure handoff can only be opened by the assigned doctor.</p>
        <Link to={`/staff/login?redirect=${encodeURIComponent(`/handoff/p/${token}`)}`}>
          Sign in as clinician
        </Link>
      </section>
    );
  if (!packet)
    return (
      <section className="card">
        <h1>Secure pre-arrival handoff</h1>
        <p role={state === 'Loading secure handoff…' ? 'status' : 'alert'}>
          {safeMessage[state] ?? state}
        </p>
      </section>
    );
  const snapshot = packet.snapshot as {
    facility?: { name?: string };
    selected_doctor?: { name?: string };
    visit_context: { session_id: string };
    routing?: { routing_state?: string; suggested_specialty?: string };
    coverage?: { required: number; confirmed: number; missing: number; conflicted: number };
    documents?: { document_id: string; filename?: string; processing_status?: string }[];
    clinical_summary?: {
      sections?: { section_key: string; title: string; content_lines?: string[] }[];
      evidence_references?: {
        statement_id: string;
        statement_text: string;
        badge: string;
        provenance_explanation: string[];
      }[];
    };
    red_flags?: { alert_id: string; reason: string; rule_id: string }[];
    conflicts?: { conflict_id: string; reason: string }[];
  };
  return (
    <section className="card">
      <p className="eyebrow">Secure clinician handoff</p>
      <h1>Pre-arrival packet</h1>
      <p>
        Facility: {snapshot.facility?.name ?? 'Not available'} · Doctor:{' '}
        {snapshot.selected_doctor?.name ?? 'Not available'}
      </p>
      <p>
        Queue: {packet.live_queue?.visit_token ?? 'Pending'} (
        {packet.live_queue?.status ?? 'Not queued'})
      </p>
      <h2>Routing</h2>
      <p>
        {snapshot.routing?.routing_state ?? 'Not recorded'} ·{' '}
        {snapshot.routing?.suggested_specialty ?? 'Specialty not recorded'}
      </p>
      <h2>Clinical coverage</h2>
      {snapshot.coverage ? (
        <p>
          {snapshot.coverage.confirmed} confirmed of {snapshot.coverage.required} required;{' '}
          {snapshot.coverage.missing} missing; {snapshot.coverage.conflicted} conflicted.
        </p>
      ) : (
        <p>Not available.</p>
      )}
      <h2>Clinical summary</h2>
      {snapshot.clinical_summary?.sections?.map((section) => (
        <section key={section.section_key}>
          <h3>{section.title}</h3>
          {section.content_lines?.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </section>
      ))}
      <h2>Why is this here?</h2>
      {snapshot.clinical_summary?.evidence_references?.map((evidence) => (
        <details key={evidence.statement_id}>
          <summary>
            {evidence.statement_text} — {evidence.badge}
          </summary>
          {evidence.provenance_explanation.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </details>
      ))}
      <h2>Documents</h2>
      {snapshot.documents?.length ? (
        snapshot.documents.map((document) => (
          <p key={document.document_id}>
            {document.filename ?? document.document_id} —{' '}
            {document.processing_status ?? 'Needs verification'}
          </p>
        ))
      ) : (
        <p>None uploaded.</p>
      )}
      <h2>Red flags</h2>
      {snapshot.red_flags?.length ? (
        snapshot.red_flags.map((flag) => (
          <p key={flag.alert_id}>
            {flag.reason} — {flag.rule_id}
          </p>
        ))
      ) : (
        <p>None recorded.</p>
      )}
      <h2>Evidence conflicts</h2>
      {snapshot.conflicts?.length ? (
        snapshot.conflicts.map((conflict) => <p key={conflict.conflict_id}>{conflict.reason}</p>)
      ) : (
        <p>None recorded.</p>
      )}
      <Link to={`/doctor/sessions/${snapshot.visit_context.session_id}`}>
        Open full clinical workspace
      </Link>
    </section>
  );
}
