import { useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { DocumentExtractionRecord, DocumentRecord } from '../../api/client';
import { copy } from '../../i18n';

interface DocumentViewerProps {
  sessionId: string;
  documents: DocumentRecord[];
  onVerificationUpdate?: (updatedExtraction: DocumentExtractionRecord) => void;
}

export default function DocumentViewer({
  sessionId,
  documents: initialDocuments,
  onVerificationUpdate,
}: DocumentViewerProps) {
  const t = copy.en;
  const [documents, setDocuments] = useState<DocumentRecord[]>(initialDocuments);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [doctorName, setDoctorName] = useState('Dr. Demo Doctor');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!documents || documents.length === 0) {
    return (
      <section className="card document-viewer-empty" data-testid="document-viewer-empty">
        <h2>{t.docDoctorReview}</h2>
        <p className="muted">{t.docNoDocuments}</p>
      </section>
    );
  }

  const currentDoc = documents[selectedIndex] || documents[0];
  const isImage = currentDoc.media_type.startsWith('image/');

  async function handleVerify(extractionId: string, status: 'verified' | 'rejected') {
    if (!doctorName.trim()) {
      setError('Please enter a doctor/clinician name.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.verifyExtraction(
        sessionId,
        currentDoc.id,
        extractionId,
        status,
        doctorName.trim(),
        notes.trim() || undefined,
      );

      // Update local state
      setDocuments((prevDocs) =>
        prevDocs.map((doc) => {
          if (doc.id !== currentDoc.id) return doc;
          return {
            ...doc,
            extractions: doc.extractions.map((ext) => (ext.id === updated.id ? updated : ext)),
          };
        }),
      );

      onVerificationUpdate?.(updated);
      setNotes('');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to update extraction verification.');
      } else {
        setError('Network error updating extraction verification.');
      }
    } finally {
      setBusy(false);
    }
  }

  const fileUrl = api.documentFileUrl(sessionId, currentDoc.id);

  return (
    <section className="card document-viewer-panel" data-testid="document-viewer-panel">
      <div className="doc-viewer-header">
        <div>
          <h2>{t.docDoctorReview}</h2>
          <p className="eyebrow">Auxiliary Ingestion · OCR Verification</p>
        </div>

        {documents.length > 1 && (
          <div className="doc-tabs">
            {documents.map((doc, idx) => (
              <button
                key={doc.id}
                type="button"
                className={`tab-btn ${idx === selectedIndex ? 'active' : 'secondary'}`}
                onClick={() => {
                  setSelectedIndex(idx);
                  setError(null);
                }}
              >
                {doc.original_filename} ({doc.document_type})
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="document-immutability-notice" role="note">
        <span aria-hidden="true">🔒</span>
        <span>{t.docImmutabilityNotice}</span>
      </div>

      <div className="doc-viewer-split-layout">
        {/* Left Column: Original Document File Preview */}
        <div className="doc-preview-column">
          <div className="preview-card">
            <div className="preview-meta">
              <strong>{currentDoc.original_filename}</strong>
              <span className="doc-badge doc-type-badge">{currentDoc.document_type}</span>
              <span className="muted" style={{ fontSize: '0.8rem' }}>
                ({Math.round(currentDoc.file_size_bytes / 1024)} KB · {currentDoc.media_type})
              </span>
            </div>

            <div className="file-preview-container">
              {isImage ? (
                <img
                  src={fileUrl}
                  alt={currentDoc.original_filename}
                  className="document-image-preview"
                  data-testid="document-image-preview"
                />
              ) : (
                <div className="pdf-preview-placeholder">
                  <p>📄 PDF Document</p>
                </div>
              )}
            </div>

            <div className="preview-actions">
              <a
                href={fileUrl}
                target="_blank"
                rel="noreferrer"
                className="button-link secondary"
                data-testid="open-document-link"
              >
                🔍 {t.docViewOriginal}
              </a>
            </div>
          </div>
        </div>

        {/* Right Column: Structured Extractions & Verification */}
        <div className="doc-extractions-column">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          {currentDoc.extractions && currentDoc.extractions.length > 0 ? (
            currentDoc.extractions.map((ext) => {
              const meds = ext.structured_json.medications;
              const labs = ext.structured_json.lab_observations;
              const isVerified = ext.verification_status === 'verified';
              const isRejected = ext.verification_status === 'rejected';

              return (
                <div
                  key={ext.id}
                  className={`extraction-verification-card status-${ext.verification_status}`}
                  data-testid={`extraction-card-${ext.id}`}
                >
                  <div className="ext-header">
                    <div>
                      <strong>Extractor: {ext.extractor}</strong> ({ext.extractor_version})
                      {ext.confidence !== null && (
                        <span className="muted" style={{ marginLeft: '8px' }}>
                          Confidence: {Math.round(ext.confidence * 100)}%
                        </span>
                      )}
                    </div>

                    <span
                      className={`verification-tag status-${ext.verification_status}`}
                      data-testid={`verification-status-${ext.id}`}
                    >
                      {isVerified
                        ? `✓ ${t.docVerified}`
                        : isRejected
                          ? `✗ ${t.docRejected}`
                          : `⚠️ ${t.docPendingVerification}`}
                    </span>
                  </div>

                  {/* Verification Audit Trail Info */}
                  {(isVerified || isRejected) && ext.verified_by && (
                    <div className="verification-audit-info">
                      <p className="muted" style={{ fontSize: '0.85rem', margin: '4px 0' }}>
                        {isVerified ? 'Verified by' : 'Rejected by'} <b>{ext.verified_by}</b>
                        {ext.verified_at ? ` on ${new Date(ext.verified_at).toLocaleString()}` : ''}
                      </p>
                      {ext.verification_notes && (
                        <p className="audit-notes" style={{ fontSize: '0.85rem', margin: '2px 0' }}>
                          <em>Notes: {ext.verification_notes}</em>
                        </p>
                      )}
                    </div>
                  )}

                  {/* Extracted Structured Medications */}
                  {meds && meds.length > 0 && (
                    <div className="extracted-section">
                      <h4>{t.docExtractedMedications}</h4>
                      <table className="doctor-facts-table">
                        <thead>
                          <tr>
                            <th>Medication</th>
                            <th>Dosage</th>
                            <th>Frequency</th>
                            <th>Duration</th>
                          </tr>
                        </thead>
                        <tbody>
                          {meds.map((m, idx) => (
                            <tr key={idx}>
                              <td>
                                <b>{m.name}</b>
                              </td>
                              <td>{m.dosage || '—'}</td>
                              <td>{m.frequency || '—'}</td>
                              <td>{m.duration || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Extracted Structured Lab Observations */}
                  {labs && labs.length > 0 && (
                    <div className="extracted-section">
                      <h4>{t.docExtractedLabs}</h4>
                      <table className="doctor-facts-table">
                        <thead>
                          <tr>
                            <th>Test</th>
                            <th>Value</th>
                            <th>Unit</th>
                            <th>Reference</th>
                            <th>Flag</th>
                          </tr>
                        </thead>
                        <tbody>
                          {labs.map((l, idx) => (
                            <tr key={idx} className={l.flag && l.flag !== 'normal' ? 'abnormal-row' : ''}>
                              <td>
                                <b>{l.test_name}</b>
                              </td>
                              <td>{l.value}</td>
                              <td>{l.unit || '—'}</td>
                              <td>{l.reference_range || '—'}</td>
                              <td>
                                {l.flag && l.flag !== 'normal' ? (
                                  <span className="badge-abnormal">{l.flag.toUpperCase()}</span>
                                ) : (
                                  'Normal'
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Raw Text View (collapsible) */}
                  {ext.raw_text && (
                    <details style={{ marginTop: '12px' }}>
                      <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>
                        Raw OCR Output
                      </summary>
                      <pre className="raw-ocr-text">{ext.raw_text}</pre>
                    </details>
                  )}

                  {/* Clinician Verification Controls */}
                  <div className="verification-controls-box">
                    <div className="clinician-inputs">
                      <label htmlFor={`doc-name-${ext.id}`}>
                        {t.docDoctorName}:
                        <input
                          id={`doc-name-${ext.id}`}
                          type="text"
                          value={doctorName}
                          onChange={(e) => setDoctorName(e.target.value)}
                          disabled={busy}
                        />
                      </label>

                      <label htmlFor={`doc-notes-${ext.id}`}>
                        {t.docVerificationNotes}:
                        <input
                          id={`doc-notes-${ext.id}`}
                          type="text"
                          placeholder="e.g. Confirmed against paper slip"
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          disabled={busy}
                        />
                      </label>
                    </div>

                    <div className="actions" style={{ marginTop: '8px' }}>
                      <button
                        type="button"
                        disabled={busy || isVerified}
                        onClick={() => handleVerify(ext.id, 'verified')}
                        data-testid={`btn-verify-${ext.id}`}
                      >
                        {busy ? t.saving : `✓ ${t.docVerifyAction}`}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy || isRejected}
                        onClick={() => handleVerify(ext.id, 'rejected')}
                        data-testid={`btn-reject-${ext.id}`}
                      >
                        {busy ? t.saving : `✗ ${t.docRejectAction}`}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <p className="muted">No extractions available for this document.</p>
          )}
        </div>
      </div>
    </section>
  );
}
