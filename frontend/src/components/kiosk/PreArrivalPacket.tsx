import { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { api, ApiError } from '../../api/client';
import type { HandoffTokenIssued, PacketMetadata, PacketView } from '../../api/client';

export default function PreArrivalPacket({ sessionId }: { sessionId: string }) {
  const [packet, setPacket] = useState<PacketMetadata | null>(null);
  const [view, setView] = useState<PacketView | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [issued, setIssued] = useState<HandoffTokenIssued | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .createPacket(sessionId)
      .then(async (value) => {
        if (!active) return;
        setPacket(value);
        if (value.status === 'ACTIVE') {
          const snapshot = await api.packet(sessionId).catch(() => null);
          if (active) setView(snapshot);
        }
      })
      .catch(() => {
        if (active) setError('The pre-arrival packet could not be prepared.');
      })
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [sessionId]);

  const showQr = async () => {
    setBusy(true);
    setError(null);
    setIssued(null);
    try {
      setIssued(await api.issueHandoffToken(sessionId));
    } catch (err) {
      setError(err instanceof ApiError ? err.code : 'The secure QR could not be created.');
    } finally {
      setBusy(false);
    }
  };
  const showSummary = async () => {
    setSummaryOpen(true);
    setBusy(true);
    setError(null);
    try {
      setView(await api.packet(sessionId));
    } catch {
      setError('The packet summary could not be loaded.');
    } finally {
      setBusy(false);
    }
  };
  const revoke = async () => {
    setBusy(true);
    setError(null);
    try {
      setPacket(await api.revokePacket(sessionId));
      setIssued(null);
    } catch {
      setError('The packet could not be revoked.');
    } finally {
      setBusy(false);
    }
  };
  const qrValue = issued ? `${window.location.origin}${issued.handoff_url}` : '';
  const facility = view?.snapshot.facility as { name?: string } | undefined;
  const doctor = view?.snapshot.selected_doctor as { name?: string } | undefined;
  const snapshot = view?.snapshot;
  const history = snapshot?.structured_history as unknown[] | undefined;
  const documents = snapshot?.documents as unknown[] | undefined;
  const summary = snapshot?.clinical_summary as
    { evidence_references?: unknown[] } | null | undefined;
  const redFlags = snapshot?.red_flags as unknown[] | undefined;
  return (
    <div className="card" aria-label="Pre-arrival packet">
      <h2>Your Pre-Arrival Packet</h2>
      <p>Prepared for your clinical team before consultation.</p>
      {packet?.status === 'ACTIVE' && <p className="packet-ready">✓ Secure handoff packet ready</p>}
      {packet?.status === 'REVOKED' && <p role="status">This packet has been revoked.</p>}
      {packet?.status === 'EXPIRED' && <p role="status">This packet has expired.</p>}
      {busy && <p role="status">Preparing secure handoff…</p>}
      {error && <p role="alert">{error}</p>}
      {packet?.status === 'ACTIVE' && (
        <div className="button-row packet-actions">
          <button type="button" onClick={showQr} disabled={busy}>
            Show Secure QR
          </button>
          <button type="button" className="secondary" onClick={showSummary} disabled={busy}>
            View Packet Summary
          </button>
          <button type="button" className="secondary" onClick={revoke} disabled={busy}>
            Revoke packet
          </button>
        </div>
      )}
      {issued && (
        <div aria-label="Secure handoff QR">
          <QRCodeSVG value={qrValue} size={192} title="Secure clinician handoff QR" />
          <p>
            <strong>Show this QR to authorized clinical staff.</strong>
          </p>
          <p>For your privacy, this QR does not contain your clinical record directly.</p>
        </div>
      )}
      {snapshot && (
        <details className="packet-contents" open>
          <summary>What will the doctor receive?</summary>
          <ul>
            {snapshot.chief_complaint != null && <li>Chief complaint</li>}
            {history && history.length > 0 && <li>Structured patient history</li>}
            {documents && documents.length > 0 && (
              <li>Uploaded document references and extracted information</li>
            )}
            {redFlags && <li>Red-flag status</li>}
            {summary && <li>Clinical summary for doctor review</li>}
            {summary?.evidence_references && summary.evidence_references.length > 0 && (
              <li>Evidence and source information</li>
            )}
          </ul>
        </details>
      )}
      {packet?.status === 'ACTIVE' && (
        <div className="packet-security-note">
          <strong>Secure handoff</strong>
          <p>
            The QR contains only an opaque secure link. Your medical information is not embedded
            directly in the QR.
          </p>
        </div>
      )}
      {view && summaryOpen && (
        <div>
          <h3>Packet summary</h3>
          <p>Facility: {facility?.name ?? 'Not available'}</p>
          <p>Doctor: {doctor?.name ?? 'Not available'}</p>
          <p>Chief complaint: {String(view.snapshot.chief_complaint ?? 'Not recorded')}</p>
        </div>
      )}
    </div>
  );
}
