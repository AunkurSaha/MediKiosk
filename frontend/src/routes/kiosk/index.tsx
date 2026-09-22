import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import type {
  Detail,
  Hospital,
  JourneyMode,
  Language,
  PatientQueueEstimate,
} from '../../api/client';
import Interview from '../../components/kiosk/Interview';
import RapidRouting from '../../components/kiosk/RapidRouting';
import CareLocation from '../../components/kiosk/CareLocation';
import DoctorRecommendations from '../../components/kiosk/DoctorRecommendations';
import PreArrivalPacket from '../../components/kiosk/PreArrivalPacket';
import CompletionReadiness from '../../components/kiosk/CompletionReadiness';
import { copy, errorText, languages } from '../../i18n';
import { speechCopy } from '../../i18n/speech';

const sessionKey = 'medikiosk.session';
const journeyModeKey = 'medikiosk.journeyMode';
const onSiteHospitalKey = 'medikiosk.onSiteHospital';

const progressStages = [
  { key: 'language', label: 'Language', routes: ['language'] },
  { key: 'journey', label: 'Visit type', routes: ['journey', 'on-site-facility'] },
  { key: 'details', label: 'Details', routes: ['identify', 'consent'] },
  { key: 'safety', label: 'Safety', routes: ['rapid-routing', 'emergency'] },
  { key: 'care', label: 'Care', routes: ['location', 'doctor'] },
  { key: 'history', label: 'History', routes: ['interview'] },
  { key: 'review', label: 'Review', routes: [] },
  { key: 'ready', label: 'Ready', routes: ['complete'] },
] as const;

