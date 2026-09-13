import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { Language } from '../../api/client';
import type { InterviewState, Submission } from '../../api/interview';
import { copy, errorText } from '../../i18n';
import { interviewCopy } from '../../i18n/interview';
import { getTriageCopy } from '../../i18n/triage';
import DocumentUploader from './DocumentUploader';
import DoctorSelector from './DoctorSelector';
import QuestionRenderer from './QuestionRenderer';
import type { ResponseInput } from './QuestionRenderer';

export default function Interview({
  sessionId,
  language,
  voiceConsent = false,
  documentConsent = false,
  fixtureId,
  onComplete,
  onBusyChange,
  onManageConsent,
  selectedDoctorId,
  onDoctorSelected,
}: {
  sessionId: string;
  language: Language;
  voiceConsent?: boolean;
  documentConsent?: boolean;
  fixtureId?: string;
  onComplete: () => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  onManageConsent?: () => void;
  selectedDoctorId?: string | null;
  onDoctorSelected?: (doctorId: string) => void;
}) {
  const [state, setState] = useState<InterviewState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const pending = useRef<Submission | null>(null);
  const t = copy[language];
  const u = interviewCopy[language];
  const triageCopy = getTriageCopy(language);
  useEffect(() => {
    let active = true;
    api
      .interview(sessionId)
      .then((result) => {
        if (active) {
          setState(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) setError(err);
      });
    return () => {
      active = false;
    };
  }, [sessionId, attempt]);
  async function action(work: () => Promise<InterviewState | void>) {
    setBusy(true);
    onBusyChange?.(true);
    setError(null);
    try {
      const result = await work();
      if (result) setState(result);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  }
  function save(answer: ResponseInput) {
    if (!state?.question) return;
    const candidate: Submission = {
      ...answer,
      request_id: '',
      expected_revision: state.revision,
      question_id: state.question.question_id,
      language,
    };
    if (
      !pending.current ||
      JSON.stringify({ ...pending.current, request_id: '' }) !== JSON.stringify(candidate)
    )
      pending.current = { ...candidate, request_id: crypto.randomUUID() };
    const request = pending.current;
    void action(async () => {
      const result = await api.interviewAnswer(sessionId, request);
      pending.current = null;
      return result;
    });
  }
  function navigate(question_id: string) {
    if (!state) return;
    void action(() => api.interviewCursor(sessionId, question_id, state.revision));
  }
  const conflict =
    error instanceof ApiError &&
    ['INTERVIEW_CONFLICT', 'QUESTION_NOT_CURRENT'].includes(error.code);
  return (
    <div className="adaptive-interview">
      <p className="notice">{u.prototype}</p>
      {(!voiceConsent || !documentConsent) && onManageConsent && (
        <div className="notice" role="note">
          <p>
            Voice-to-text and OCR require their separate consent options. You can enable them
            without restarting this interview.
          </p>
          <button type="button" className="secondary" disabled={busy} onClick={onManageConsent}>
            Enable voice / document processing
          </button>
        </div>
      )}
      {Boolean(error) && (
        <div className="error" role="alert">
          <p>{conflict ? u.conflict : errorText(error, language)}</p>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => {
              pending.current = null;
              setState(null);
              setError(null);
              setAttempt(attempt + 1);
            }}
          >
            {u.reload}
          </button>
        </div>
      )}
      {!state && !error && <p role="status">{t.loading}</p>}
      {state?.selection_required && (
        <>
          <h1>{u.select}</h1>
          {['standard', 'other', 'ayush_demo'].map((namespace) => {
            const flows = state.flows.filter((f) => f.namespace === namespace);
            if (!flows.length) return null;
            return (
              <section key={namespace} className="flow-group">
                <h2>
                  {namespace === 'standard'
                    ? u.standard
                    : namespace === 'other'
                    ? (u.other || 'Other health concern')
                    : u.ayush}
                </h2>
                <div className="language-grid">
                  {flows.map((flow) => (
                    <button
                      className="language-card"
                      key={flow.flow_id}
                      disabled={busy}
                      onClick={() => void action(() => api.selectFlow(sessionId, flow.flow_id))}
                    >
                      {flow.label[language] || flow.label.en}
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </>
      )}
      {state?.flow_id && (
        <>
          {!selectedDoctorId && onDoctorSelected ? (
            <DoctorSelector sessionId={sessionId} onSelected={onDoctorSelected} />
          ) : (
          <>
          {state.namespace === 'ayush_demo' && <h2>{u.ayush}</h2>}
          <p className="eyebrow">{state.section?.[language]}</p>
          <p className="muted">
            {u.progress}: {state.progress.addressed} / {state.progress.applicable}
          </p>
          <progress
            aria-label={u.progress}
            max={state.progress.applicable || 1}
            value={state.progress.addressed}
          />
          {documentConsent && (
            <DocumentUploader
              sessionId={sessionId}
              language={language}
              documentConsent={documentConsent}
            />
          )}
          {state.red_flag_alert && (
            <aside
              className={`kiosk-safety-advisory ${state.red_flag_alert.priority}`}
              role="alert"
              aria-live="polite"
              data-testid="kiosk-safety-advisory"
            >
              <div className="advisory-icon" aria-hidden="true">
                ⚠️
              </div>
              <div className="advisory-content">
                <strong>{triageCopy.patientAlertTitle}</strong>
                <p>{triageCopy.patientAlertMessage}</p>
                <p className="advisory-subtext">{triageCopy.patientAlertStaffNotified}</p>
              </div>
            </aside>
          )}
          {state.question ? (
            <QuestionRenderer
              key={`${state.question.question_id}:${state.revision}`}
              sessionId={sessionId}
              voiceConsent={voiceConsent}
              fixtureId={fixtureId}
              question={state.question}
              initial={state.current_answer}
              ragSuggestion={
                state.question.origin === 'rag' ||
                state.question.question_id.startsWith('rag_followup.')
                  ? state.rag_suggestions?.find(
                      (s) =>
                        s.candidate_id &&
                        state.question?.question_id === `rag_followup.${s.candidate_id}`,
                    ) || state.rag_suggestions?.[0]
                  : undefined
              }
              language={language}
              busy={busy}
              blocked={conflict}
              onSave={save}
            />
          ) : (
            state.is_complete && (
              <>
                <h1>{u.review}</h1>
                <p>{u.reviewNote}</p>
                <div className="answer-review">
                  {state.active_answers.map((a) => (
                    <div className="saved-answer" key={a.question_id}>
                      <strong>{a.label[language]}</strong>
                      <p lang={a.language}>{a.raw_value}</p>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => navigate(a.question_id)}
                        aria-label={`${u.edit}: ${a.label[language]}`}
                      >
                        {u.edit}
                      </button>
                    </div>
                  ))}
                </div>
                <button disabled={busy} onClick={() => void action(onComplete)}>
                  {busy ? t.saving : u.finish}
                </button>
              </>
            )
          )}
          {state.previous_question_id && (
            <button
              className="secondary back-answer"
              disabled={busy || conflict}
              onClick={() => navigate(state.previous_question_id!)}
            >
              {t.back}
            </button>
          )}
          </>
          )}
        </>
      )}
    </div>
  );
}
