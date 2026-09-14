import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import type { Detail, Hospital, Language, PatientQueueEstimate } from '../../api/client';
import Interview from '../../components/kiosk/Interview';
import { copy, errorText, languages } from '../../i18n';
import { speechCopy } from '../../i18n/speech';

const sessionKey = 'medikiosk.session';

export function HospitalSelection({
  hospitals,
  load,
  busy,
  onSelect,
}: {
  hospitals: Hospital[] | null;
  load: () => Promise<void>;
  busy: boolean;
  onSelect: (hospitalId: string) => void;
}) {
  const [error, setError] = useState(false);
  const initialLoad = useRef(load);
  const shouldInitialLoad = useRef(hospitals === null);
  const refresh = () => {
    setError(false);
    void load().catch(() => setError(true));
  };
  useEffect(() => {
    if (shouldInitialLoad.current) void initialLoad.current().catch(() => setError(true));
  }, []); // load once on entry
  if (error)
    return (
      <div className="error" role="alert">
        <p>Hospitals could not be loaded.</p>
        <button className="secondary" onClick={refresh}>
          Retry
        </button>
      </div>
    );
  if (hospitals === null) return <p role="status">Loading hospitals…</p>;
  if (!hospitals.length)
    return (
      <div className="card empty">
        <h1>No hospitals are currently available.</h1>
        <p>Please contact the registration desk.</p>
        <button className="secondary" onClick={refresh}>
          Retry
        </button>
      </div>
    );
  return (
    <>
      <h1>Which hospital are you visiting today?</h1>
      <p className="muted">This selection applies to this visit only.</p>
      <div className="language-grid" data-testid="hospital-list">
        {hospitals.map((hospital) => (
          <button
            className="language-card"
            key={hospital.id}
            disabled={busy}
            onClick={() => onSelect(hospital.id)}
          >
            <strong>{hospital.name}</strong>
            <span>{[hospital.address, hospital.city].filter(Boolean).join(' · ')}</span>
            <span aria-hidden="true">→</span>
          </button>
        ))}
      </div>
    </>
  );
}

