import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type {
  EvidenceReference,
  Summary,
  SummaryRevisionRecord,
} from '../../api/client';
import { copy, errorText } from '../../i18n';
import { FieldVerificationBadge } from './FieldVerificationBadge';
import { SummaryAmendmentModal } from './SummaryAmendmentModal';

interface SummaryWorkspaceProps {
  sessionId: string;
  initialSummary: Summary;
  onSummaryUpdated: (updatedSummary: Summary) => void;
}

const t = copy.en;

export default function SummaryWorkspace({
  sessionId,
  initialSummary,
  onSummaryUpdated,
}: SummaryWorkspaceProps) {
  const [summary, setSummary] = useState<Summary>(initialSummary);
  const [editorText, setEditorText] = useState<string>(
    initialSummary.reviewed_text || initialSummary.generated_text || '',
  );
  const [reviewNotes, setReviewNotes] = useState('');
  const [activeTab, setActiveTab] = useState<'editor' | 'evidence' | 'revisions'>('editor');
  const [revisions, setRevisions] = useState<SummaryRevisionRecord[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceReference[]>(
    initialSummary.evidence || [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [showAmendModal, setShowAmendModal] = useState(false);

  const [prevSummaryKey, setPrevSummaryKey] = useState(
    `${initialSummary.id}-${initialSummary.version}-${initialSummary.status}`,
  );
  if (prevSummaryKey !== `${initialSummary.id}-${initialSummary.version}-${initialSummary.status}`) {
    setPrevSummaryKey(`${initialSummary.id}-${initialSummary.version}-${initialSummary.status}`);
    setSummary(initialSummary);
    setEditorText(initialSummary.reviewed_text || initialSummary.generated_text || '');
    if (initialSummary.evidence && initialSummary.evidence.length > 0) {
      setEvidenceList(initialSummary.evidence);
    }
  }

  // Load revisions and evidence on tab selection
  useEffect(() => {
    let active = true;
    if (activeTab === 'revisions') {
      api
        .getSummaryRevisions(sessionId)
        .then((data) => {
          if (active) setRevisions(data);
        })
        .catch(() => {});
    } else if (activeTab === 'evidence' && evidenceList.length === 0) {
      api
        .getSummaryEvidence(sessionId)
        .then((data) => {
          if (active) setEvidenceList(data);
        })
        .catch(() => {});
    }
    return () => {
      active = false;
    };
  }, [activeTab, sessionId, evidenceList.length]);

  const isConfirmed = summary.status === 'confirmed';
  const isDirty = editorText.trim() !== (summary.reviewed_text || '').trim();

  const handleSaveReview = async () => {
    if (isConfirmed || !editorText.trim()) return;
    setBusy(true);
    setError(null);
    setNotice('');
    try {
      const notes = reviewNotes.trim();
      const updated = notes
        ? await api.saveSummary(sessionId, editorText.trim(), summary.version, notes)
        : await api.saveSummary(sessionId, editorText.trim(), summary.version);
      setSummary(updated);
      setEditorText(updated.reviewed_text || '');
      setReviewNotes('');
      setNotice(t.savedReview);
      onSummaryUpdated(updated);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async (confirmReplacement = false) => {
    if (isConfirmed) return;
    setBusy(true);
    setError(null);
    setNotice('');
    try {
      const notes = reviewNotes.trim();
      const updated = notes
        ? await api.regenerateSummary(sessionId, summary.version, notes, confirmReplacement)
        : await api.regenerateSummary(sessionId, summary.version, undefined, confirmReplacement);
      setSummary(updated);
      setEditorText(updated.reviewed_text || updated.generated_text || '');
      setShowRegenModal(false);
      setNotice('Draft regenerated from latest clinical facts.');
      onSummaryUpdated(updated);
    } catch (err: unknown) {
      const code =
        err && typeof err === 'object' && 'code' in err
          ? String((err as { code: unknown }).code)
          : '';
      if (code === 'CONFIRM_REPLACEMENT_REQUIRED') {
        setShowRegenModal(true);
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmSummary = async () => {
    if (isConfirmed) return;
    if (!window.confirm(t.confirmPrompt)) return;
    setBusy(true);
    setError(null);
    setNotice('');
    try {
      const notes = reviewNotes.trim();
      const updated = notes
        ? await api.confirm(sessionId, summary.version, notes)
        : await api.confirm(sessionId, summary.version);
      setSummary(updated);
      setReviewNotes('');
      setNotice(t.confirmSuccess);
      onSummaryUpdated(updated);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card editor summary-workspace" data-testid="summary-workspace">
      <div className="summary-workspace-header" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div>
            <h2>{t.reviewed}</h2>
            <p className="muted" style={{ margin: '0.25rem 0 0 0' }}>
              Clinician-controlled draft · Deterministic synthesis · Non-diagnostic
            </p>
          </div>
          <div className="summary-meta-badges" style={{ display: 'flex', gap: '0.5rem' }}>
            <span className={`badge ${summary.status}`}>
              {summary.status === 'confirmed'
                ? t.confirmed
                : summary.status === 'reviewed'
                ? t.reviewed
                : 'Generated Draft'}
            </span>
            <span className="badge version-badge">
              v{summary.version} (Draft v{summary.draft_version || 1})
            </span>
          </div>
        </div>
      </div>

      {Boolean(error) && (
        <div className="error" role="alert" style={{ marginBottom: '1rem' }}>
          {errorText(error)}
        </div>
      )}

      {notice && (
        <p className="success" role="status" style={{ marginBottom: '1rem' }}>
          {notice}
        </p>
      )}

      <div className="summary-tabs-nav" style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.5rem' }}>
        <button
          type="button"
          className={activeTab === 'editor' ? 'primary' : 'secondary'}
          onClick={() => setActiveTab('editor')}
        >
          Summary Editor
        </button>
        <button
          type="button"
          className={activeTab === 'evidence' ? 'primary' : 'secondary'}
          onClick={() => setActiveTab('evidence')}
        >
          Evidence Attribution ({evidenceList.length})
        </button>
        <button
          type="button"
          className={activeTab === 'revisions' ? 'primary' : 'secondary'}
          onClick={() => setActiveTab('revisions')}
        >
          Revision History
        </button>
      </div>

      {/* TAB 1: SUMMARY EDITOR */}
      {activeTab === 'editor' && (
        <div className="summary-tab-content editor-tab">
          <p className="muted">{isConfirmed ? t.readOnly : t.editHelp}</p>
          <label htmlFor="review">{t.reviewed}</label>
          <textarea
            id="review"
            aria-label="Reviewed summary"
            rows={15}
            value={editorText}
            disabled={busy}
            readOnly={isConfirmed}
            maxLength={64000}
            style={{ width: '100%', marginBottom: '1rem' }}
            onChange={(e) => {
              setEditorText(e.target.value);
              setNotice('');
            }}
          />

          {!isConfirmed && (
            <div style={{ marginBottom: '1rem' }}>
              <label htmlFor="review-notes-input" style={{ fontSize: '0.85rem' }}>
                Revision Notes (Optional)
              </label>
              <input
                id="review-notes-input"
                type="text"
                placeholder="Brief clinical rationale for changes..."
                value={reviewNotes}
                disabled={busy}
                maxLength={1000}
                style={{ width: '100%', padding: '0.4rem 0.6rem' }}
                onChange={(e) => setReviewNotes(e.target.value)}
              />
            </div>
          )}

          {!isConfirmed && (
            <>
              {isDirty && <p className="muted">{t.saveFirst}</p>}
              <div className="actions stacked">
                <button
                  type="button"
                  disabled={busy || !editorText.trim()}
                  onClick={handleSaveReview}
                >
                  {busy ? t.saving : t.save}
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => handleRegenerate(false)}
                >
                  Regenerate Draft
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || isDirty || summary.status !== 'reviewed'}
                  onClick={handleConfirmSummary}
                >
                  {t.confirm}
                </button>
              </div>
            </>
          )}

          {(isConfirmed || summary.status === 'amended') && (
            <div style={{ marginTop: '1rem' }}>
              <div className="success">
                <strong>{t.confirmed}</strong>
                <p>
                  {t.confirmedBy}: {summary.confirmed_by}
                </p>
                <p>
                  {t.confirmedAt}:{' '}
                  {summary.confirmed_at && new Date(summary.confirmed_at).toLocaleString()}
                </p>
              </div>

              <div style={{ marginTop: '1rem' }}>
                <button
                  type="button"
                  className="secondary"
                  data-testid="file-amendment-button"
                  onClick={() => setShowAmendModal(true)}
                  style={{
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    border: 'none',
                    padding: '8px 14px',
                    borderRadius: '4px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  + File Clinical Amendment
                </button>
              </div>

              {summary.amended_text && (
                <div
                  className="card amendment-display"
                  data-testid="amendment-display"
                  style={{
                    marginTop: '1rem',
                    borderLeft: '4px solid #2563eb',
                    backgroundColor: '#f8fafc',
                    padding: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <h4 style={{ margin: 0, color: '#1e40af' }}>
                      📋 Official Clinical Amendment / Addendum
                    </h4>
                    <span className="badge" style={{ backgroundColor: '#dbeafe', color: '#1e40af' }}>
                      Amended
                    </span>
                  </div>
                  <p style={{ fontSize: '0.8rem', color: '#64748b', margin: '0 0 0.5rem 0' }}>
                    Amended by {summary.amended_by} at{' '}
                    {summary.amended_at && new Date(summary.amended_at).toLocaleString()}
                  </p>
                  {summary.amendment_notes && (
                    <p style={{ fontStyle: 'italic', fontSize: '0.85rem', color: '#334155', margin: '0 0 0.5rem 0' }}>
                      Clinical Reason: "{summary.amendment_notes}"
                    </p>
                  )}
                  <pre
                    className="draft"
                    style={{
                      whiteSpace: 'pre-wrap',
                      backgroundColor: '#ffffff',
                      padding: '0.75rem',
                      borderRadius: '4px',
                      border: '1px solid #e2e8f0',
                      fontSize: '0.85rem',
                    }}
                  >
                    {summary.amended_text}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: EVIDENCE ATTRIBUTION */}
      {activeTab === 'evidence' && (
        <div className="summary-tab-content evidence-tab">
          <p className="muted" style={{ marginBottom: '1rem' }}>
            Source attribution mapping. Every summary item traces deterministically to patient interview answers, medical facts, documents, or safety rules.
          </p>

          {evidenceList.length === 0 ? (
            <p className="muted">No evidence references recorded.</p>
          ) : (
            <div className="evidence-grid" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {evidenceList.map((ev, idx) => (
                <div
                  key={ev.statement_id || idx}
                  className="card evidence-item"
                  style={{
                    padding: '0.75rem 1rem',
                    backgroundColor: '#f8fafc',
                    borderLeft: '4px solid #3b82f6',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                    <span className="badge" style={{ backgroundColor: '#e0f2fe', color: '#0369a1' }}>
                      {ev.section.replace('_', ' ').toUpperCase()}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="badge" style={{ backgroundColor: '#f1f5f9', color: '#475569' }}>
                        Source: {ev.source_type}
                      </span>
                      <FieldVerificationBadge
                        sessionId={sessionId}
                        fieldType="summary_statement"
                        fieldId={ev.statement_id}
                      />
                    </div>
                  </div>
                  <p style={{ margin: '0.25rem 0', fontWeight: 600 }}>
                    {ev.statement_text}
                  </p>
                  <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                    <span>Original Source: <code>{ev.source_text}</code></span>
                    {ev.source_id && <span style={{ marginLeft: '1rem' }}>ID: <code>{ev.source_id.slice(0, 8)}</code></span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: REVISION HISTORY */}
      {activeTab === 'revisions' && (
        <div className="summary-tab-content revisions-tab">
          <p className="muted" style={{ marginBottom: '1rem' }}>
            Complete append-only audit trail of summary revisions.
          </p>

          {revisions.length === 0 ? (
            <p className="muted">Loading revisions…</p>
          ) : (
            <div className="revisions-list" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {revisions.map((rev) => (
                <div
                  key={rev.id}
                  className="card revision-card"
                  style={{
                    padding: '0.75rem 1rem',
                    borderLeft: rev.actor_type === 'DOCTOR' ? '4px solid #10b981' : '4px solid #6366f1',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div>
                      <strong>v{rev.version}</strong> ·{' '}
                      <span className="badge" style={{ textTransform: 'capitalize' }}>
                        {rev.revision_type.replace('_', ' ')}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b' }}>
                      {new Date(rev.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#475569', marginBottom: '0.5rem' }}>
                    <span>Actor: <strong>{rev.actor_type}</strong></span>
                    {rev.actor_name && <span style={{ marginLeft: '0.5rem' }}>({rev.actor_name})</span>}
                    {rev.actor_user_id && <span style={{ marginLeft: '0.5rem' }}><code>{rev.actor_user_id.slice(0, 8)}</code></span>}
                  </div>
                  {rev.review_notes && (
                    <p style={{ margin: '0.25rem 0', fontStyle: 'italic', fontSize: '0.9rem', color: '#334155' }}>
                      Notes: "{rev.review_notes}"
                    </p>
                  )}
                  <details style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                    <summary style={{ cursor: 'pointer', color: '#2563eb' }}>View Snapshot Text</summary>
                    <pre style={{ marginTop: '0.5rem', padding: '0.5rem', backgroundColor: '#f1f5f9', borderRadius: '0.25rem', whiteSpace: 'pre-wrap', maxHeight: '200px', overflowY: 'auto' }}>
                      {rev.reviewed_text}
                    </pre>
                  </details>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* REGENERATION CONFIRMATION MODAL */}
      {showRegenModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="regen-modal-title"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            className="card"
            style={{
              backgroundColor: '#fff',
              maxWidth: '500px',
              width: '90%',
              padding: '1.5rem',
              borderRadius: '0.5rem',
            }}
          >
            <h3 id="regen-modal-title" style={{ marginTop: 0 }}>Confirm Draft Regeneration</h3>
            <p style={{ color: '#dc2626', fontWeight: 500 }}>
              ⚠️ Manual edits currently exist on this summary.
            </p>
            <p className="muted" style={{ fontSize: '0.9rem' }}>
              Regenerating will replace your current working draft with a freshly constructed draft based on the latest interview answers and medical facts.
              Your previous edits will remain safely preserved in the Revision History.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setShowRegenModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                style={{ backgroundColor: '#dc2626', color: '#fff', borderColor: '#dc2626' }}
                disabled={busy}
                onClick={() => handleRegenerate(true)}
              >
                {busy ? 'Regenerating…' : 'Replace Draft'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AMENDMENT MODAL */}
      <SummaryAmendmentModal
        isOpen={showAmendModal}
        onClose={() => setShowAmendModal(false)}
        sessionId={sessionId}
        confirmedText={summary.reviewed_text || summary.generated_text || ''}
        onAmendmentSaved={(updated) => {
          setSummary(updated);
          setNotice('Clinical amendment filed successfully.');
          onSummaryUpdated(updated);
        }}
      />
    </section>
  );
}
