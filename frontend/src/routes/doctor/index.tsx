import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../../api/client';
import type {
  Detail,
  SessionList,
  TranslationResult,
  TransliterationResult,
} from '../../api/client';
import { copy, errorText } from '../../i18n';
import { useOptionalAuth } from '../../context/AuthContext';
import NormalizationPanel from '../../components/doctor/NormalizationPanel';
import DocumentViewer from '../../components/doctor/DocumentViewer';
import ClinicalEvidencePanel from '../../components/doctor/ClinicalEvidencePanel';
import SummaryWorkspace from '../../components/doctor/SummaryWorkspace';
import { FieldVerificationBadge } from '../../components/doctor/FieldVerificationBadge';
import { AuditTrailViewer } from '../../components/doctor/AuditTrailViewer';
import { FHIRExportModal } from '../../components/doctor/FHIRExportModal';
import { ABDMHISModal } from '../../components/doctor/ABDMHISModal';

const t = copy.en;

function alertStatusText(alert: NonNullable<Detail['alerts']>[number]) {
  if (alert.status === 'acknowledged') {
    return `✓ Acknowledged by ${alert.acknowledged_by ?? 'clinical staff'}`;
  }
  if (alert.status === 'resolved') {
    return 'Resolved · retained in the audit history';
  }
  return '⚠️ Potential emergency symptoms detected · immediate clinical assessment recommended';
}

