import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { Language } from '../../api/client';
import { speechCopy } from '../../i18n/speech';

export interface QuestionAudioPlayerProps {
  sessionId: string;
  questionId: string;
  language: Language;
  disabled?: boolean;
}

export default function QuestionAudioPlayer({
  sessionId,
  questionId,
  language,
  disabled = false,
}: QuestionAudioPlayerProps) {
  const t = speechCopy[language];
  const [status, setStatus] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [usingBrowserVoice, setUsingBrowserVoice] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const [prevId, setPrevId] = useState(questionId);
  const [prevLang, setPrevLang] = useState(language);

  if (questionId !== prevId || language !== prevLang) {
    setPrevId(questionId);
    setPrevLang(language);
    setStatus('idle');
    setErrorMsg(null);
    setUsingBrowserVoice(false);
  }

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (utteranceRef.current) {
        window.speechSynthesis?.cancel();
        utteranceRef.current = null;
      }
    };
  }, [questionId, language]);

  async function handlePlay() {
    if (disabled || status === 'loading') return;

    if (status === 'playing') {
      audioRef.current?.pause();
      audioRef.current = null;
      if (utteranceRef.current) window.speechSynthesis.cancel();
      utteranceRef.current = null;
      setStatus('idle');
      return;
    }

    setStatus('loading');
    setErrorMsg(null);

    try {
      const res = await api.synthesizeSpeech(sessionId, questionId);
      if (res.provider === 'mock' || res.status !== 'success' || !res.audio_base64) {
        if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
          setStatus('error');
          setErrorMsg(t.ttsError);
          return;
        }
        const utterance = new SpeechSynthesisUtterance(res.text);
        utterance.lang = { en: 'en-IN', bn: 'bn-IN', hi: 'hi-IN' }[language];
        utterance.onend = () => {
          utteranceRef.current = null;
          setStatus('idle');
        };
        utterance.onerror = () => {
          utteranceRef.current = null;
          setStatus('error');
          setErrorMsg(t.ttsError);
        };
        utteranceRef.current = utterance;
        setUsingBrowserVoice(true);
        window.speechSynthesis.speak(utterance);
        setStatus('playing');
        return;
      }

      setUsingBrowserVoice(false);
      const audioUri = `data:${res.media_type || 'audio/wav'};base64,${res.audio_base64}`;
      const audio = new Audio(audioUri);
      audioRef.current = audio;

      audio.onended = () => {
        setStatus('idle');
        audioRef.current = null;
      };

      audio.onerror = () => {
        setStatus('error');
        setErrorMsg(t.ttsError);
        audioRef.current = null;
      };

      await audio.play();
      setStatus('playing');
    } catch {
      setStatus('error');
      setErrorMsg(t.ttsError);
      audioRef.current = null;
    }
  }

  return (
    <div className="question-audio-player">
      <button
        type="button"
        className={`audio-button ${status === 'playing' ? 'playing' : ''}`}
        onClick={handlePlay}
        disabled={disabled || status === 'loading'}
        aria-label={`${t.listen}: ${status === 'playing' ? t.playing : ''}`}
      >
        <span aria-hidden="true" className="speaker-icon">
          {status === 'playing' ? '⏹' : '🔊'}
        </span>
        <span>{status === 'loading' ? '...' : status === 'playing' ? t.playing : t.listen}</span>
      </button>
      {Boolean(errorMsg) && (
        <span className="audio-error" role="alert">
          {errorMsg}
        </span>
      )}
      {usingBrowserVoice && !errorMsg && (
        <span className="muted" role="note">
          {t.browserTtsFallback}
        </span>
      )}
    </div>
  );
}
