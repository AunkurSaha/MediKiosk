import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { ComplaintCategory, JourneyMode, Language, RapidRoutingState } from '../../api/client';
import VoiceRecorder from './VoiceRecorder';

const labels: Record<Language, Record<ComplaintCategory, string>> = {
  en: {
    CHEST_DISCOMFORT: 'Chest discomfort',
    FEVER: 'Fever',
    HEADACHE: 'Headache',
    BREATHING_DIFFICULTY: 'Breathing difficulty',
    ABDOMINAL_PAIN: 'Abdominal pain',
    COUGH: 'Cough',
    SKIN_PROBLEM: 'Skin problem',
    INJURY: 'Injury',
    JOINT_PAIN: 'Joint pain',
    OTHER: 'Other',
  },
  bn: {
    CHEST_DISCOMFORT: 'বুকে অস্বস্তি',
    FEVER: 'জ্বর',
    HEADACHE: 'মাথাব্যথা',
    BREATHING_DIFFICULTY: 'শ্বাসকষ্ট',
    ABDOMINAL_PAIN: 'পেটব্যথা',
    COUGH: 'কাশি',
    SKIN_PROBLEM: 'ত্বকের সমস্যা',
    INJURY: 'আঘাত',
    JOINT_PAIN: 'জয়েন্টে ব্যথা',
    OTHER: 'অন্যান্য',
  },
  hi: {
    CHEST_DISCOMFORT: 'सीने में तकलीफ़',
    FEVER: 'बुखार',
    HEADACHE: 'सिरदर्द',
    BREATHING_DIFFICULTY: 'सांस लेने में तकलीफ़',
    ABDOMINAL_PAIN: 'पेट दर्द',
    COUGH: 'खांसी',
    SKIN_PROBLEM: 'त्वचा की समस्या',
    INJURY: 'चोट',
    JOINT_PAIN: 'जोड़ों का दर्द',
    OTHER: 'अन्य',
  },
};
const categories = Object.keys(labels.en) as ComplaintCategory[];
const complaintIcons: Record<ComplaintCategory, string> = {
  CHEST_DISCOMFORT: '♥',
  FEVER: '°C',
  HEADACHE: '◉',
  BREATHING_DIFFICULTY: '≈',
  ABDOMINAL_PAIN: '◎',
  COUGH: '⌁',
  SKIN_PROBLEM: '◇',
  INJURY: '+',
  JOINT_PAIN: '○',
  OTHER: '…',
};