export default function Doctor() {
  const { sessionId } = useParams();
  const [list, setList] = useState<SessionList | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy] = useState(false);
  const navigate = useNavigate();
  const auth = useOptionalAuth();
  const [loggingIn, setLoggingIn] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [fhirModalOpen, setFhirModalOpen] = useState(false);
  const [abdmModalOpen, setAbdmModalOpen] = useState(false);
  const [translations, setTranslations] = useState<Record<string, TranslationResult>>({});
  const [transliterations, setTransliterations] = useState<Record<string, TransliterationResult>>(
    {},
  );
  const [translatingFieldId, setTranslatingFieldId] = useState<string | null>(null);

  async function handleTranslate(fieldId: string, text: string, sourceLang: string) {
    if (!detail) return;
    setTranslatingFieldId(fieldId);
    try {
      const res = await api.translate(detail.session.id, text, sourceLang, 'en');
      if (res.status === 'success') {
        setTranslations((prev) => ({ ...prev, [fieldId]: res }));
      }
    } catch {
      // Non-critical assistive action; errors do not block clinical review
    } finally {
      setTranslatingFieldId(null);
    }
  }

  async function handleTransliterate(fieldId: string, text: string, sourceLang: string) {
    if (!detail) return;
    try {
      const res = await api.transliterate(detail.session.id, text, sourceLang, 'en');
      if (res.status === 'success') {
        setTransliterations((prev) => ({ ...prev, [fieldId]: res }));
      }
    } catch {
      // Non-critical
    }
  }

  useEffect(() => {
    let active = true;
    if (sessionId) {
      api
        .doctorDetail(sessionId)
        .then((result) => {
          if (!active) return;
          setTranslations({});
          setTransliterations({});
          setDetail(result);
          setLoading(false);
          setError(null);
        })
        .catch((err) => {
          if (active) {
            setError(err);
            setLoading(false);
          }
        });
    } else {
      api
        .sessions()
        .then((result) => {
          if (active) {
            setList(result);
            setLoading(false);
            setError(null);
          }
        })
        .catch((err) => {
          if (active) {
            setError(err);
            setLoading(false);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [sessionId, attempt]);
  function refresh() {
    setLoading(true);
    setNotice('');
    setAttempt(attempt + 1);
  }

  async function handleSeedShowcase() {
    setLoading(true);
    setError(null);
    setNotice('');
    try {
      const res = await api.seedShowcase();
      setNotice(
        `Showcase patient ${res.patient_name} (${res.hospital_token}) seeded successfully!`,
      );
      setAttempt((a) => a + 1);
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  }

  async function handleResetDemo() {
    if (
      typeof window !== 'undefined' &&
      !window.confirm('Reset all demo patient intake records? Doctor accounts will be preserved.')
    ) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice('');
    try {
      const res = await api.resetDemo();
      setNotice(res.message || 'Demo data reset successfully.');
      setAttempt((a) => a + 1);
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  }

  const summary = detail?.summary;
  return (
    <div className="doctor-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t.overview}</p>
          <h1>{sessionId ? t.detailTitle : t.doctorTitle}</h1>
          <p className="muted">{t.doctorIntro}</p>
        </div>
        <div className="doctor-header-actions">
          <button
            type="button"
            className="secondary"
            data-testid="seed-showcase-btn"
            onClick={() => void handleSeedShowcase()}
            disabled={busy || loading}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
            title="Seed canonical Bengali chest-pain showcase patient"
          >
            <span>🌟</span> Seed Showcase
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="reset-demo-btn"
            onClick={() => void handleResetDemo()}
            disabled={busy || loading}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#b91c1c' }}
            title="Reset all demo intake data while preserving doctor user accounts"
          >
            <span>🔄</span> Reset Demo
          </button>
          <button className="secondary" onClick={refresh} disabled={busy || loading}>
            {t.refresh}
          </button>
        </div>
      </div>
      <p className="notice">{t.demoDoctor}</p>
      {Boolean(error) && (
        <div className="error" role="alert">
          <div style={{ marginBottom: '8px' }}>
            {errorText(error)}
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="secondary" onClick={refresh} disabled={loggingIn}>
              {t.reload}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                setLoggingIn(true);
                try {
                  if (auth?.demoLogin) {
                    await auth.demoLogin('doctor');
                  }
                  navigate('/doctor', { replace: true });
                  refresh();
                } catch { /* ignore */ } finally {
                  setLoggingIn(false);
                }
              }}
              disabled={loggingIn}
              title="Sign in as Demo Doctor to restore access"
            >
              {loggingIn ? 'Signing in…' : '🔐 Demo Doctor Login'}
            </button>
          </div>
        </div>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {loading && <p role="status">{t.loading}</p>}
      {!loading && !sessionId && list && (
        <section className="session-list">
          {list.items.length === 0 && (
            <div className="card empty">
              <h2>{t.empty}</h2>
              <p>{t.emptyNote}</p>
              <Link to="/kiosk/language">{t.kiosk} →</Link>
            </div>
          )}
          {list.items.map((session) => (
            <Link className="session-card" key={session.id} to={'/doctor/sessions/' + session.id}>
              <span className="avatar" aria-hidden="true">
                {session.patient_name.charAt(0).toUpperCase()}
              </span>
              <div>
                <h2>{session.patient_name}</h2>
                <p className="muted">
                  {session.hospital_token} · {session.language.toUpperCase()}
                </p>
              </div>
              <span className={'badge ' + session.status}>{t[session.status]}</span>
              {session.queue_status && <span className="badge">Queue: {session.queue_status.replaceAll('_', ' ')}</span>}
              <span className="review-link">{t.open} →</span>
            </Link>
          ))}
        </section>
      )}
      {!loading && sessionId && detail && (
        <>
          <Link to="/doctor" className="back-link">
            ← {t.allSessions}
          </Link>
          <div className="patient-heading">
            <div>
              <h2>{detail.patient.name}</h2>
              <p className="muted">
                {detail.session.hospital_token} · {detail.session.language.toUpperCase()}
              </p>
            </div>
            <div className="doctor-header-actions">
              <button type="button" className="secondary" onClick={async () => { await api.updateQueue(detail.session.id, 'IN_CONSULTATION'); refresh(); }}>Start consultation</button>
              <button type="button" className="secondary" onClick={async () => { await api.updateQueue(detail.session.id, 'COMPLETED'); refresh(); }}>Complete consultation</button>
              <button
                type="button"
                className="btn btn-secondary"
                data-testid="export-fhir-btn"
                onClick={() => setFhirModalOpen(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  fontSize: '13px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  color: '#1e293b',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                <span>📦</span> Export FHIR R4
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                data-testid="abdm-his-btn"
                onClick={() => setAbdmModalOpen(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  fontSize: '13px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  color: '#1e293b',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                <span>🏥</span> ABDM & HIS
              </button>
              <span className={'badge ' + detail.session.status}>{t[detail.session.status]}</span>
            </div>
          </div>
          {detail.alerts && detail.alerts.length > 0 && (
            <section
              className="card doctor-alerts-banner"
              aria-label="Triage Safety Alerts"
              data-testid="doctor-alerts-banner"
            >
              <div className="alerts-banner-header">
                <h3>⚠️ Safety Screening Alerts ({detail.alerts.length})</h3>
              </div>
              <div className="alerts-banner-list">
                {detail.alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className={`doctor-alert-item ${alert.priority} ${
                      alert.priority === 'emergency' ? 'emergency-pulse-border' : ''
                    }`}
                    style={
                      alert.priority === 'emergency'
                        ? {
                            border: '2px solid #ef4444',
                            backgroundColor: '#fef2f2',
                            boxShadow: '0 0 12px rgba(239, 68, 68, 0.25)',
                          }
                        : undefined
                    }
                  >
                    <div className="alert-meta">
                      <span
                        className={`priority-tag ${alert.priority}`}
                        style={
                          alert.priority === 'emergency'
                            ? {
                                backgroundColor: '#dc2626',
                                color: '#ffffff',
                                fontWeight: 700,
                              }
                            : undefined
                        }
                      >
                        {alert.priority === 'emergency'
                          ? '🚨 EMERGENCY'
                          : alert.priority.toUpperCase()}
                      </span>
                      <span className="rule-tag">{alert.rule_id}</span>
                      <span className="category-tag">{alert.category}</span>
                      <span className={`status-tag status-${alert.status}`}>
                        {alertStatusText(alert)}
                      </span>
                    </div>
                    <p
                      className="alert-reason-text"
                      style={{
                        fontWeight: 500,
                        color: alert.priority === 'emergency' ? '#991b1b' : undefined,
                      }}
                    >
                      {alert.reason}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}
          <div className="review-grid">
            <section className="card history">
              <h2>{t.detailTitle}</h2>
              <p className="eyebrow">{t.patientReported}</p>
              {detail.history ? (
                <>
                  <p>
                    <strong>{detail.history.selected_complaint.en}</strong> ·{' '}
                    {detail.history.flow_version}
                  </p>
                  {detail.history.namespace === 'ayush_demo' && (
                    <p className="notice">AYUSH demonstration only. No interpretation.</p>
                  )}
                  {detail.history.sections
                    .filter((section) => section.facts.length > 0)
                    .map((section) => (
                      <section key={section.section_id}>
                        <h3>{section.label.en}</h3>
                        <dl>
                          {section.facts.map((fact) => (
                            <div key={fact.question_id}>
                              <dt
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                }}
                              >
                                <span>{fact.label.en}</span>
                                <FieldVerificationBadge
                                  sessionId={detail.session.id}
                                  fieldType="interview_answer"
                                  fieldId={fact.question_id}
                                  disabled={
                                    detail.session.status === 'confirmed' ||
                                    detail.session.status === 'cancelled'
                                  }
                                />
                              </dt>
                              <dd
                                lang={fact.language}
                                style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}
                              >
                                <div
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                  }}
                                >
                                  <span lang={fact.language}>{fact.raw_value}</span>

                                  {fact.language !== 'en' && (
                                    <span style={{ display: 'inline-flex', gap: '6px' }}>
                                      <button
                                        type="button"
                                        data-testid={`translate-btn-${fact.question_id}`}
                                        disabled={translatingFieldId === fact.question_id}
                                        onClick={() =>
                                          handleTranslate(
                                            fact.question_id,
                                            fact.raw_value,
                                            fact.language,
                                          )
                                        }
                                        style={{
                                          fontSize: '0.75rem',
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          border: '1px solid #93c5fd',
                                          backgroundColor: '#eff6ff',
                                          color: '#1d4ed8',
                                          cursor: 'pointer',
                                        }}
                                      >
                                        {translatingFieldId === fact.question_id
                                          ? '...'
                                          : '🌐 Translate'}
                                      </button>
                                      <button
                                        type="button"
                                        data-testid={`transliterate-btn-${fact.question_id}`}
                                        onClick={() =>
                                          handleTransliterate(
                                            fact.question_id,
                                            fact.raw_value,
                                            fact.language,
                                          )
                                        }
                                        style={{
                                          fontSize: '0.75rem',
                                          padding: '2px 6px',
                                          borderRadius: '4px',
                                          border: '1px solid #cbd5e1',
                                          backgroundColor: '#f8fafc',
                                          color: '#475569',
                                          cursor: 'pointer',
                                        }}
                                      >
                                        🔤 Transliterate
                                      </button>
                                    </span>
                                  )}
                                </div>
                                {translations[fact.question_id] && (
                                  <div
                                    data-testid={`translation-box-${fact.question_id}`}
                                    style={{
                                      padding: '6px 8px',
                                      backgroundColor: '#eff6ff',
                                      borderLeft: '3px solid #3b82f6',
                                      borderRadius: '4px',
                                      fontSize: '0.82rem',
                                    }}
                                  >
                                    <span style={{ fontWeight: 600, color: '#1e40af' }}>
                                      🌐 Translation ({translations[fact.question_id].provider} ·{' '}
                                      {translations[fact.question_id].model}):
                                    </span>{' '}
                                    <span>
                                      &ldquo;{translations[fact.question_id].translated_text}&rdquo;
                                    </span>
                                    <p
                                      className="muted"
                                      style={{ fontSize: '0.72rem', margin: '2px 0 0 0' }}
                                    >
                                      {translations[fact.question_id].provenance_note}
                                    </p>
                                  </div>
                                )}
                                {transliterations[fact.question_id] && (
                                  <div
                                    data-testid={`transliteration-box-${fact.question_id}`}
                                    style={{
                                      padding: '4px 8px',
                                      backgroundColor: '#f1f5f9',
                                      borderLeft: '3px solid #64748b',
                                      borderRadius: '4px',
                                      fontSize: '0.82rem',
                                    }}
                                  >
                                    <span style={{ fontWeight: 600, color: '#334155' }}>
                                      🔤 Latin Transliteration:
                                    </span>{' '}
                                    <span style={{ fontStyle: 'italic' }}>
                                      {transliterations[fact.question_id].transliterated_text}
                                    </span>
                                  </div>
                                )}
                              </dd>
                              <dd>
                                <NormalizationPanel result={fact.normalization} />
                              </dd>
                              <dd className="muted">
                                Patient reported · {fact.source} · {fact.language.toUpperCase()} ·{' '}
                                {fact.status.replace('_', ' ')}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </section>
                    ))}
                </>
              ) : (
                <dl>
                  {detail.answers.map((answer) => (
                    <div key={answer.id}>
                      <dt
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <span>{answer.field.replaceAll('_', ' ')}</span>
                        <FieldVerificationBadge
                          sessionId={detail.session.id}
                          fieldType="interview_answer"
                          fieldId={answer.field}
                          disabled={
                            detail.session.status === 'confirmed' ||
                            detail.session.status === 'cancelled'
                          }
                        />
                      </dt>
                      <dd
                        lang={answer.language}
                        style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                          }}
                        >
                          <span lang={answer.language}>{answer.raw_value}</span>

                          {answer.language !== 'en' && (
                            <span style={{ display: 'inline-flex', gap: '6px' }}>
                              <button
                                type="button"
                                data-testid={`translate-btn-${answer.field}`}
                                disabled={translatingFieldId === answer.field}
                                onClick={() =>
                                  handleTranslate(answer.field, answer.raw_value, answer.language)
                                }
                                style={{
                                  fontSize: '0.75rem',
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  border: '1px solid #93c5fd',
                                  backgroundColor: '#eff6ff',
                                  color: '#1d4ed8',
                                  cursor: 'pointer',
                                }}
                              >
                                {translatingFieldId === answer.field ? '...' : '🌐 Translate'}
                              </button>
                            </span>
                          )}
                        </div>
                        {translations[answer.field] && (
                          <div
                            data-testid={`translation-box-${answer.field}`}
                            style={{
                              padding: '6px 8px',
                              backgroundColor: '#eff6ff',
                              borderLeft: '3px solid #3b82f6',
                              borderRadius: '4px',
                              fontSize: '0.82rem',
                            }}
                          >
                            <span style={{ fontWeight: 600, color: '#1e40af' }}>
                              🌐 Translation ({translations[answer.field].provider}):
                            </span>{' '}
                            <span>&ldquo;{translations[answer.field].translated_text}&rdquo;</span>
                            <p
                              className="muted"
                              style={{ fontSize: '0.72rem', margin: '2px 0 0 0' }}
                            >
                              {translations[answer.field].provenance_note}
                            </p>
                          </div>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
              {summary && (
                <details>
                  <summary>{t.draft}</summary>
                  <p className="muted">{t.draftNote}</p>
                  <pre className="draft">{summary.generated_text}</pre>
                </details>
              )}
            </section>
            {summary ? (
              <SummaryWorkspace
                sessionId={detail.session.id}
                initialSummary={summary}
                onSummaryUpdated={(updatedSummary) => {
                  setDetail((prev) =>
                    prev
                      ? {
                          ...prev,
                          summary: updatedSummary,
                          session: {
                            ...prev.session,
                            status:
                              updatedSummary.status === 'confirmed'
                                ? 'confirmed'
                                : updatedSummary.status === 'reviewed'
                                  ? 'under_review'
                                  : prev.session.status,
                          },
                        }
                      : prev,
                  );
                }}
              />
            ) : (
              <section className="card editor">
                <h2>{t.reviewed}</h2>
                <p>{t.notReady}</p>
              </section>
            )}
          </div>
          <ClinicalEvidencePanel
            key={detail.session.id}
            sessionId={detail.session.id}
            locked={detail.session.status === 'confirmed' || detail.session.status === 'cancelled'}
          />
          {detail.documents && detail.documents.length > 0 && (
            <DocumentViewer
              locked={
                detail.session.status === 'confirmed' || detail.session.status === 'cancelled'
              }
              sessionId={detail.session.id}
              documents={detail.documents}
              onVerificationUpdate={(updatedExtraction) => {
                setDetail((prev) => {
                  if (!prev || !prev.documents) return prev;
                  return {
                    ...prev,
                    documents: prev.documents.map((doc) => ({
                      ...doc,
                      extractions: doc.extractions.map((ext) =>
                        ext.id === updatedExtraction.id ? updatedExtraction : ext,
                      ),
                    })),
                  };
                });
              }}
            />
          )}
          <AuditTrailViewer
            key={`audit-trail-${detail.session.id}`}
            sessionId={detail.session.id}
          />
          <FHIRExportModal
            isOpen={fhirModalOpen}
            onClose={() => setFhirModalOpen(false)}
            sessionId={detail.session.id}
            patientName={detail.patient.name}
            hospitalToken={detail.session.hospital_token}
          />
          <ABDMHISModal
            isOpen={abdmModalOpen}
            onClose={() => setAbdmModalOpen(false)}
            sessionId={detail.session.id}
            patientName={detail.patient.name}
            hospitalToken={detail.session.hospital_token}
            demoAbhaId={detail.patient.demo_abha_id}
          />
        </>
      )}
    </div>
  );
}
