import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Language } from '../../api/client';
import type { AnswerStatus, AnswerValue, Fact, Question } from '../../api/interview';
import { copy } from '../../i18n';
import { interviewCopy } from '../../i18n/interview';

import QuestionAudioPlayer from './QuestionAudioPlayer';
import VoiceRecorder from './VoiceRecorder';

export interface ResponseInput {
  value: AnswerValue;
  status: AnswerStatus;
  raw_value: string;
  source: 'typed' | 'touch' | 'voice';
}
export default function QuestionRenderer({
  question,
  initial,
  language,
  busy,
  blocked = false,
  sessionId,
  voiceConsent = false,
  fixtureId,
  onSave,
}: {
  question: Question;
  initial: Fact | null;
  language: Language;
  busy: boolean;
  onSave: (answer: ResponseInput) => void;
  blocked?: boolean;
  sessionId?: string;
  voiceConsent?: boolean;
  fixtureId?: string;
}) {
  const t = copy[language];
  const u = interviewCopy[language];
  const [value, setValue] = useState<AnswerValue>(initial?.value ?? null);
  const [text, setText] = useState(() => {
    if (initial?.status !== 'answered') return '';
    if (typeof initial.value === 'string' || typeof initial.value === 'number')
      return String(initial.value);
    if (initial.value && typeof initial.value === 'object' && 'amount' in initial.value)
      return String(initial.value.amount);
    return '';
  });
  const [unit, setUnit] = useState(
    initial?.value && typeof initial.value === 'object' && 'unit' in initial.value
      ? initial.value.unit
      : 'days',
  );
  const [error, setError] = useState(false);
  const [answerSource, setAnswerSource] = useState<'typed' | 'voice'>('typed');
  const q = question;
  function submit(event: FormEvent) {
    event.preventDefault();
    let saved = value;
    let raw = '';
    if (q.type === 'short_text') {
      saved = text;
      raw = text;
    }
    if (['number', 'severity', 'duration'].includes(q.type)) {
      const number = Number(text);
      const c = q.constraints;
      if (
        !text.trim() ||
        !Number.isFinite(number) ||
        (c.minimum != null && number < c.minimum) ||
        (c.maximum != null && number > c.maximum) ||
        (c.integer && !Number.isInteger(number))
      ) {
        setError(true);
        return;
      }
      saved = q.type === 'duration' ? { amount: number, unit } : number;
      raw = q.type === 'duration' ? `${text} ${u[unit as 'days']}` : text;
    }
    if (q.type === 'boolean') raw = saved === true ? u.yes : u.no;
    if (q.type === 'single_choice')
      raw = q.options.find((o) => o.value === saved)?.label[language] || '';
    if (q.type === 'multiple_choice')
      raw = q.options
        .filter((o) => Array.isArray(saved) && saved.includes(o.value))
        .map((o) => o.label[language])
        .join(', ');
    if (
      saved === null ||
      (typeof saved === 'string' && !saved.trim()) ||
      (Array.isArray(saved) && !saved.length)
    ) {
      setError(true);
      return;
    }
    onSave({
      value: saved,
      raw_value: raw,
      status: 'answered',
      source:
        q.type === 'short_text'
          ? answerSource
          : ['number', 'duration', 'severity'].includes(q.type)
            ? 'typed'
            : 'touch',
    });
  }
  function special(status: AnswerStatus, raw: string) {
    onSave({ value: null, raw_value: raw, status, source: 'touch' });
  }
  return (
    <form onSubmit={submit} noValidate>
      <div className="question-header">
        <h1 id="question-title">{q.text[language]}</h1>
        {sessionId && (
          <QuestionAudioPlayer
            sessionId={sessionId}
            questionId={q.question_id}
            language={language}
            disabled={busy || blocked}
          />
        )}
      </div>
      {!q.required && <p className="muted">{u.optional}</p>}
      {initial && initial.status !== 'answered' && (
        <p className="notice">
          {t.saved}: {initial.raw_value}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {u.invalid}
        </p>
      )}
      <fieldset
        disabled={busy || blocked}
        className="question-fields"
        aria-labelledby="question-title"
      >
        {q.type === 'short_text' && (
          <>
            <label htmlFor="answer">{t.answer}</label>
            <textarea
              id="answer"
              rows={4}
              value={text}
              maxLength={q.constraints?.max_length}
              onChange={(e) => {
                setText(e.target.value);
                setAnswerSource('typed');
              }}
            />
            {voiceConsent && sessionId && (
              <VoiceRecorder
                sessionId={sessionId}
                questionId={q.question_id}
                language={language}
                disabled={busy || blocked}
                fixtureId={fixtureId}
                onConfirmCandidate={(transcript) => {
                  onSave({
                    value: transcript,
                    raw_value: transcript,
                    status: 'answered',
                    source: 'voice',
                  });
                }}
                onEditCandidate={(transcript) => {
                  setText(transcript);
                  setAnswerSource('voice');
                }}
              />
            )}
          </>
        )}
        {['number', 'severity', 'duration'].includes(q.type) && (
          <>
            <label htmlFor="answer">
              {t.answer}
              {q.constraints.unit ? ` (${q.constraints.unit})` : ''}
            </label>
            <input
              id="answer"
              type="number"
              inputMode="decimal"
              value={text}
              min={q.constraints.minimum ?? undefined}
              max={q.constraints.maximum ?? undefined}
              step={q.constraints.integer ? 1 : 'any'}
              onChange={(e) => setText(e.target.value)}
            />
            {q.type === 'duration' && (
              <>
                <label htmlFor="duration-unit">{u.unit}</label>
                <select id="duration-unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
                  {(['minutes', 'hours', 'days', 'weeks', 'months', 'years'] as const).map(
                    (key) => (
                      <option key={key} value={key}>
                        {u[key]}
                      </option>
                    ),
                  )}
                </select>
              </>
            )}
          </>
        )}
        {q.type === 'boolean' && (
          <div className="choice-grid">
            {[
              { value: true, label: u.yes },
              { value: false, label: u.no },
            ].map((o) => (
              <label className="choice-card" key={String(o.value)}>
                <input
                  type="radio"
                  name="answer"
                  checked={value === o.value}
                  onChange={() => setValue(o.value)}
                />
                {o.label}
              </label>
            ))}
          </div>
        )}
        {(q.type === 'single_choice' || q.type === 'multiple_choice') && (
          <>
            {q.type === 'multiple_choice' && <p>{u.multiple}</p>}
            <div className="choice-grid">
              {q.options.map((o) => (
                <label className="choice-card" key={o.value}>
                  <input
                    type={q.type === 'single_choice' ? 'radio' : 'checkbox'}
                    name="answer"
                    checked={
                      q.type === 'single_choice'
                        ? value === o.value
                        : Array.isArray(value) && value.includes(o.value)
                    }
                    onChange={(e) => {
                      if (q.type === 'single_choice') setValue(o.value);
                      else {
                        const previous = Array.isArray(value) ? value : [];
                        setValue(
                          e.target.checked
                            ? o.exclusive
                              ? [o.value]
                              : [
                                  ...previous.filter(
                                    (v) =>
                                      !q.options.find((option) => option.value === v)?.exclusive,
                                  ),
                                  o.value,
                                ]
                            : previous.filter((v) => v !== o.value),
                        );
                      }
                    }}
                  />
                  {o.label[language]}
                </label>
              ))}
            </div>
          </>
        )}
        <div className="actions">
          <button type="submit">{busy ? t.saving : t.next}</button>
        </div>
        <div className="actions secondary-actions">
          {q.allow_unknown && (
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => special('unknown', u.unknown)}
              >
                {u.unknown}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => special('not_reported', u.notReported)}
              >
                {u.notReported}
              </button>
            </>
          )}
          {!q.required && (
            <button type="button" className="secondary" onClick={() => special('skipped', u.skip)}>
              {u.skip}
            </button>
          )}
        </div>
      </fieldset>
    </form>
  );
}