export default function Kiosk() {
  const navigate = useNavigate();
  const location = useLocation();
  const [resumeId, setResumeId] = useState(() => sessionStorage.getItem(sessionKey));
  const pendingId = useRef(resumeId);
  const [language, setLanguage] = useState<Language>('en');
  const [record, setRecord] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(Boolean(resumeId));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [name, setName] = useState('');
  const [token, setToken] = useState('');
  const [abha, setAbha] = useState('');
  const [abhaVerified, setAbhaVerified] = useState(false);
  const [abhaChecking, setAbhaChecking] = useState(false);
  const [abhaMessage, setAbhaMessage] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [voiceAgreed, setVoiceAgreed] = useState(false);
  const [docAgreed, setDocAgreed] = useState(false);
  const [hospitals, setHospitals] = useState<Hospital[] | null>(null);
  const [queueEstimate, setQueueEstimate] = useState<PatientQueueEstimate | null>(null);
  const [queueEstimateLoading, setQueueEstimateLoading] = useState(true);
  const [queueEstimateError, setQueueEstimateError] = useState(false);
  const [queueEstimateAttempt, setQueueEstimateAttempt] = useState(0);
  const step = location.pathname.split('/').pop() || 'language';
  const t = copy[language];
  const queueSessionId = record?.session.id;

  useEffect(() => {
    if (!resumeId) return;
    let active = true;
    api
      .session(resumeId)
      .then((result) => {
        if (!active) return;
        setRecord(result);
        setLanguage(result.session.language);
        setAgreed(Boolean(result.consent?.share_with_doctor));
        setVoiceAgreed(Boolean(result.consent?.voice_processing));
        setDocAgreed(Boolean(result.consent?.document_processing));
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 404) {
          sessionStorage.removeItem(sessionKey);
          pendingId.current = null;
          setResumeId(null);
        } else {
          setError(err);
        }
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt, resumeId]);

  useEffect(() => {
    if (step !== 'complete' || !queueSessionId) return;
    let active = true;
    api
      .queueEstimate(queueSessionId)
      .then((estimate) => {
        if (!active) return;
        setQueueEstimate(estimate);
      })
      .catch(() => {
        if (!active) return;
        setQueueEstimate(null);
        setQueueEstimateError(true);
      })
      .finally(() => {
        if (active) setQueueEstimateLoading(false);
      });
    return () => {
      active = false;
    };
  }, [queueEstimateAttempt, queueSessionId, step]);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState('');

  useEffect(() => {
    const syncFullscreenState = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  async function toggleFullscreen() {
    if (typeof document === 'undefined') return;
    setFullscreenError('');
    try {
      if (!document.fullscreenElement) {
        if (!document.documentElement.requestFullscreen) {
          setFullscreenError('Fullscreen is not supported by this browser.');
          return;
        }
        await document.documentElement.requestFullscreen();
      } else {
        if (!document.exitFullscreen) {
          setFullscreenError('Fullscreen cannot be exited from this browser.');
          return;
        }
        await document.exitFullscreen();
      }
      setIsFullscreen(Boolean(document.fullscreenElement));
    } catch {
      setFullscreenError('Fullscreen could not be changed. Try the browser controls instead.');
    }
  }

  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  function clear() {
    sessionStorage.removeItem(sessionKey);
    setResumeId(null);
    pendingId.current = null;
    setRecord(null);
    setQueueEstimate(null);
    setQueueEstimateLoading(false);
    setQueueEstimateError(false);
    setQueueEstimateAttempt(0);
    setName('');
    setToken('');
    setAbha('');
    setAbhaVerified(false);
    setAbhaChecking(false);
    setAbhaMessage(null);
    setAgreed(false);
    setVoiceAgreed(false);
    setDocAgreed(false);
    setLanguage('en');
    setError(null);
    navigate('/kiosk/language', { replace: true });
  }
  function identify(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !token.trim()) return;
    void action(async () => {
      const id = pendingId.current || crypto.randomUUID();
      pendingId.current = id;
      sessionStorage.setItem(sessionKey, id);
      await api.create({
        id,
        patient: { name: name.trim(), demo_abha_id: abha.trim() || null },
        hospital_token: token.trim(),
        language,
      });
      const result = await api.session(id);
      setRecord(result);
      navigate('/kiosk/hospital');
    });
  }
  async function completeInterview() {
    if (!record) return;
    const session = await api.complete(record.session.id);
    setRecord((current) => (current ? { ...current, session } : current));
    sessionStorage.removeItem(sessionKey);
    setResumeId(null);
    setQueueEstimateLoading(true);
    setQueueEstimateError(false);
    navigate('/kiosk/complete', { replace: true });
  }

  if (loading)
    return (
      <div className="card" role="status">
        {t.loading}
      </div>
    );
  if (error && resumeId && !record)
    return (
      <div className="card">
        <p role="alert" className="error">
          {errorText(error, language)}
        </p>
        <button
          onClick={() => {
            setLoading(true);
            setAttempt(attempt + 1);
          }}
        >
          {t.retry}
        </button>
        <button className="secondary" onClick={clear}>
          {t.reset}
        </button>
      </div>
    );
  if (!record && !['language', 'identify'].includes(step))
    return <Navigate to="/kiosk/language" replace />;
  if (record?.session.status !== 'intake' && record && step !== 'complete')
    return <Navigate to="/kiosk/complete" replace />;
  if (record?.session.status === 'intake') {
    if (!record.session.hospital_id && step !== 'hospital')
      return <Navigate to="/kiosk/hospital" replace />;
    if (
      record.session.hospital_id &&
      !record.consent?.share_with_doctor &&
      step !== 'consent'
    )
      return <Navigate to="/kiosk/consent" replace />;
    if (record.consent?.share_with_doctor && !['consent', 'interview'].includes(step))
      return <Navigate to="/kiosk/interview" replace />;
  }

  return (
    <div lang={language} className="kiosk">
      <div className="flex items-center justify-end pb-3 mb-2 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="kiosk-fullscreen-btn"
            onClick={() => void toggleFullscreen()}
            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 px-2.5 py-1 rounded shadow-sm transition-colors flex items-center gap-1"
            title="Toggle Fullscreen"
          >
            <span>{isFullscreen ? '⤦ Exit Fullscreen' : '⛶ Fullscreen'}</span>
          </button>
        </div>
      </div>
      {fullscreenError && (
        <p className="error" role="alert">
          {fullscreenError}
        </p>
      )}
      <div className="stepper" aria-label={t.kiosk}>
        {['language', 'identify', 'hospital', 'consent', 'interview', 'complete'].map((s, i) => (
          <span key={s} aria-current={s === step ? 'step' : undefined}>
            <b>{i + 1}</b>
            {s === 'hospital'
              ? 'Hospital'
              : t[s as 'language' | 'identify' | 'consent' | 'interview' | 'complete']}
          </span>
        ))}
      </div>
      <section className="card">
        {Boolean(error) && (
          <p className="error" role="alert">
            {errorText(error, language)}
          </p>
        )}
        {step === 'language' && (
          <>
            <p className="eyebrow">{t.welcomeText}</p>
            <h1>{t.welcome}</h1>
            <p>{t.choose}</p>
            <div className="language-grid">
              {languages.map((lang) => (
                <button
                  className="language-card"
                  key={lang.id}
                  onClick={() => {
                    setLanguage(lang.id);
                    navigate('/kiosk/identify');
                  }}
                >
                  <strong>{lang.native}</strong>
                  <span>{lang.label}</span>
                  <span aria-hidden="true">→</span>
                </button>
              ))}
            </div>
          </>
        )}
        {step === 'identify' && (
          <form onSubmit={identify}>
            <p className="eyebrow">{t.identify}</p>
            <h1>{t.identify}</h1>
            <p className="muted">{t.identityNote}</p>
            <label htmlFor="name">{t.name}</label>
            <input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
              autoComplete="off"
              disabled={busy}
            />
            <label htmlFor="token">{t.token}</label>
            <input
              id="token"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              maxLength={80}
              required
              autoComplete="off"
              disabled={busy}
            />
            <label htmlFor="abha">{t.abha}</label>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                id="abha"
                value={abha}
                onChange={(e) => {
                  setAbha(e.target.value);
                  setAbhaVerified(false);
                  setAbhaMessage(null);
                }}
                maxLength={80}
                autoComplete="off"
                disabled={busy}
                placeholder="e.g. patient@abdm or 91-1234-5678-9012"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="secondary"
                data-testid="kiosk-verify-abha-btn"
                disabled={busy || !abha.trim() || abhaChecking}
                onClick={async () => {
                  if (!abha.trim()) return;
                  setAbhaChecking(true);
                  setAbhaMessage(null);
                  try {
                    const res = await api.verifyAbha(abha.trim());
                    if (res.success && res.profile) {
                      setAbhaVerified(true);
                      setAbhaMessage(`✓ ABHA Verified (Sandbox): ${res.profile.name}`);
                    } else {
                      setAbhaVerified(false);
                      setAbhaMessage(`⚠️ ${res.message}`);
                    }
                  } catch (err: unknown) {
                    setAbhaVerified(false);
                    setAbhaMessage(
                      `Error: ${err instanceof Error ? err.message : 'Verification failed'}`,
                    );
                  } finally {
                    setAbhaChecking(false);
                  }
                }}
                style={{ whiteSpace: 'nowrap', padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}
              >
                {abhaChecking ? 'Verifying...' : 'Verify'}
              </button>
            </div>
            {abhaMessage && (
              <p
                data-testid="kiosk-abha-message"
                style={{
                  fontSize: '0.8rem',
                  marginTop: '4px',
                  color: abhaVerified ? '#166534' : '#b91c1c',
                }}
              >
                {abhaMessage}
              </p>
            )}
            <div className="actions">
              <button
                type="button"
                className="secondary"
                onClick={() => navigate('/kiosk/language')}
                disabled={busy}
              >
                {t.back}
              </button>
              <button disabled={busy || !name.trim() || !token.trim()}>
                {busy ? t.saving : t.continue}
              </button>
            </div>
          </form>
        )}
        {step === 'hospital' && record && (
          <HospitalSelection
            hospitals={hospitals}
            load={() => api.hospitals().then((result) => setHospitals(result.items))}
            busy={busy}
            onSelect={(hospitalId) =>
              void action(async () => {
                const session = await api.selectHospital(record.session.id, hospitalId);
                setRecord({ ...record, session });
                navigate('/kiosk/consent');
              })
            }
          />
        )}
        {step === 'consent' && record && (
          <>
            <p className="eyebrow">{record.session.hospital_token}</p>
            <h1>{t.consent}</h1>
            <p>{t.consentNote}</p>
            <label className="check">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                disabled={busy}
              />
              {t.agreement}
            </label>
            <label className="check" style={{ marginTop: '0.75rem' }}>
              <input
                type="checkbox"
                checked={voiceAgreed}
                onChange={(e) => setVoiceAgreed(e.target.checked)}
                disabled={busy}
              />
              {speechCopy[language].voiceConsentLabel}
            </label>
            <p
              className="muted"
              style={{ fontSize: '0.85rem', margin: '0.25rem 0 0.5rem 1.75rem' }}
            >
              {speechCopy[language].voiceConsentNote}
            </p>
            <label className="check" style={{ marginTop: '0.75rem' }}>
              <input
                type="checkbox"
                checked={docAgreed}
                onChange={(e) => setDocAgreed(e.target.checked)}
                disabled={busy}
                data-testid="consent-document-checkbox"
              />
              {t.docConsentAgreement}
            </label>
            <p className="muted" style={{ fontSize: '0.85rem', margin: '0.25rem 0 1rem 1.75rem' }}>
              {t.docConsentNote}
            </p>
            {!agreed && <p className="muted">{t.noConsent}</p>}
            <div className="actions">
              <button className="secondary" onClick={clear} disabled={busy}>
                {t.reset}
              </button>
              <button
                disabled={busy || !agreed}
                onClick={() =>
                  void action(async () => {
                    const consent = await api.consent(
                      record.session.id,
                      agreed,
                      voiceAgreed,
                      docAgreed,
                    );
                    setRecord({ ...record, consent });
                    navigate('/kiosk/interview');
                  })
                }
              >
                {busy ? t.saving : t.start}
              </button>
            </div>
          </>
        )}
        {step === 'interview' && record && (
          <Interview
            sessionId={record.session.id}
            language={language}
            voiceConsent={Boolean(record.consent?.voice_processing)}
            documentConsent={Boolean(record.consent?.document_processing)}
            selectedDoctorId={record.session.selected_doctor_id}
            onDoctorSelected={(doctorId) =>
              setRecord({
                ...record,
                session: { ...record.session, selected_doctor_id: doctorId },
              })
            }
            onComplete={completeInterview}
            onBusyChange={setBusy}
            onManageConsent={() => navigate('/kiosk/consent')}
          />
        )}
        {step === 'complete' && record && (
          <div className="completion">
            <span className="completion-icon" aria-hidden="true">
              ✓
            </span>
            <p className="eyebrow">{t.saved}</p>
            <h1>{t.complete}</h1>
            <p>{t.doneText}</p>
            <div className="queue-estimate" role="status" aria-live="polite">
              {queueEstimateLoading && <p>{t.queueEstimateLoading}</p>}
              {queueEstimateError && !queueEstimateLoading && (
                <div>
                  <p>{t.queueEstimateUnavailable}</p>
                  <button
                    type="button"
                    className="secondary queue-estimate-retry"
                    onClick={() => {
                      setQueueEstimateLoading(true);
                      setQueueEstimateError(false);
                      setQueueEstimateAttempt((value) => value + 1);
                    }}
                  >
                    {t.retry}
                  </button>
                </div>
              )}
              {queueEstimate && !queueEstimateLoading && (
                <>
                  <p>
                    {t.queuePriority}: <strong>{queueEstimate.position}</strong>
                    {' · '}
                    <strong>{queueEstimate.doctor_name}</strong>
                  </p>
                  <p>
                    {t.approximateWait}:{' '}
                    <strong>
                      {queueEstimate.estimated_wait_minutes} {t.minutes}
                    </strong>
                  </p>
                  <p>
                    {t.expectedMeeting}:{' '}
                    <strong>
                      {new Intl.DateTimeFormat(language, {
                        hour: 'numeric',
                        minute: '2-digit',
                      }).format(new Date(queueEstimate.expected_meeting_at))}
                    </strong>
                  </p>
                </>
              )}
            </div>
            <div className="token">
              <span>{t.token}</span>
              <strong>{record.session.hospital_token}</strong>
            </div>
            <p className="muted">{t.doneNote}</p>
            <button onClick={clear}>{t.newPatient}</button>
          </div>
        )}
      </section>
      {record && step !== 'complete' && (
        <button
          className="text-button"
          disabled={busy}
          onClick={() => {
            if (window.confirm(t.cancelConfirm)) clear();
          }}
        >
          {t.cancel}
        </button>
      )}
      <p className="footer-note">{t.boundary}</p>
    </div>
  );
}
