// Regression fixture for the Phase 1 contract; never imported by application code.
import type { Question, InterviewState } from '../api/interview';
export const questions: Question[] = [
  {
    question_id: 'chief_complaint',
    field: 'chief_complaint',
    type: 'short_text',
    required: true,
    allow_unknown: true,
    text: {
      en: 'What brings you to see the doctor today?',
      bn: 'আজ কী সমস্যার জন্য চিকিৎসকের কাছে এসেছেন?',
      hi: 'आज आप किस समस्या के लिए चिकित्सक से मिलने आए हैं?',
    },
    constraints: {
      max_length: 4000,
    },
    options: [],
  },
  {
    question_id: 'onset_duration',
    field: 'onset_duration',
    type: 'short_text',
    required: true,
    allow_unknown: true,
    text: {
      en: 'When did this problem start?',
      bn: 'এই সমস্যা কখন শুরু হয়েছে?',
      hi: 'यह समस्या कब शुरू हुई?',
    },
    constraints: {
      max_length: 4000,
    },
    options: [],
  },
  {
    question_id: 'medications',
    field: 'medications',
    type: 'short_text',
    required: true,
    allow_unknown: true,
    text: {
      en: 'What medicines are you currently taking?',
      bn: 'বর্তমানে কী কী ওষুধ খাচ্ছেন?',
      hi: 'आप अभी कौन-कौन सी दवाएँ ले रहे हैं?',
    },
    constraints: {
      max_length: 4000,
    },
    options: [],
  },
  {
    question_id: 'allergies',
    field: 'allergies',
    type: 'short_text',
    required: true,
    allow_unknown: true,
    text: {
      en: 'Do you have any allergies to medicines, foods, or anything else?',
      bn: 'ওষুধ, খাবার বা অন্য কিছুর প্রতি আপনার অ্যালার্জি আছে কি?',
      hi: 'क्या आपको किसी दवा, भोजन या अन्य चीज़ से एलर्जी है?',
    },
    constraints: {
      max_length: 4000,
    },
    options: [],
  },
  {
    question_id: 'past_history',
    field: 'past_history',
    type: 'short_text',
    required: true,
    allow_unknown: true,
    text: {
      en: 'What past illnesses, operations, or ongoing health conditions should the doctor know about?',
      bn: 'আগের অসুস্থতা, অস্ত্রোপচার বা চলমান স্বাস্থ্যসমস্যা সম্পর্কে চিকিৎসককে কী জানাতে চান?',
      hi: 'पुरानी बीमारियों, ऑपरेशन या वर्तमान स्वास्थ्य समस्याओं के बारे में चिकित्सक को क्या बताना चाहेंगे?',
    },
    constraints: {
      max_length: 4000,
    },
    options: [],
  },
];
export function legacyState(index = 0): InterviewState {
  return {
    selection_required: false,
    flows: [],
    flow_id: 'legacy.intake',
    flow_version: '1.0.0',
    namespace: 'legacy',
    revision: index,
    section: { en: 'History', bn: 'ইতিহাস', hi: 'इतिहास' },
    question: questions[index] || null,
    current_answer: null,
    previous_question_id: index > 0 ? questions[index - 1].question_id : null,
    active_answers: [],
    inactive_question_ids: [],
    missing_required: questions.slice(index).map((q) => q.question_id),
    progress: { addressed: index, applicable: 5, position: Math.min(index + 1, 5) },
    is_complete: index >= 5,
    history: null,
  };
}
