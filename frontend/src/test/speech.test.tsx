import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import type { Question } from '../api/interview';
import QuestionAudioPlayer from '../components/kiosk/QuestionAudioPlayer';
import QuestionRenderer from '../components/kiosk/QuestionRenderer';
import VoiceRecorder from '../components/kiosk/VoiceRecorder';
import { speechCopy } from '../i18n/speech';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map((k) => [k, vi.fn()])) };
});

class MockMediaRecorder {
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  static isTypeSupported = vi.fn().mockReturnValue(true);
  constructor() {}
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    if (this.ondataavailable) {
      this.ondataavailable({ data: new Blob(['dummy audio chunk'], { type: 'audio/webm' }) });
    }
    if (this.onstop) {
      this.onstop();
    }
  }
}

class MockAudio {
  src = '';
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn().mockImplementation(() => {
    return Promise.resolve();
  });
  pause = vi.fn();
}

const mockQuestion: Question = {
  question_id: 'chief_complaint',
  field: 'chief_complaint',
  type: 'short_text',
  text: {
    en: 'What is your primary symptom?',
    bn: 'আপনার প্রধান উপসর্গ কী?',
    hi: 'आपका मुख्य लक्षण क्या है?',
  },
  required: true,
  allow_unknown: false,
  options: [],
  constraints: {
    max_length: 500,
  },
};