export function HospitalSelection({
  hospitals,
  load,
  busy,
  onSelect,
  title = 'Which hospital are you visiting today?',
  subtitle = 'This selection applies to this visit only.',
}: {
  hospitals: Hospital[] | null;
  load: () => Promise<void>;
  busy: boolean;
  onSelect: (hospitalId: string) => void;
  title?: string;
  subtitle?: string;
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
      <h1>{title}</h1>
      <p className="muted">{subtitle}</p>
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
  const [journeyMode, setJourneyMode] = useState<JourneyMode | null>(
    () => sessionStorage.getItem(journeyModeKey) as JourneyMode | null,
  );
  const [onSiteHospitalId, setOnSiteHospitalId] = useState(
    () => sessionStorage.getItem(onSiteHospitalKey) || '',
  );
  const [record, setRecord] = useState<Detail | null>(null);
  const [queue, setQueue] = useState<PatientQueueEstimate | null>(null);
  const [queueError, setQueueError] = useState(false);
  const [loading, setLoading] = useState(Boolean(resumeId));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const demoPatient = sessionStorage.getItem('medikiosk.demoPatient') === 'true';
  const [name, setName] = useState(demoPatient ? 'Patient' : '');
  const [gender, setGender] = useState(demoPatient ? 'female' : '');
  const [age, setAge] = useState(demoPatient ? '42' : '');
  const [height, setHeight] = useState(demoPatient ? '162' : '');
  const [weight, setWeight] = useState(demoPatient ? '64' : '');
  // This is an internal intake reference.  The visit/queue token is issued after
  // routing and doctor selection, so a patient planning a visit never has to know
  // an institution-specific token up front.
  const [token] = useState(`INTAKE-${crypto.randomUUID().slice(0, 8).toUpperCase()}`);
  const [abha, setAbha] = useState('');
  const [abhaVerified, setAbhaVerified] = useState(false);
  const [abhaChecking, setAbhaChecking] = useState(false);
  const [abhaMessage, setAbhaMessage] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [voiceAgreed, setVoiceAgreed] = useState(false);
  const [docAgreed, setDocAgreed] = useState(false);
  const [hospitals, setHospitals] = useState<Hospital[] | null>(null);
  const step = location.pathname.split('/').pop() || 'language';
  const t = copy[language];
  const currentProgressIndex = Math.max(
    0,
    progressStages.findIndex((stage) => stage.routes.includes(step as never)),
  );

  useEffect(() => {
    if (step !== 'complete' || !record) return;
    let active = true;
    const refresh = () => {
      api
        .queueEstimate(record.session.id)
        .then((result) => {
          if (active) {
            setQueue(result);
            setQueueError(false);
          }
        })
        .catch(() => {
          if (active) setQueueError(true);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 20000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [step, record]);

  useEffect(() => {
    if (!resumeId) return;
    let active = true;
    api
      .session(resumeId)
      .then((result) => {
        if (!active) return;
        setRecord(result);
        setLanguage(result.session.language);
        const persistedJourneyMode = result.session.journey_mode || 'PRE_ARRIVAL';
        setJourneyMode(persistedJourneyMode);
        sessionStorage.setItem(journeyModeKey, persistedJourneyMode);
        if (result.session.journey_mode === 'ON_SITE' && result.session.hospital_id) {
          setOnSiteHospitalId(result.session.hospital_id);
          sessionStorage.setItem(onSiteHospitalKey, result.session.hospital_id);
        }
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
    if (journeyMode !== 'ON_SITE' || hospitals !== null) return;
    void api
      .hospitals()
      .then((result) => setHospitals(result.items))
      .catch(() => setHospitals([]));
  }, [journeyMode, hospitals]);

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
    sessionStorage.removeItem('medikiosk.demoPatient');
    sessionStorage.removeItem(journeyModeKey);
    sessionStorage.removeItem(onSiteHospitalKey);
    setResumeId(null);
    pendingId.current = null;
    setRecord(null);
    setQueue(null);
    setName('');
    setGender('');
    setAge('');
    setHeight('');
    setWeight('');
    setAbha('');
    setAbhaVerified(false);
    setAbhaChecking(false);
    setAbhaMessage(null);
    setAgreed(false);
    setVoiceAgreed(false);
    setDocAgreed(false);
    setLanguage('en');
    setJourneyMode(null);
    setOnSiteHospitalId('');
    setError(null);
    navigate('/kiosk/language', { replace: true });
  }
  function identify(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || !gender || !age || !height || !weight) return;
    void action(async () => {
      const id = pendingId.current || crypto.randomUUID();
      pendingId.current = id;
      sessionStorage.setItem(sessionKey, id);
      await api.create({
        id,
        patient: {
          name: name.trim(),
          gender: gender as 'female' | 'male' | 'non_binary' | 'other' | 'prefer_not_to_say',
          age_years: Number(age),
          height_cm: Number(height),
          weight_kg: Number(weight),
          demo_abha_id: abha.trim() || null,
        },
        hospital_token: token.trim(),
        language,
        journey_mode: journeyMode || 'PRE_ARRIVAL',
        hospital_id: journeyMode === 'ON_SITE' ? onSiteHospitalId : undefined,
      });
      const result = await api.session(id);
      setRecord(result);
      navigate('/kiosk/consent');
    });
  }
  function chooseJourneyMode(mode: JourneyMode) {
    void action(async () => {
      sessionStorage.setItem(journeyModeKey, mode);
      sessionStorage.removeItem(onSiteHospitalKey);
      setJourneyMode(mode);
      setOnSiteHospitalId('');
      if (record) {
        const session = await api.updateJourneyMode(record.session.id, mode);
        setRecord({ ...record, session });
      }
      navigate(mode === 'ON_SITE' ? '/kiosk/on-site-facility' : '/kiosk/identify');
    });
  }
  async function completeInterview() {
    if (!record) return;
    const session = await api.complete(record.session.id);
    setRecord({ ...record, session });
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
  if (!record && !['language', 'journey', 'on-site-facility', 'identify'].includes(step))
    return <Navigate to="/kiosk/language" replace />;
  if (record?.session.status !== 'intake' && record && step !== 'complete')
    return <Navigate to="/kiosk/complete" replace />;
  if (record?.session.status === 'intake') {
    if (
      !record.consent?.share_with_doctor &&
      !['journey', 'on-site-facility', 'consent'].includes(step)
    )
      return <Navigate to="/kiosk/consent" replace />;
    if (
      record.consent?.share_with_doctor &&
      !['consent', 'rapid-routing', 'location', 'doctor', 'emergency', 'interview'].includes(step)
    )
      return <Navigate to="/kiosk/rapid-routing" replace />;
  }

  return (
    <div lang={language} className={`kiosk${step === 'complete' ? ' kiosk-complete' : ''}`}>
      <div className="kiosk-utility-bar">
        <div>
          <strong>Patient Intake</strong>
          <span>Private pre-consultation history</span>
        </div>
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
        {progressStages.map((stage, index) => (
          <span
            key={stage.key}
            className={index < currentProgressIndex ? 'complete' : ''}
            aria-current={index === currentProgressIndex ? 'step' : undefined}
          >
            <b>{index < currentProgressIndex ? '✓' : index + 1}</b>
            {stage.label}
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
                    navigate('/kiosk/journey');
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
        {step === 'journey' && (
          <>
            <p className="eyebrow">Visit setup</p>
            <h1>How are you using MediKiosk today?</h1>
            <div className="language-grid" data-testid="journey-mode-options">
              <button
                className="language-card"
                disabled={busy}
                onClick={() => chooseJourneyMode('PRE_ARRIVAL')}
              >
                <strong>Planning my visit</strong>
                <span>At home or away from the hospital</span>
                <span aria-hidden="true">→</span>
              </button>
              <button
                className="language-card"
                disabled={busy}
                onClick={() => chooseJourneyMode('ON_SITE')}
              >
                <strong>Already at a hospital</strong>
                <span>Using MediKiosk after arriving</span>
                <span aria-hidden="true">→</span>
              </button>
            </div>
          </>
        )}
        {step === 'on-site-facility' && (
          <HospitalSelection
            hospitals={hospitals}
            load={() => api.hospitals().then((result) => setHospitals(result.items))}
            busy={busy}
            title="Which hospital are you currently at?"
            subtitle="Choose where you have already arrived. Nearby-hospital search will be skipped."
            onSelect={(hospitalId) => {
              sessionStorage.setItem(onSiteHospitalKey, hospitalId);
              setOnSiteHospitalId(hospitalId);
              if (record) {
                void action(async () => {
                  const session = await api.selectHospital(record.session.id, hospitalId);
                  setRecord({ ...record, session });
                  navigate('/kiosk/consent');
                });
              } else navigate('/kiosk/identify');
            }}
          />
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
            <label htmlFor="gender">{t.gender}</label>
            <select
              id="gender"
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              required
              disabled={busy}
            >
              <option value="">{t.selectGender}</option>
              <option value="female">{t.female}</option>
              <option value="male">{t.male}</option>
              <option value="non_binary">{t.nonBinary}</option>
              <option value="other">{t.otherGender}</option>
              <option value="prefer_not_to_say">{t.preferNotToSay}</option>
            </select>
            <label htmlFor="age">{t.age}</label>
            <input
              id="age"
              type="number"
              min="0"
              max="120"
              step="1"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              required
              disabled={busy}
            />
            <label htmlFor="height">{t.height}</label>
            <input
              id="height"
              type="number"
              min="30"
              max="250"
              step="0.1"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              required
              disabled={busy}
            />
            <label htmlFor="weight">{t.weight}</label>
            <input
              id="weight"
              type="number"
              min="1"
              max="500"
              step="0.1"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              required
              disabled={busy}
            />
            <p className="notice" role="note">
              <strong>No hospital token is needed.</strong> We will issue your visit token after a
              facility and clinician are matched. Your intake reference stays in the background.
            </p>
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
                      setAbhaMessage(`✓ ABHA identity verified: ${res.profile.name}`);
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
                onClick={() => navigate('/kiosk/journey')}
                disabled={busy}
              >
                {t.back}
              </button>
              <button disabled={busy || !name.trim() || !gender || !age || !height || !weight}>
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
            <p className="eyebrow">Privacy and consent</p>
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
                    navigate('/kiosk/rapid-routing');
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
            onManageConsent={() => navigate('/kiosk/consent')}
          />
        )}
        {step === 'rapid-routing' && record && (
          <RapidRouting
            sessionId={record.session.id}
            language={language}
            voiceConsent={Boolean(record.consent?.voice_processing)}
            journeyMode={record.session.journey_mode || 'PRE_ARRIVAL'}
            onContinue={(emergency) =>
              navigate(
                record.session.journey_mode === 'ON_SITE'
                  ? emergency
                    ? '/kiosk/emergency'
                    : '/kiosk/doctor'
                  : '/kiosk/location',
              )
            }
          />
        )}
        {step === 'location' && record && (
          <CareLocation
            sessionId={record.session.id}
            onSelected={(emergency) => navigate(emergency ? '/kiosk/emergency' : '/kiosk/doctor')}
          />
        )}
        {step === 'doctor' && record && (
          <>
            {record.session.journey_mode === 'ON_SITE' && (
              <div className="notice" data-testid="on-site-facility-context">
                <strong>Current facility</strong>
                <p>
                  {hospitals?.find((item) => item.id === record.session.hospital_id)?.name ||
                    'Selected hospital'}
                </p>
                <span>Already here — hospital search skipped</span>
              </div>
            )}
            <DoctorRecommendations
              sessionId={record.session.id}
              onSelected={(doctorId) => {
                setRecord({
                  ...record,
                  session: { ...record.session, selected_doctor_id: doctorId },
                });
                navigate('/kiosk/interview');
              }}
              onChooseFacility={() =>
                navigate(
                  record.session.journey_mode === 'ON_SITE'
                    ? '/kiosk/on-site-facility'
                    : '/kiosk/location',
                )
              }
            />
          </>
        )}
        {step === 'emergency' && record && (
          <div className="kiosk-safety-advisory emergency" role="alert">
            <h1>Potential emergency symptoms detected</h1>
            <p>
              Immediate clinical assessment recommended.{' '}
              {record.session.journey_mode === 'ON_SITE'
                ? 'Please seek immediate assistance from the clinical or triage team at your current hospital.'
                : 'Please speak to staff at the selected emergency-capable facility now.'}
            </p>
            {record.session.journey_mode === 'ON_SITE' && (
              <p data-testid="on-site-emergency-facility">
                You are already at:{' '}
                <strong>
                  {hospitals?.find((item) => item.id === record.session.hospital_id)?.name ||
                    'your selected hospital'}
                </strong>
              </p>
            )}
            <p>Routine doctor matching and the normal queue pathway are paused.</p>
            <div className="emergency-explanation">
              <h2>How was this detected?</h2>
              <p>
                Your symptom responses matched a predefined deterministic clinical safety rule. This
                decision was not generated by an AI diagnosis model.
              </p>
            </div>
          </div>
        )}
        {step === 'complete' && record && (
          <div className="completion">
            <p className="eyebrow">✓ {t.saved}</p>
            <h1>
              {record.session.journey_mode === 'ON_SITE'
                ? 'Your hospital intake is ready'
                : 'Your pre-consultation intake is ready'}
            </h1>
            <p>
              Your information has been organized for the selected clinical team before
              consultation.
            </p>
            <CompletionReadiness record={record} />
            <div className="completion-grid">
              <div className="card completion-visit" aria-label="Visit queue reservation">
                <h2>Your visit</h2>
                {queue && (
                  <>
                    <div className="completion-visit-grid">
                      <div>
                        <span>Selected Facility</span>
                        <strong>{queue.hospital_name}</strong>
                      </div>
                      <div>
                        <span>Doctor</span>
                        <strong>{queue.doctor_name}</strong>
                      </div>
                      <div className="completion-visit-highlight">
                        <span>Visit Token</span>
                        <strong>{queue.visit_token ?? 'Pending'}</strong>
                      </div>
                      <div className="completion-visit-highlight">
                        <span>Approx. Waiting Time</span>
                        <strong>{queue.estimated_wait_minutes} minutes</strong>
                      </div>
                      <div>
                        <span>Queue Status</span>
                        <strong>{queue.status.replaceAll('_', ' ')}</strong>
                      </div>
                    </div>
                    <p className="muted">
                      Waiting time is an estimate and may change during clinical care.
                    </p>
                  </>
                )}
                {queueError && (
                  <p role="alert">Queue status could not be loaded. Please retry or ask staff.</p>
                )}
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    record &&
                    api
                      .queueEstimate(record.session.id)
                      .then(setQueue)
                      .catch(() => setQueueError(true))
                  }
                >
                  Refresh queue status
                </button>
                <p className="completion-reference">
                  Intake reference: {record.session.hospital_token}
                </p>
              </div>
              <PreArrivalPacket sessionId={record.session.id} />
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
