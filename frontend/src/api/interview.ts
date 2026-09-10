import type { Language } from './client';

export type Localized = Record<Language, string>;
export type AnswerValue =
  string | boolean | number | string[] | { amount: number; unit: string } | null;
export type AnswerStatus = 'answered' | 'unknown' | 'not_reported' | 'skipped';
export interface Question {
  question_id: string;
  field: string;
  type:
    | 'boolean'
    | 'single_choice'
    | 'multiple_choice'
    | 'short_text'
    | 'number'
    | 'duration'
    | 'severity';
  text: Localized;
  required: boolean;
  allow_unknown: boolean;
  options: { value: string; label: Localized; exclusive: boolean }[];
  constraints: {
    minimum?: number | null;
    maximum?: number | null;
    max_length: number;
    integer?: boolean;
    unit?: string | null;
  };
}
export interface Fact {
  answer_id: string;
  question_id: string;
  field: string;
  label: Localized;
  status: AnswerStatus;
  value: AnswerValue;
  raw_value: string;
  source: string;
  language: Language;
  verification_status: 'patient_reported';
  recorded_at: string;
  normalization?: Normalization | null;
}

export interface Normalization {
  id: string | null;
  source_answer_id: string;
  source_question_id: string;
  canonical_field: string;
  original_language: string;
  original_text: string;
  status: 'normalized' | 'unrecognized' | 'unknown' | 'unavailable';
  reason: string | null;
  facts: {
    normalized_concept: string;
    normalized_display: string;
    normalized_value: boolean | string | null;
    polarity?: 'present' | 'absent';
    evidence: string;
    certainty: 'certain' | 'uncertain' | 'unknown';
    confidence: number | null;
    verification_status: 'machine_normalized' | 'needs_verification';
  }[];
  provider: string | null;
  provider_version: string | null;
  schema_version: '1.0' | '1.1';
  model?: string | null;
  prompt_version?: string | null;
  latency_ms?: number | null;
  token_usage?: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  } | null;
  policy_version: '1.0';
  created_at: string | null;
}
export interface ClinicalHistory {
  schema_version: 1;
  flow_id: string;
  flow_version: string;
  namespace: 'standard' | 'ayush_demo' | 'legacy';
  selected_complaint: Localized;
  selection_source: 'patient_selected' | 'legacy_intake';
  sections: { section_id: string; label: Localized; facts: Fact[] }[];
}
export interface AlertSummary {
  id: string;
  rule_id: string;
  priority: 'emergency' | 'urgent' | 'priority';
  category: string;
  reason: string;
  created_at: string;
}

export interface InterviewState {
  selection_required: boolean;
  flows: { flow_id: string; version: string; namespace: string; label: Localized }[];
  flow_id: string | null;
  flow_version: string | null;
  namespace: string | null;
  revision: number;
  section: Localized | null;
  question: Question | null;
  current_answer: Fact | null;
  previous_question_id: string | null;
  active_answers: Fact[];
  inactive_question_ids: string[];
  missing_required: string[];
  progress: { addressed: number; applicable: number; position: number };
  is_complete: boolean;
  history: ClinicalHistory | null;
  red_flag_alert?: AlertSummary | null;
}
export interface Submission {
  request_id: string;
  expected_revision: number;
  question_id: string;
  value: AnswerValue;
  status: AnswerStatus;
  raw_value: string;
  source: 'typed' | 'touch' | 'voice';
  voice_candidate?: string;
  language: Language;
}

export interface TranscriptionResponse {
  status: 'success' | 'unavailable';
  transcript: string | null;
  candidate_token?: string | null;
  language: Language;
  confidence: number | null;
  provider: string;
  model: string | null;
  reason: string | null;
}

export interface SpeechSynthesisResponse {
  status: 'success' | 'unavailable';
  audio_base64: string | null;
  media_type: string;
  text: string;
  language: Language;
  provider: string;
  reason: string | null;
}
