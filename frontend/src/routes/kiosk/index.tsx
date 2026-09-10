import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import type { Detail, Language } from '../../api/client';
import Interview from '../../components/kiosk/Interview';
import { copy, errorText, languages } from '../../i18n';
import { speechCopy } from '../../i18n/speech';

const sessionKey = 'medikiosk.session';
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
  const [agreed, setAgreed] = useState(false);
  const [voiceAgreed, setVoiceAgreed] = useState(false);
  const [docAgreed, setDocAgreed] = useState(false);
  const step = location.pathname.split('/').pop() || 'language';
  const t = copy[language];

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
    setName('');
    setToken('');
    setAbha('');
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
      navigate('/kiosk/consent');
    });
  }
  async function completeInterview() {
    if (!record) return;
    const session = await api.complete(record.session.id);
    setRecord((current) => (current ? { ...current, session } : current));
    sessionStorage.removeItem(sessionKey);
    setResumeId(null);
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
    if (!record.consent?.share_with_doctor && step !== 'consent')
      return <Navigate to="/kiosk/consent" replace />;
    if (record.consent?.share_with_doctor && !['consent', 'interview'].includes(step))
      return <Navigate to="/kiosk/interview" replace />;
  }

  return (
    <div lang={language} className="kiosk">
      <div className="stepper" aria-label={t.kiosk}>
        {['language', 'identify', 'consent', 'interview', 'complete'].map((s, i) => (
          <span key={s} aria-current={s === step ? 'step' : undefined}>
            <b>{i + 1}</b>
            {t[s as 'language' | 'identify' | 'consent' | 'interview' | 'complete']}
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
            <input
              id="abha"
              value={abha}
              onChange={(e) => setAbha(e.target.value)}
              maxLength={80}
              autoComplete="off"
              disabled={busy}
            />
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
            onComplete={completeInterview}
            onBusyChange={setBusy}
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