describe('Speech and TTS Component Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (window as unknown as { MediaRecorder: unknown }).MediaRecorder = MockMediaRecorder;
    (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = MockMediaRecorder;
    (window as unknown as { Audio: unknown }).Audio = MockAudio;
    (globalThis as unknown as { Audio: unknown }).Audio = MockAudio;
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
      configurable: true,
      writable: true,
    });
  });

  describe('QuestionAudioPlayer (TTS)', () => {
    it('renders localized Listen button in English, Bengali, and Hindi', () => {
      const { rerender } = render(
        <QuestionAudioPlayer sessionId="sess-1" questionId="q1" language="en" />
      );
      expect(screen.getByRole('button', { name: new RegExp(speechCopy.en.listen, 'i') })).toBeInTheDocument();

      rerender(<QuestionAudioPlayer sessionId="sess-1" questionId="q1" language="bn" />);
      expect(screen.getByRole('button', { name: new RegExp(speechCopy.bn.listen, 'i') })).toBeInTheDocument();

      rerender(<QuestionAudioPlayer sessionId="sess-1" questionId="q1" language="hi" />);
      expect(screen.getByRole('button', { name: new RegExp(speechCopy.hi.listen, 'i') })).toBeInTheDocument();
    });

    it('requests synthesis and triggers audio playback', async () => {
      vi.mocked(api.synthesizeSpeech).mockResolvedValue({
        audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
        media_type: 'audio/wav',
        text: 'What is your primary symptom?',
        language: 'en',
        provider: 'mock',
        status: 'success',
        reason: null,
      });

      render(<QuestionAudioPlayer sessionId="sess-1" questionId="q1" language="en" />);
      const btn = screen.getByRole('button', { name: new RegExp(speechCopy.en.listen, 'i') });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(api.synthesizeSpeech).toHaveBeenCalledWith('sess-1', 'q1');
      });
    });

    it('handles TTS error without breaking the interface', async () => {
      vi.mocked(api.synthesizeSpeech).mockRejectedValue(new Error('Network error'));

      render(<QuestionAudioPlayer sessionId="sess-1" questionId="q1" language="en" />);
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.listen, 'i') }));

      await waitFor(() => {
        expect(screen.getByText(speechCopy.en.ttsError)).toBeInTheDocument();
      });
      expect(screen.getByRole('button', { name: new RegExp(speechCopy.en.listen, 'i') })).toBeInTheDocument();
    });
  });

  describe('VoiceRecorder', () => {
    it('shows fallback if MediaRecorder is not supported in the browser', () => {
      delete (window as unknown as { MediaRecorder?: unknown }).MediaRecorder;
      delete (globalThis as unknown as { MediaRecorder?: unknown }).MediaRecorder;

      render(
        <VoiceRecorder
          sessionId="sess-1"
          questionId="q1"
          language="en"
          disabled={false}
          onConfirmCandidate={vi.fn()}
          onEditCandidate={vi.fn()}
        />
      );

      expect(screen.getByText(speechCopy.en.voiceUnavailable)).toBeInTheDocument();
    });

    it('handles permission denied error gracefully', async () => {
      Object.defineProperty(navigator, 'mediaDevices', {
        value: {
          getUserMedia: vi.fn().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError')),
        },
        configurable: true,
        writable: true,
      });

      render(
        <VoiceRecorder
          sessionId="sess-1"
          questionId="q1"
          language="en"
          disabled={false}
          onConfirmCandidate={vi.fn()}
          onEditCandidate={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') }));

      await waitFor(() => {
        expect(screen.getByText(speechCopy.en.micDenied)).toBeInTheDocument();
      });
    });

    it('completes recording flow, presents candidate review card, and handles confirm', async () => {
      const onConfirm = vi.fn();
      const onEdit = vi.fn();

      vi.mocked(api.transcribeSpeech).mockResolvedValue({
        transcript: 'I have severe chest pain',
        language: 'en',
        confidence: null,
        provider: 'mock',
        model: 'deterministic-mock-asr',
        status: 'success',
        reason: null,
      });

      render(
        <VoiceRecorder
          sessionId="sess-1"
          questionId="q1"
          language="en"
          disabled={false}
          onConfirmCandidate={onConfirm}
          onEditCandidate={onEdit}
        />
      );

      // Start recording
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') }));

      // Shows recording state
      await waitFor(() => {
        expect(screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') })).toBeInTheDocument();
      });

      // Stop recording
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));

      // Candidate review card appears
      await waitFor(() => {
        expect(screen.getByText(speechCopy.en.candidateTitle)).toBeInTheDocument();
        expect(screen.getByText(/I have severe chest pain/)).toBeInTheDocument();
      });

      // Confirm candidate
      const confirmBtn = screen.getByRole('button', { name: new RegExp(speechCopy.en.confirmCandidate, 'i') });
      fireEvent.click(confirmBtn);

      expect(onConfirm).toHaveBeenCalledWith('I have severe chest pain');
    });

    it('allows patient to edit candidate transcript before submitting', async () => {
      const onConfirm = vi.fn();
      const onEdit = vi.fn();

      vi.mocked(api.transcribeSpeech).mockResolvedValue({
        transcript: 'আমার বুকে ব্যথা হচ্ছে',
        language: 'bn',
        confidence: null,
        provider: 'mock',
        model: 'deterministic-mock-asr',
        status: 'success',
        reason: null,
      });

      render(
        <VoiceRecorder
          sessionId="sess-1"
          questionId="q1"
          language="bn"
          disabled={false}
          onConfirmCandidate={onConfirm}
          onEditCandidate={onEdit}
        />
      );

      // Start recording
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.bn.speak, 'i') }));
      await waitFor(() => {
        expect(screen.getByRole('button', { name: new RegExp(speechCopy.bn.stop, 'i') })).toBeInTheDocument();
      });
      // Stop recording
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.bn.stop, 'i') }));

      // Review card in Bengali
      await waitFor(() => {
        expect(screen.getByText(speechCopy.bn.candidateTitle)).toBeInTheDocument();
        expect(screen.getByText(/আমার বুকে ব্যথা হচ্ছে/)).toBeInTheDocument();
      });

      // Click Edit
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.bn.editCandidate, 'i') }));

      expect(onEdit).toHaveBeenCalledWith('আমার বুকে ব্যথা হচ্ছে');
      // Candidate card is dismissed
      expect(screen.queryByText(speechCopy.bn.candidateTitle)).not.toBeInTheDocument();
    });

    it('allows patient to record again / retry from candidate review card', async () => {
      vi.mocked(api.transcribeSpeech).mockResolvedValue({
        transcript: 'Candidate 1',
        language: 'en',
        confidence: null,
        provider: 'mock',
        model: 'deterministic-mock-asr',
        status: 'success',
        reason: null,
      });

      render(
        <VoiceRecorder
          sessionId="sess-1"
          questionId="q1"
          language="en"
          disabled={false}
          onConfirmCandidate={vi.fn()}
          onEditCandidate={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') }));
      await waitFor(() => screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));

      await waitFor(() => {
        expect(screen.getByText(/Candidate 1/)).toBeInTheDocument();
      });

      // Click Record again
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.recordAgain, 'i') }));

      // Resets candidate card, ready to speak again
      await waitFor(() => {
        expect(screen.queryByText(/Candidate 1/)).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') })).toBeInTheDocument();
      });
    });
  });

  describe('QuestionRenderer integration with Voice and Consent', () => {
    it('does NOT display voice recorder when voiceConsent is false', () => {
      render(
        <QuestionRenderer
          question={mockQuestion}
          initial={null}
          language="en"
          busy={false}
          sessionId="sess-1"
          voiceConsent={false}
          onSave={vi.fn()}
        />
      );

      expect(screen.queryByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') })).not.toBeInTheDocument();
      expect(screen.getByLabelText('Your answer')).toBeInTheDocument();
    });

    it('displays voice recorder when voiceConsent is true and submits answer with source="voice"', async () => {
      const onSave = vi.fn();
      vi.mocked(api.transcribeSpeech).mockResolvedValue({
        transcript: 'I have chest pain',
        language: 'en',
        confidence: null,
        provider: 'mock',
        model: 'deterministic-mock-asr',
        status: 'success',
        reason: null,
      });

      render(
        <QuestionRenderer
          question={mockQuestion}
          initial={null}
          language="en"
          busy={false}
          sessionId="sess-1"
          voiceConsent={true}
          onSave={onSave}
        />
      );

      // Voice recorder button is present
      expect(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') })).toBeInTheDocument();

      // Record speech
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') }));
      await waitFor(() => screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));

      // Confirm candidate
      await waitFor(() => screen.getByRole('button', { name: new RegExp(speechCopy.en.confirmCandidate, 'i') }));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.confirmCandidate, 'i') }));

      // Saved with source = 'voice'
      expect(onSave).toHaveBeenCalledWith({
        value: 'I have chest pain',
        raw_value: 'I have chest pain',
        status: 'answered',
        source: 'voice',
      });
    });

    it('populates typed input on candidate edit, allowing patient to modify and submit typed answer', async () => {
      const onSave = vi.fn();
      vi.mocked(api.transcribeSpeech).mockResolvedValue({
        transcript: 'I have chest pain',
        language: 'en',
        confidence: null,
        provider: 'mock',
        model: 'deterministic-mock-asr',
        status: 'success',
        reason: null,
      });

      render(
        <QuestionRenderer
          question={mockQuestion}
          initial={null}
          language="en"
          busy={false}
          sessionId="sess-1"
          voiceConsent={true}
          onSave={onSave}
        />
      );

      // Record speech
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.speak, 'i') }));
      await waitFor(() => screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.stop, 'i') }));

      // Click Edit
      await waitFor(() => screen.getByRole('button', { name: new RegExp(speechCopy.en.editCandidate, 'i') }));
      fireEvent.click(screen.getByRole('button', { name: new RegExp(speechCopy.en.editCandidate, 'i') }));

      // Text input has value 'I have chest pain'
      const input = screen.getByLabelText('Your answer') as HTMLInputElement;
      expect(input.value).toBe('I have chest pain');

      // Patient edits the text
      fireEvent.change(input, { target: { value: 'I have chest pain and shortness of breath' } });

      // Patient clicks "Save and continue"
      fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));

      // Submits as typed
      expect(onSave).toHaveBeenCalledWith({
        value: 'I have chest pain and shortness of breath',
        raw_value: 'I have chest pain and shortness of breath',
        status: 'answered',
        source: 'typed',
      });
    });
  });
});
