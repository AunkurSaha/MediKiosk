import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { Language } from '../../api/client';
import { speechCopy } from '../../i18n/speech';

export interface VoiceRecorderProps {
  sessionId: string;
  questionId: string;
  language: Language;
  disabled?: boolean;
  fixtureId?: string;
  onConfirmCandidate: (transcript: string) => void;
  onEditCandidate: (transcript: string) => void;
}

type RecordingState = 'idle' | 'recording' | 'transcribing' | 'candidate' | 'error';

export default function VoiceRecorder({
  sessionId,
  questionId,
  language,
  disabled = false,
  fixtureId,
  onConfirmCandidate,
  onEditCandidate,
}: VoiceRecorderProps) {
  const t = speechCopy[language];
  const [state, setState] = useState<RecordingState>('idle');
  const [candidateText, setCandidateText] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      stopTracks();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const isSupported =
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    Boolean(navigator?.mediaDevices?.getUserMedia);

  if (!isSupported) {
    return (
      <div className="voice-recorder-container" data-testid="voice-recorder">
        <p className="voice-unsupported-note muted" style={{ fontSize: '0.85rem' }}>
          {t.voiceUnavailable}
        </p>
      </div>
    );
  }

  function stopTracks() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }

  async function startRecording() {
    if (disabled) return;
    setErrorMessage(null);
    setCandidateText('');
    setRecordingSeconds(0);
    chunksRef.current = [];

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setState('error');
      setErrorMessage(t.voiceUnavailable);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4')
            ? 'audio/mp4'
            : '';

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        stopTracks();
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        void handleAudioReady();
      };

      recorder.start(250);
      setState('recording');

      timerRef.current = window.setInterval(() => {
        setRecordingSeconds((sec) => {
          if (sec >= 30) {
            // Max 30 seconds for prototype question response
            stopRecording();
            return sec;
          }
          return sec + 1;
        });
      }, 1000);
    } catch (err) {
      stopTracks();
      setState('error');
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setErrorMessage(t.micDenied);
      } else {
        setErrorMessage(t.voiceUnavailable);
      }
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }

  function cancelRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    stopTracks();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    chunksRef.current = [];
    setState('idle');
    setErrorMessage(null);
    setCandidateText('');
  }

  async function handleAudioReady() {
    const chunks = chunksRef.current;
    chunksRef.current = [];

    if (chunks.length === 0) {
      setState('error');
      setErrorMessage(t.voiceUnavailable);
      return;
    }

    const mimeType = mediaRecorderRef.current?.mimeType || 'audio/webm';
    const audioBlob = new Blob(chunks, { type: mimeType });

    setState('transcribing');
    try {
      const res = await api.transcribeSpeech(sessionId, audioBlob, questionId, fixtureId);
      if (res.status === 'success' && res.transcript) {
        setCandidateText(res.transcript);
        setState('candidate');
      } else {
        setState('error');
        setErrorMessage(t.voiceUnavailable);
      }
    } catch (err) {
      setState('error');
      if (err instanceof ApiError && err.code === 'VOICE_CONSENT_REQUIRED') {
        setErrorMessage(t.voiceUnavailable);
      } else {
        setErrorMessage(t.voiceUnavailable);
      }
    }
  }

  return (
    <div className="voice-recorder-container" data-testid="voice-recorder">
      {state === 'idle' && (
        <button
          type="button"
          className="secondary voice-speak-button"
          onClick={startRecording}
          disabled={disabled}
        >
          <span aria-hidden="true">🎙️</span> {t.speak}
        </button>
      )}

      {state === 'recording' && (
        <div className="recording-panel" role="region" aria-label={t.listening}>
          <div className="recording-status">
            <span className="recording-pulse" aria-hidden="true" />
            <span className="recording-label">
              {t.listening} ({recordingSeconds}s)
            </span>
          </div>
          <div className="recording-actions">
            <button
              type="button"
              className="primary stop-recording-button"
              onClick={stopRecording}
            >
              ⏹ {t.stop}
            </button>
            <button
              type="button"
              className="secondary cancel-recording-button"
              onClick={cancelRecording}
            >
              ✕ {t.cancelVoice}
            </button>
          </div>
        </div>
      )}

      {state === 'transcribing' && (
        <div className="transcribing-panel" role="status">
          <span className="spinner" aria-hidden="true" />
          <p>{t.transcribing}</p>
        </div>
      )}

      {state === 'candidate' && (
        <div className="candidate-review-card" role="region" aria-label={t.candidateTitle}>
          <p className="candidate-heading">{t.candidateTitle}</p>
          <blockquote className="candidate-text" lang={language}>
            &ldquo;{candidateText}&rdquo;
          </blockquote>
          <div className="candidate-actions">
            <button
              type="button"
              className="primary confirm-candidate-button"
              onClick={() => onConfirmCandidate(candidateText)}
            >
              ✓ {t.confirmCandidate}
            </button>
            <button
              type="button"
              className="secondary edit-candidate-button"
              onClick={() => {
                onEditCandidate(candidateText);
                setState('idle');
              }}
            >
              ✏️ {t.editCandidate}
            </button>
            <button
              type="button"
              className="secondary retry-recording-button"
              onClick={startRecording}
            >
              🔄 {t.recordAgain}
            </button>
            <button
              type="button"
              className="secondary cancel-candidate-button"
              onClick={() => {
                setState('idle');
                setCandidateText('');
              }}
            >
              ✕ {t.cancelVoice}
            </button>
          </div>
        </div>
      )}

      {state === 'error' && (
        <div className="voice-error-panel" role="alert">
          <p className="error-text">{errorMessage || t.voiceUnavailable}</p>
          <div className="error-actions">
            <button type="button" className="secondary" onClick={startRecording}>
              🔄 {t.recordAgain}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setState('idle');
                setErrorMessage(null);
              }}
            >
              ✕ {t.cancelVoice}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
