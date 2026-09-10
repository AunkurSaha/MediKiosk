import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../../api/client';
import type { Detail, SessionList } from '../../api/client';
import { copy, errorText } from '../../i18n';
import NormalizationPanel from '../../components/doctor/NormalizationPanel';
import DocumentViewer from '../../components/doctor/DocumentViewer';
import ClinicalEvidencePanel from '../../components/doctor/ClinicalEvidencePanel';
import SummaryWorkspace from '../../components/doctor/SummaryWorkspace';
import { FieldVerificationBadge } from '../../components/doctor/FieldVerificationBadge';
import { AuditTrailViewer } from '../../components/doctor/AuditTrailViewer';

const t = copy.en;
export default function Doctor() {
  const { sessionId } = useParams();
  const [list, setList] = useState<SessionList | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    if (sessionId) {
      api
        .doctorDetail(sessionId)
        .then((result) => {
          if (!active) return;
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
  const summary = detail?.summary;
  return (
    <div className="doctor-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t.overview}</p>
          <h1>{sessionId ? t.detailTitle : t.doctorTitle}</h1>
          <p className="muted">{t.doctorIntro}</p>
        </div>
        <button className="secondary" onClick={refresh} disabled={busy || loading}>
          {t.refresh}
        </button>
      </div>
      <p className="notice">{t.demoDoctor}</p>
      {Boolean(error) && (
        <div className="error" role="alert">
          {errorText(error)}{' '}
          <button className="secondary" onClick={refresh}>
            {t.reload}
          </button>
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
            <span className={'badge ' + detail.session.status}>{t[detail.session.status]}</span>
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
                  <div key={alert.id} className={`doctor-alert-item ${alert.priority}`}>
                    <div className="alert-meta">
                      <span className={`priority-tag ${alert.priority}`}>
                        {alert.priority.toUpperCase()}
                      </span>
                      <span className="rule-tag">{alert.rule_id}</span>
                      <span className="category-tag">{alert.category}</span>
                      <span className={`status-tag status-${alert.status}`}>
                        {alert.status === 'acknowledged'
                          ? `✓ Acknowledged by ${alert.acknowledged_by}`
                          : '⚠️ Active / Unacknowledged'}
                      </span>
                    </div>
                    <p className="alert-reason-text">{alert.reason}</p>
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
                              <dt style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span>{fact.label.en}</span>
                                <FieldVerificationBadge
                                  sessionId={detail.session.id}
                                  fieldType="interview_answer"
                                  fieldId={fact.question_id}
                                  disabled={detail.session.status === 'confirmed' || detail.session.status === 'cancelled'}
                                />
                              </dt>
                              <dd lang={fact.language}>{fact.raw_value}</dd>
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
                      <dt style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>{answer.field.replaceAll('_', ' ')}</span>
                        <FieldVerificationBadge
                          sessionId={detail.session.id}
                          fieldType="interview_answer"
                          fieldId={answer.field}
                          disabled={detail.session.status === 'confirmed' || detail.session.status === 'cancelled'}
                        />
                      </dt>
                      <dd lang={answer.language}>{answer.raw_value}</dd>
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
          <AuditTrailViewer key={`audit-trail-${detail.session.id}`} sessionId={detail.session.id} />
        </>
      )}
    </div>
  );
}
