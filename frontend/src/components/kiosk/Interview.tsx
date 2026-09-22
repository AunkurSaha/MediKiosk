import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { Language } from '../../api/client';
import type { InterviewState, Submission } from '../../api/interview';
import { copy, errorText } from '../../i18n';
import { interviewCopy } from '../../i18n/interview';
import { getTriageCopy } from '../../i18n/triage';
import DocumentUploader from './DocumentUploader';
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
}: {
  sessionId: string;
  language: Language;
  voiceConsent?: boolean;
  documentConsent?: boolean;
  fixtureId?: string;
  onComplete: () => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  onManageConsent?: () => void;
}) {
  const [state, setState] = useState<InterviewState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [medicationHistoryOptimized, setMedicationHistoryOptimized] = useState(false);
  const pending = useRef<Submission | null>(null);
  const t = copy[language];
  const u = interviewCopy[language];
  const triageCopy = getTriageCopy(language);
  const clinicalBoundaryNotice = {
    en: 'Questions and translations are reviewed by clinicians. No diagnosis or treatment advice is provided.',
    bn: 'প্রশ্ন ও অনুবাদ চিকিৎসকদের পর্যালোচনাধীন। এখানে রোগ নির্ণয় বা চিকিৎসার পরামর্শ দেওয়া হয় না।',
    hi: 'प्रश्नों और अनुवादों की चिकित्सकों द्वारा समीक्षा की जाती है। यहाँ निदान या उपचार की सलाह नहीं दी जाती।',
  }[language];
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
    const answeredQuestion = state.question;
    const answeredDocumentConfirmation = state.document_confirmation;
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
      if (
        answeredDocumentConfirmation?.target_field === 'medications.details' ||
        answeredQuestion.origin === 'document_confirmation'
      ) {
        let confirmedAndSkipped = false;
        if (answer.value === 'yes') {
          const medicationDomainCovered = result.covered_domains?.some((domain) =>
            domain.toLowerCase().includes('medication'),
          );
          confirmedAndSkipped =
            Boolean(medicationDomainCovered) &&
            !['medications.any', 'medications.details', 'medications'].includes(
              result.question?.field || '',
            );
        }
        setMedicationHistoryOptimized(confirmedAndSkipped);
      } else {
        setMedicationHistoryOptimized(false);
      }
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
  const reviewSections = state?.active_answers.reduce<Record<string, typeof state.active_answers>>(
    (groups, answer) => {
      const field = answer.field.toLowerCase();
      const section =
        field.includes('chief') || field.includes('concern')
          ? 'Main concern'
          : field.includes('medication')
            ? 'Medications'
            : field.includes('allerg')
              ? 'Allergies'
              : field.includes('history') || field.includes('medical') || field.includes('surgery')
                ? 'Medical history'
                : field.includes('symptom') ||
                    field.includes('pain') ||
                    field.includes('fever') ||
                    field.includes('onset') ||
                    field.includes('duration')
                  ? 'Symptoms'
                  : 'Additional information';
      groups[section] = [...(groups[section] || []), answer];
      return groups;
    },
    {},
  );
  const currentField = state?.question?.field || '';
  const medicationHistoryCovered = Boolean(
    state?.covered_domains?.some((domain) => domain.toLowerCase().includes('medication')) &&
    !state.document_confirmation &&
    !['medications.any', 'medications.details', 'medications'].includes(currentField),
  );
  return (
    <div className="adaptive-interview">
      <p className="notice">{clinicalBoundaryNotice}</p>
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
                      ? u.other || 'Other health concern'
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
              onUploadComplete={() => setAttempt((value) => value + 1)}
            />
          )}
          {state.document_confirmation && (
            <aside className="notice" role="note" data-testid="document-confirmation-notice">
              <strong>We found information in your uploaded document.</strong>
              <p>
                We’ll confirm this detail so you don’t have to repeat information unnecessarily.
              </p>
              <p className="muted">
                Source: {state.document_confirmation.document_filename || 'uploaded document'}
                {state.document_confirmation.page_number
                  ? `, page ${state.document_confirmation.page_number}`
                  : ''}
                {' · '}Needs your confirmation
              </p>
            </aside>
          )}
          {(medicationHistoryOptimized || medicationHistoryCovered) && (
            <aside
              className="history-optimized"
              role="status"
              data-testid="medication-history-optimized"
            >
              <span className="history-optimized-icon" aria-hidden="true">
                ✓
              </span>
              <div>
                <strong>History optimized</strong>
                <p>Medication confirmed by you from your prescription.</p>
                <p>Medication history is covered, so we won’t ask the same questions again.</p>
              </div>
            </aside>
          )}
          {state.continuity_reconfirmation && (
            <aside className="notice" role="note" data-testid="continuity-reconfirmation-notice">
              <strong>From your previous visit</strong>
              <p>
                We found information from your previous visit. We’ll confirm what is still current
                so you don’t have to repeat everything.
              </p>
            </aside>
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
                <div className="answer-review grouped-review">
                  {Object.entries(reviewSections || {}).map(([section, answers]) => (
                    <section className="review-section" key={section}>
                      <h2>{section}</h2>
                      {answers.map((a) => (
                        <div className="review-answer-row" key={a.question_id}>
                          <div>
                            <strong>{a.label[language]}</strong>
                            <p lang={a.language}>{a.raw_value}</p>
                          </div>
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() => navigate(a.question_id)}
                            aria-label={`${u.edit}: ${a.label[language]}`}
                          >
                            {u.edit}
                          </button>
                        </div>
                      ))}
                    </section>
                  ))}
                  {documentConsent && (
                    <section className="review-section">
                      <h2>Documents</h2>
                      <p>
                        Uploaded documents and your confirmations are included in the clinical
                        evidence.
                      </p>
                    </section>
                  )}
                </div>
                <button
                  className="finish-intake-button"
                  disabled={busy}
                  onClick={() => void action(onComplete)}
                >
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
    </div>
  );
}
