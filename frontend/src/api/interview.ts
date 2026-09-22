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
  origin?: string;
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
  namespace: 'standard' | 'ayush_demo' | 'legacy' | 'other';
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

export interface RAGSuggestion {
  question: string;
  reason: string;
  source_chunk_ids: string[];
  origin: string;
  candidate_id?: string | null;
  target_field?: string | null;
  target_domain?: string | null;
  similarity_score?: number | null;
  source_title?: string | null;
  source_section?: string | null;
  generation_provider?: string | null;
  generation_model?: string | null;
  generation_fallback_used?: boolean | null;
  generation_latency_ms?: number | null;
  template_question?: string | null;
  display_language?: string | null;
  translated_question?: string | null;
  translation_provider?: string | null;
  translation_fallback_used?: boolean | null;
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
  covered_domains?: string[];
  missing_required_domains?: string[];
  missing_optional_domains?: string[];
  progress: { addressed: number; applicable: number; position: number };
  is_complete: boolean;
  history: ClinicalHistory | null;
  red_flag_alert?: AlertSummary | null;
  rag_suggestions?: RAGSuggestion[];
  document_confirmation?: {
    question_source: 'DOCUMENT_CONFIRMATION';
    target_field: string;
    evidence_id: string;
    source_fact_id: string;
    source_document_id?: string | null;
    document_filename?: string | null;
    page_number?: number | null;
    bounding_box?: Record<string, unknown> | unknown[] | null;
    ocr_provider?: string | null;
    ocr_model?: string | null;
    original_extracted_value: string;
    verification_state: string;
  } | null;
  continuity_reconfirmation?: {
    question_source: 'CONTINUITY_RECONFIRMATION';
    target_field: string;
    evidence_id: string;
    source_session_id: string;
    historical_value: unknown;
    canonical_field: string;
    concept?: string | null;
  } | null;
}

export type CoverageState =
  'CONFIRMED' | 'DOCUMENT_SUPPORTED_UNCONFIRMED' | 'CONFLICTED' | 'MISSING' | 'NOT_APPLICABLE';

export interface CoverageResponse {
  session_id: string;
  required: number;
  confirmed: number;
  document_supported_unconfirmed: number;
  conflicted: number;
  missing: number;
  not_applicable: number;
  fields: Array<{
    field: string;
    label: string;
    required: boolean;
    applicable: boolean;
    state: CoverageState;
    patient_answer_id?: string | null;
    provenance: Array<{
      evidence_id: string;
      source_fact_id: string;
      source_document_id?: string | null;
      document_filename?: string | null;
      page_number?: number | null;
      bounding_box?: Record<string, unknown> | unknown[] | null;
      ocr_provider?: string | null;
      ocr_model?: string | null;
      original_extracted_value?: string | null;
      verification_state: string;
    }>;
  }>;
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
