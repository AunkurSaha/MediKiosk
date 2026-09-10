import type { Language } from '../api/client';

export interface SpeechCopy {
  speak: string;
  listening: string;
  stop: string;
  transcribing: string;
  candidateTitle: string;
  confirmCandidate: string;
  editCandidate: string;
  recordAgain: string;
  cancelVoice: string;
  voiceUnavailable: string;
  listen: string;
  playing: string;
  ttsError: string;
  micDenied: string;
  voiceConsentLabel: string;
  voiceConsentNote: string;
}

const en: SpeechCopy = {
  speak: 'Speak',
  listening: 'Listening… click to finish',
  stop: 'Finish speaking',
  transcribing: 'Transcribing audio…',
  candidateTitle: 'You said:',
  confirmCandidate: 'Confirm',
  editCandidate: 'Edit',
  recordAgain: 'Record again',
  cancelVoice: 'Cancel',
  voiceUnavailable: 'Voice input is unavailable. Please type your answer.',
  listen: 'Listen',
  playing: 'Playing…',
  ttsError: 'Audio playback unavailable.',
  micDenied: 'Microphone permission denied. Please allow microphone access or type your answer.',
  voiceConsentLabel: 'Allow microphone use for speaking your answers (optional)',
  voiceConsentNote:
    'Spoken audio is converted to text and deleted immediately. Raw audio is never stored.',
};

const bn: SpeechCopy = {
  speak: 'বলুন',
  listening: 'শুনছি… শেষ করতে চাপুন',
  stop: 'বলা শেষ করুন',
  transcribing: 'অডিও প্রক্রিয়াকরণ হচ্ছে…',
  candidateTitle: 'আপনি বলেছেন:',
  confirmCandidate: 'নিশ্চিত করুন',
  editCandidate: 'সংশোধন করুন',
  recordAgain: 'আবার বলুন',
  cancelVoice: 'বাতিল',
  voiceUnavailable: 'ভয়েস ইনপুট উপলব্ধ নেই। অনুগ্রহ করে টাইপ করুন।',
  listen: 'শুনুন',
  playing: 'বাজছে…',
  ttsError: 'অডিও প্লেব্যাক উপলব্ধ নেই।',
  micDenied: 'মাইক্রোফোনের অনুমতি পাওয়া যায়নি। মাইক্রোফোন চালু করুন অথবা টাইপ করুন।',
  voiceConsentLabel: 'উত্তর মুখে বলার জন্য মাইক্রোফোন ব্যবহারের অনুমতি দিন (ঐচ্ছিক)',
  voiceConsentNote:
    'কথা বলা অডিও লেখায় রূপান্তর করে সাথে সাথে মুছে ফেলা হয়। অডিও কখনো সংরক্ষণ করা হয় না।',
};

const hi: SpeechCopy = {
  speak: 'बोलें',
  listening: 'सुन रहे हैं… समाप्त करने के लिए दबाएँ',
  stop: 'बोलना समाप्त करें',
  transcribing: 'ऑडियो ट्रांसक्राइब हो रहा है…',
  candidateTitle: 'आपने कहा:',
  confirmCandidate: 'पुष्टि करें',
  editCandidate: 'सुधारें',
  recordAgain: 'फिर बोलें',
  cancelVoice: 'रद्द करें',
  voiceUnavailable: 'आवाज़ इनपुट उपलब्ध नहीं है। कृपया टाइप करें।',
  listen: 'सुनें',
  playing: 'चल रहा है…',
  ttsError: 'ऑडियो प्लेबैक उपलब्ध नहीं है।',
  micDenied: 'माइक्रोफ़ोन की अनुमति अस्वीकृत। कृपया माइक्रोफ़ोन चालू करें या टाइप करें।',
  voiceConsentLabel: 'उत्तर बोलने के लिए माइक्रोफ़ोन के उपयोग की अनुमति दें (वैकल्पिक)',
  voiceConsentNote:
    'बोली गई आवाज़ को पाठ में बदलकर तुरंत हटा दिया जाता है। कच्ची आवाज़ कभी संग्रहीत नहीं की जाती।',
};

export const speechCopy: Record<Language, SpeechCopy> = { en, bn, hi };