export default function RapidRouting({
  sessionId,
  language,
  voiceConsent,
  journeyMode = 'PRE_ARRIVAL',
  onContinue,
}: {
  sessionId: string;
  language: Language;
  voiceConsent: boolean;
  journeyMode?: JourneyMode;
  onContinue: (emergency: boolean) => void;
}) {
  const [state, setState] = useState<RapidRoutingState | null>(null);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api
      .rapidRouting(sessionId)
      .then(setState)
      .catch(() => setError('Routing information could not be loaded.'));
  }, [sessionId]);
  async function run(work: () => Promise<RapidRoutingState>) {
    setBusy(true);
    setError('');
    try {
      setState(await work());
    } catch {
      setError('Please reload and try again.');
    } finally {
      setBusy(false);
    }
  }
  if (!state) return <p role="status">Loading quick safety check…</p>;
  if (state.phase === 'chief_complaint')
    return (
      <>
        <p className="eyebrow">Chief complaint</p>
        <h1>What brings you here today?</h1>
        <p className="muted">Choose the concern that best matches what you need help with.</p>
        <div className="complaint-grid" data-testid="complaint-cards">
          {categories.map((c) => (
            <button
              key={c}
              className={`complaint-card complaint-${c.toLowerCase().replaceAll('_', '-')}`}
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const mapped = await api.mapComplaint(sessionId, {
                    original_text: labels[language][c],
                    language,
                    source: 'card',
                  });
                  return api.confirmComplaint(sessionId, c, mapped.revision);
                })
              }
            >
              <span className="complaint-icon" aria-hidden="true">
                {complaintIcons[c]}
              </span>
              <strong>{labels[language][c]}</strong>
            </button>
          ))}
        </div>
        <label htmlFor="complaint-text">Describe it in your own words</label>
        <textarea
          id="complaint-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
        />
        <button
          disabled={busy || !text.trim()}
          onClick={() =>
            void run(() =>
              api.mapComplaint(sessionId, {
                original_text: text.trim(),
                language,
                source: 'typed',
              }),
            )
          }
        >
          Understand my concern
        </button>
        {voiceConsent && (
          <VoiceRecorder
            sessionId={sessionId}
            questionId="rapid.chief_complaint"
            language={language}
            disabled={busy}
            onConfirmCandidate={(transcript, token) =>
              void run(() =>
                api.mapComplaint(sessionId, {
                  original_text: transcript,
                  language,
                  source: 'voice',
                  voice_candidate: token,
                }),
              )
            }
            onEditCandidate={setText}
          />
        )}{' '}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </>
    );
  if (state.phase === 'confirm_complaint' && state.mapping)
    return (
      <>
        <p className="eyebrow">Please confirm</p>
        <h1>We understood: {labels[language][state.mapping.candidate_category]}</h1>
        <blockquote lang={state.mapping.language}>“{state.mapping.original_text}”</blockquote>
        <div className="actions">
          <button
            className="secondary"
            onClick={() => setState({ ...state, phase: 'chief_complaint' })}
          >
            Change
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void run(() =>
                api.confirmComplaint(sessionId, state.mapping!.candidate_category, state.revision),
              )
            }
          >
            Yes, continue
          </button>
        </div>
      </>
    );
  if (state.phase === 'rapid_interview' && state.question) {
    const q = state.question;
    return (
      <>
        <p className="eyebrow">Quick safety check</p>
        <h1>{q.prompt[language] || q.prompt.en}</h1>
        {q.input_type === 'boolean' ? (
          <div className="actions">
            <button
              disabled={busy}
              onClick={() =>
                void run(() =>
                  api.rapidAnswer(sessionId, {
                    question_id: q.question_id,
                    value: true,
                    raw_value: 'Yes',
                    source: 'touch',
                    language,
                    expected_revision: state.revision,
                  }),
                )
              }
            >
              Yes
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void run(() =>
                  api.rapidAnswer(sessionId, {
                    question_id: q.question_id,
                    value: false,
                    raw_value: 'No',
                    source: 'touch',
                    language,
                    expected_revision: state.revision,
                  }),
                )
              }
            >
              No
            </button>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const value = Number(text);
              void run(() =>
                api.rapidAnswer(sessionId, {
                  question_id: q.question_id,
                  value,
                  raw_value: text,
                  source: 'typed',
                  language,
                  expected_revision: state.revision,
                }),
              );
            }}
          >
            <input
              aria-label="Answer"
              type="number"
              min={q.input_type === 'severity' ? 0 : 30}
              max={q.input_type === 'severity' ? 10 : 50}
              step={q.input_type === 'severity' ? 1 : 0.1}
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
            />
            <button disabled={busy}>Continue</button>
          </form>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </>
    );
  }
  const result = state.result!;
  const emergency = result.routing_state === 'EMERGENCY';
  return (
    <div
      className={emergency ? 'kiosk-safety-advisory emergency' : 'completion'}
      data-testid="rapid-routing-result"
    >
      <p className="eyebrow">Care routing result</p>
      <h1>
        {emergency ? 'Potential emergency symptoms detected.' : 'Quick safety check complete'}
      </h1>
      <p>
        {emergency
          ? 'Immediate clinical assessment recommended. Because your answers may indicate a time-sensitive condition, MediKiosk will not continue with the routine intake pathway.'
          : 'Based on the information provided, ' +
            result.routing_state.replaceAll('_', ' ').toLowerCase() +
            ' appears appropriate.'}
      </p>
      <p>
        <strong>Suggested department:</strong> {result.suggested_specialty.replaceAll('_', ' ')}
      </p>
      {!!result.triggered_red_flags.length && <p>Clinical safety alert recorded for triage.</p>}
      {emergency && (
        <div className="emergency-explanation">
          <h2>How was this detected?</h2>
          <p>
            Your symptom responses matched a predefined deterministic clinical safety rule. This
            decision was not generated by an AI diagnosis model.
          </p>
          <p>
            Routine doctor matching and the normal queue pathway are paused.{' '}
            {journeyMode === 'ON_SITE'
              ? 'Please seek immediate clinical or triage assistance at this hospital.'
              : 'An emergency-capable facility can be selected for immediate clinical assessment.'}
          </p>
        </div>
      )}
      <button onClick={() => onContinue(emergency)}>
        {journeyMode === 'ON_SITE'
          ? emergency
            ? 'Get immediate help at this hospital'
            : 'Continue with this hospital'
          : emergency
            ? 'Find emergency-capable facilities'
            : 'Find a suitable facility'}
      </button>
    </div>
  );
}
