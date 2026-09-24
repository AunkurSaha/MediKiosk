import type {
  AnswerValue,
  ClinicalHistory,
  CoverageResponse,
  InterviewState,
  SpeechSynthesisResponse,
  Submission,
  TranscriptionResponse,
} from './interview';
export type Language = 'en' | 'bn' | 'hi';
export type JourneyMode = 'PRE_ARRIVAL' | 'ON_SITE';
export type FieldName =
  'chief_complaint' | 'onset_duration' | 'medications' | 'allergies' | 'past_history';
export type IntakeStatus =
  'intake' | 'ready_for_review' | 'under_review' | 'confirmed' | 'cancelled';
export interface Session {
  id: string;
  patient_id: string;
  hospital_token: string;
  language: Language;
  status: IntakeStatus;
  created_at: string;
  completed_at: string | null;
  user_id?: string | null;
  hospital_id?: string | null;
  selected_doctor_id?: string | null;
  journey_mode?: JourneyMode;
}
export type ComplaintCategory =
  | 'CHEST_DISCOMFORT'
  | 'FEVER'
  | 'HEADACHE'
  | 'BREATHING_DIFFICULTY'
  | 'ABDOMINAL_PAIN'
  | 'COUGH'
  | 'SKIN_PROBLEM'
  | 'INJURY'
  | 'JOINT_PAIN'
  | 'OTHER';
export interface RapidRoutingState {
  phase: 'chief_complaint' | 'confirm_complaint' | 'rapid_interview' | 'result';
  revision: number;
  mapping?: {
    original_text: string;
    translated_text?: string | null;
    language: Language;
    source: 'card' | 'typed' | 'voice';
    candidate_category: ComplaintCategory;
    mapping_provider: string;
    patient_confirmed: boolean;
  } | null;
  chief_complaint?: ComplaintCategory | null;
  question?: {
    question_id: string;
    concept_code: string;
    target_field: string;
    prompt: Record<Language, string>;
    input_type: 'boolean' | 'severity' | 'single_choice' | 'number';
    options: { value: string; label: Record<Language, string> }[];
    required_for_safety: boolean;
    required_for_routing: boolean;
    equivalent_fields: string[];
    version: string;
  } | null;
  questions_asked: string[];
  questions_skipped: string[];
  result?: {
    id: string;
    session_id: string;
    chief_complaint: ComplaintCategory;
    routing_state: 'EMERGENCY' | 'URGENT' | 'ROUTINE_OPD' | 'TELECONSULT_MAY_BE_SUITABLE';
    suggested_specialty: string;
    triggered_red_flags: string[];
    supporting_evidence_ids: string[];
    questions_asked: string[];
    questions_skipped: string[];
    completed_at: string;
    routing_protocol_version: string;
  } | null;
}
export interface RoutingLocation {
  id: string;
  session_id: string;
  patient_id: string;
  source: string;
  latitude: number | null;
  longitude: number | null;
  locality: string | null;
  postal_code: string | null;
  precision: string | null;
  revision: number;
  captured_at: string;
}
export interface MediRouteResponse {
  id: string;
  session_id: string;
  clinical_routing_result_id: string;
  status: string;
  routing_state: string;
  suggested_specialty: string;
  directory_version: string;
  protocol_version: string;
  required_specialty: string;
  required_capabilities: string[];
  preferred_capabilities: string[];
  generated_at: string;
  recommendations: {
    facility_id: string;
    facility_name: string;
    rank: number;
    distance_km: number | null;
    eligibility_reasons: string[];
    ranking_reasons: string[];
    capabilities: string[];
    emergency_available: boolean;
  }[];
}
export interface DoctorMatchResponse {
  id: string;
  session_id: string;
  facility_id: string;
  required_specialty: string;
  directory_version: string;
  protocol_version: string;
  status: 'COMPLETED' | 'NO_ELIGIBLE_DOCTOR' | 'DOCTOR_MATCHING_BYPASSED_EMERGENCY';
  selected_doctor_id: string | null;
  generated_at: string;
  recommendations: {
    doctor_id: string;
    name: string;
    qualification: string | null;
    primary_specialty: string;
    expertise_tags: string[];
    languages: string[];
    availability_status: string;
    years_of_experience: number;
    rank: number;
    recommended: boolean;
    eligibility_reasons: string[];
    ranking_reasons: string[];
  }[];
}
export interface Hospital {
  id: string;
  name: string;
  city: string | null;
  address: string | null;
}
export interface DoctorMatch {
  doctor_id: string;
  name: string;
  qualification: string | null;
  specialties: string[];
  matched_specialty: string;
  waiting_count: number;
  recommended: boolean;
  fallback: boolean;
}

export interface PatientQueueEstimate {
  session_id: string;
  doctor_id: string;
  doctor_name: string;
  hospital_id: string;
  hospital_name: string;
  service_date: string | null;
  visit_token: string | null;
  status: 'WAITING' | 'CALLED' | 'IN_CONSULTATION' | 'COMPLETED' | 'CANCELLED';
  position: number | null;
  patients_ahead: number;
  estimated_wait_minutes: number;
  is_estimate: true;
  calculation_basis: string;
  policy_version: string;
}
export interface PacketMetadata {
  packet_id: string;
  session_id: string;
  packet_version: string;
  status: 'ACTIVE' | 'EXPIRED' | 'REVOKED';
  created_at: string;
  expires_at: string;
}
export interface PacketView extends PacketMetadata {
  snapshot: Record<string, unknown>;
  live_queue: { status: string; visit_token: string | null } | null;
}
export interface HandoffTokenIssued extends PacketMetadata {
  handoff_token: string;
  handoff_url: string;
  handoff_token_expires_at: string;
}
export interface DoctorRosterItem {
  doctor_id: string;
  name: string;
  waiting_count: number;
}
export interface DoctorMatches {
  specialty_codes: string[];
  fallback_used: boolean;
  items: DoctorMatch[];
}
export interface Answer {
  id: string;
  session_id: string;
  question_id: string;
  field: string;
  value: AnswerValue;
  raw_value: string;
  language: Language;
  source: string;
  verification_status: string;
}
export interface Patient {
  id: string;
  name: string;
  gender: 'female' | 'male' | 'non_binary' | 'other' | 'prefer_not_to_say' | null;
  age_years: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  demo_abha_id: string | null;
}
export interface EvidenceReference {
  statement_id: string;
  section: string;
  statement_text: string;
  source_type:
    | 'patient_answer'
    | 'normalized_fact'
    | 'medical_fact'
    | 'document'
    | 'alert'
    | 'discrepancy'
    | 'timeline';
  source_id: string;
  source_text: string;
  source_metadata: Record<string, unknown>;
  status?:
    | 'patient_reported'
    | 'patient_confirmed'
    | 'clinician_verified'
    | 'document_unverified'
    | 'conflicting'
    | 'normalized_unverified'
    | 'safety_rule'
    | 'timeline'
    | 'not_reported';
  badge?: string;
  evidence_refs?: string[];
  source_summary?: string[];
  provenance_explanation?: string[];
}

export interface SummaryCoverage {
  session_id: string;
  required: number;
  confirmed: number;
  document_supported_unconfirmed: number;
  conflicted: number;
  missing: number;
  not_applicable: number;
  fields: Record<string, unknown>[];
}

export interface StructuredSummarySection {
  section_key: string;
  title: string;
  content_lines: string[];
  items: Record<string, unknown>[];
  evidence: EvidenceReference[];
}

export interface StructuredClinicalSummary {
  session_id: string;
  generated_at: string;
  draft_version: number;
  draft_provider: string;
  sections: StructuredSummarySection[];
  evidence_references: EvidenceReference[];
  disclaimer: string | null;
  coverage?: SummaryCoverage | null;
}

export interface SummaryRevisionRecord {
  id: string;
  summary_id: string;
  version: number;
  revision_type: 'initial_draft' | 'edit' | 'regenerate' | 'confirmed' | 'amendment';
  actor_type: 'SYSTEM' | 'DOCTOR';
  actor_user_id: string | null;
  actor_name: string | null;
  reviewed_text: string;
  review_notes: string | null;
  structured_snapshot: Record<string, unknown> | null;
  created_at: string;
}

export interface Summary {
  id: string;
  session_id?: string;
  generated_text: string;
  reviewed_text: string | null;
  confirmed_text?: string | null;
  amended_text?: string | null;
  amended_by?: string | null;
  amended_at?: string | null;
  amendment_notes?: string | null;
  status: 'generated' | 'reviewed' | 'confirmed' | 'amended';
  draft_provider?: string;
  draft_version?: number;
  version: number;
  confirmed_by: string | null;
  confirmed_at: string | null;
  structured_summary?: StructuredClinicalSummary | null;
  evidence?: EvidenceReference[] | null;
  coverage?: SummaryCoverage | null;
  pre_arrival_packet?: Record<string, unknown> | null;
}
import type { AlertItem } from './triage';

export interface ExtractedMedication {
  name: string;
  dosage: string | null;
  unit?: string | null;
  frequency: string | null;
  route: string | null;
  duration: string | null;
  start_date?: string | null;
  end_date?: string | null;
  instructions?: string | null;
}

export interface ExtractedLabObservation {
  test_name: string;
  value: string;
  unit: string | null;
  reference_range: string | null;
  flag: string | null;
  observation_timestamp?: string | null;
}

export interface DocumentExtractionRecord {
  id: string;
  document_id: string;
  session_id: string;
  extractor: string;
  extractor_version: string;
  raw_text: string | null;
  structured_json: {
    document_type?: string;
    document_date?: string | null;
    medications?: ExtractedMedication[];
    observations?: ExtractedLabObservation[];
    [key: string]: unknown;
  };
  confidence: number | null;
  verification_status: 'unverified' | 'verified' | 'rejected';
  review_version: number;
  verified_by: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface DocumentRecord {
  id: string;
  session_id: string;
  object_key: string;
  original_filename: string;
  media_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  document_type: 'prescription' | 'lab_report' | 'other';
  document_date: string | null;
  processing_status:
    'pending' | 'processing' | 'completed' | 'failed' | 'unavailable' | 'mock_fixture';
  created_at: string;
  updated_at: string | null;
  extractions: DocumentExtractionRecord[];
}

export type FieldVerificationStatus = 'unverified' | 'verified' | 'flagged';
export type FieldVerificationType = 'interview_answer' | 'summary_statement';

export interface FieldVerificationRevisionRecord {
  id: string;
  version: number;
  status: string;
  actor_user_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface FieldVerificationRecord {
  id: string;
  session_id: string;
  field_type: FieldVerificationType;
  field_id: string;
  status: FieldVerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  notes: string | null;
  version: number;
  created_at: string;
  updated_at: string | null;
  revisions: FieldVerificationRevisionRecord[];
}

export interface FieldVerificationRequest {
  field_type: FieldVerificationType;
  field_id: string;
  status: FieldVerificationStatus;
  notes?: string;
  expected_version?: number;
}

export interface AuditTrailItem {
  id: string;
  timestamp: string;
  actor_type: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown>;
}

export interface AuditTrailResponse {
  session_id: string;
  total: number;
  items: AuditTrailItem[];
}

export interface DocumentFactLink {
  fact_id: string;
  fact_type: 'medication' | 'lab';
  label: string;
  verification_status: string;
}

export interface DocumentCrossReference {
  document_id: string;
  filename: string;
  document_type: string;
  created_at: string;
  medications: DocumentFactLink[];
  labs: DocumentFactLink[];
  discrepancies: string[];
  summary_statements: string[];
}

export interface CrossReferenceResponse {
  session_id: string;
  documents: DocumentCrossReference[];
  statement_cross_references: Record<string, Record<string, unknown>>;
}

export interface Detail {
  session: Session;
  patient: Patient;
  consent: {
    voice_processing: boolean;
    document_processing: boolean;
    share_with_doctor: boolean;
  } | null;
  answers: Answer[];
  summary: Summary | null;
  history?: ClinicalHistory | null;
  alerts?: AlertItem[];
  documents?: DocumentRecord[];
}
export interface SessionList {
  items: (Session & {
    patient_name: string;
    queue_status?: string | null;
    queue_joined_at?: string | null;
    visit_token?: string | null;
  })[];
}

export type VerificationStatus = 'unverified' | 'verified' | 'rejected';
export interface FactSource {
  source_type: 'document' | 'patient_answer';
  source_id: string;
  document_id: string | null;
  extraction_id: string | null;
  document_filename: string | null;
  raw_text: string | null;
  source_location: string | null;
}
export interface MedicationValue {
  name: string;
  dosage: string | null;
  unit: string | null;
  route: string | null;
  frequency: string | null;
  duration: string | null;
  start_date: string | null;
  end_date: string | null;
  instructions: string | null;
}
export interface LabValue {
  test_name: string;
  value: string;
  unit: string | null;
  reference_range: string | null;
  flag: string | null;
  observation_timestamp: string | null;
}
export interface FactRevision {
  id: string;
  version: number;
  review_status: VerificationStatus;
  corrected_data: Record<string, unknown> | null;
  reviewer_id: string;
  review_notes: string | null;
  reviewed_at: string;
}
export interface MedicalFactRecord<T> {
  id: string;
  fact_type: 'medication' | 'lab';
  original: T;
  current: T;
  source: FactSource;
  verification_status: VerificationStatus;
  review_version: number;
  verified_by: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  revisions: FactRevision[];
}
export type MedicationFactRecord = MedicalFactRecord<MedicationValue>;
export type LabFactRecord = MedicalFactRecord<LabValue>;
export interface MedicalFactsResponse {
  medications: MedicationFactRecord[];
  labs: LabFactRecord[];
  rejected_medications: MedicationFactRecord[];
  rejected_labs: LabFactRecord[];
  counts: { unverified: number; verified: number; rejected: number };
}
export interface TimelineEntry {
  id: string;
  event_type: string;
  canonical_label: string;
  event_timestamp: string | null;
  date_status: 'known' | 'partial' | 'unknown';
  date_precision: 'datetime' | 'day' | 'month' | 'year' | 'unknown';
  source: FactSource;
  verification_status: VerificationStatus;
}
export interface TimelineResponse {
  known_date: TimelineEntry[];
  unknown_date: TimelineEntry[];
}
export interface DiscrepancySource {
  source_type: 'patient_answer' | 'document_fact';
  source_id: string;
  label: string;
  displayed_value: string;
  document_id: string | null;
  extraction_id: string | null;
  raw_text: string | null;
}
export interface DiscrepancyRecord {
  discrepancy_id: string;
  type:
    | 'MEDICATION_MISMATCH'
    | 'MEDICATION_MISSING_FROM_PATIENT_REPORT'
    | 'ALLERGY_CONFLICT'
    | 'LAB_VALUE_CONFLICT';
  workflow_priority: 'routine_review';
  source_a: DiscrepancySource;
  source_b: DiscrepancySource;
  reason: string;
  status: 'open';
  verification_state: 'requires_clinician_review';
}
export interface DiscrepancyResponse {
  items: DiscrepancyRecord[];
}
export interface PatientEvidenceSearchResult {
  fact_id: string;
  fact_type: 'medication' | 'lab';
  label: string;
  details: Record<string, string | null>;
  verification_status: VerificationStatus;
  patient_confirmation: string;
  source_document_id: string | null;
  source_filename: string | null;
  source_extraction_id: string | null;
  source_text: string | null;
  source_location: string | null;
  score: number;
}
export interface PatientRAGEvidence {
  chunk_id: string;
  text: string;
  source_type: string;
  source_record_id: string;
  session_id: string | null;
  document_id: string | null;
  source_filename: string | null;
  page_number: number | null;
  verification_status: string;
  timestamp: string | null;
  similarity: number;
  score: number;
  clinician_verified: boolean;
  is_current: boolean;
  is_conflicted: boolean;
  provenance: Record<string, unknown>;
  metadata: Record<string, unknown>;
}
export interface PatientEvidenceSearchResponse {
  answer: string;
  evidence: PatientRAGEvidence[];
  patient_id: string;
  query: string;
  intent: string;
  retrieval_strategy: 'patient_scoped_hybrid';
  embedding_provider: string;
  embedding_model: string;
  index_latency_ms: number;
  embedding_latency_ms: number;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  total_latency_ms: number;
  retrieval_mode: 'deterministic_patient_scoped';
  fallback_used: boolean;
  disclaimer: string;
  results: PatientEvidenceSearchResult[];
}
export interface FHIROperationOutcomeIssue {
  severity: 'fatal' | 'error' | 'warning' | 'information';
  code: string;
  diagnostics?: string;
  expression?: string[];
}
export interface FHIROperationOutcome {
  resourceType: 'OperationOutcome';
  id?: string;
  issue: FHIROperationOutcomeIssue[];
}
export interface FHIRBundleEntry {
  fullUrl: string;
  resource: {
    resourceType: string;
    id: string;
    [key: string]: unknown;
  };
}
export interface FHIRBundle {
  resourceType: 'Bundle';
  id: string;
  type: 'document' | 'collection';
  timestamp: string;
  entry: FHIRBundleEntry[];
}
export interface FHIRExportResponse {
  session_id: string;
  bundle_type: string;
  compliance_profile: string;
  generated_at: string;
  resource_counts: Record<string, number>;
  validation: FHIROperationOutcome;
  bundle: FHIRBundle;
}
export interface ABDMProfile {
  abha_number: string;
  abha_address: string;
  name: string;
  gender: string;
  dob: string;
  mobile_masked: string;
  status: string;
}
export interface ABDMVerificationResponse {
  success: boolean;
  profile: ABDMProfile | null;
  message: string;
}
export interface ABDMCareContextLinkResponse {
  success: boolean;
  care_context_reference: string;
  display: string;
  status: string;
  linked_at: string;
  message: string;
}
export interface ABDMStatusResponse {
  session_id: string;
  patient_id: string;
  abha_number: string | null;
  abha_address: string | null;
  abha_status: string;
  care_context_reference: string | null;
  care_context_display: string | null;
  care_context_status: string;
  care_context_linked_at: string | null;
  his_dispatch_status: string;
  his_dispatch_receipt: Record<string, unknown> | null;
  his_dispatched_at: string | null;
  consent_artefact_id: string | null;
}
export interface HISDispatchResponse {
  success: boolean;
  dispatch_id: string;
  target_endpoint: string;
  status: string;
  dispatched_at: string;
  receipt_reference: string;
  message: string;
  attached_bundle_type: string;
}
export interface TranslationResult {
  status: 'success' | 'unavailable';
  source_text: string;
  source_language: string;
  target_language: string;
  translated_text: string | null;
  provider: string;
  model: string | null;
  reason: string | null;
  provenance_note: string;
}
export interface TransliterationResult {
  status: 'success' | 'unavailable';
  source_text: string;
  source_language: string;
  source_type: 'document' | 'patient_answer';
  source_id: string;
  document_id: string | null;
  extraction_id: string | null;
  document_filename: string | null;
  raw_text: string | null;
  source_location: string | null;
}

export interface ABDMProfile {
  abha_number: string;
  abha_address: string;
  name: string;
  gender: string;
  dob: string;
  mobile_masked: string;
  status: string;
}
export interface ABDMVerificationResponse {
  success: boolean;
  profile: ABDMProfile | null;
  message: string;
}
export interface ABDMCareContextLinkResponse {
  success: boolean;
  care_context_reference: string;
  display: string;
  status: string;
  linked_at: string;
  message: string;
}
export interface ABDMStatusResponse {
  session_id: string;
  patient_id: string;
  abha_number: string | null;
  abha_address: string | null;
  abha_status: string;
  care_context_reference: string | null;
  care_context_display: string | null;
  care_context_status: string;
  care_context_linked_at: string | null;
  his_dispatch_status: string;
  his_dispatch_receipt: Record<string, unknown> | null;
  his_dispatched_at: string | null;
  consent_artefact_id: string | null;
}
export interface HISDispatchResponse {
  success: boolean;
  dispatch_id: string;
  target_endpoint: string;
  status: string;
  dispatched_at: string;
  receipt_reference: string;
  message: string;
  attached_bundle_type: string;
}
export interface TranslationResult {
  status: 'success' | 'unavailable';
  source_text: string;
  source_language: string;
  target_language: string;
  translated_text: string | null;
  provider: string;
  model: string | null;
  reason: string | null;
  provenance_note: string;
}
export interface TransliterationResult {
  status: 'success' | 'unavailable';
  source_text: string;
  source_language: string;
  transliterated_text: string | null;
  provider: string;
  reason: string | null;
  provenance_note: string;
}
export interface LanguageIdentificationResult {
  status: 'success' | 'unavailable';
  detected_language: string | null;
  script_code: string | null;
  provider: string;
  reason: string | null;
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

export interface AuthUser {
  id: string;
  name: string;
  role: string;
  phone_number: string | null;
  phone_verified: boolean;
  hospital_id?: string | null;
  hospital_name?: string | null;
  specialty?: string | null;
  specialties?: string[];
  qualification?: string | null;
}

export interface OtpRequestResult {
  success: boolean;
  message: string;
  expires_in: number;
  cooldown_seconds: number;
  delivery_mode: string;
  masked_phone: string;
}

export interface LoginResult {
  success: boolean;
  user: AuthUser;
  token?: string;
}

export interface LogoutResult {
  success: boolean;
  message: string;
}

export interface StaffRegisterPayload {
  name: string;
  role: 'doctor' | 'triage';
  phone_number: string;
  email?: string;
  password: string;
  hospital_id?: string;
  specialty?: string;
  qualification?: string;
}

let activeAuthToken: string | null = null;

export function setAuthToken(token: string | null) {
  activeAuthToken = token;
  if (typeof sessionStorage !== 'undefined') {
    if (token) {
      sessionStorage.setItem('medikiosk.auth_token', token);
    } else {
      sessionStorage.removeItem('medikiosk.auth_token');
    }
  }
}

export function getStoredAuthToken(): string | null {
  if (!activeAuthToken && typeof sessionStorage !== 'undefined') {
    activeAuthToken = sessionStorage.getItem('medikiosk.auth_token');
  }
  return activeAuthToken;
}

const base = import.meta.env.VITE_API_BASE_URL || '/api';

async function request<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  doctor = false,
  externalSignal?: AbortSignal,
  timeoutMs = 60000,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const token = getStoredAuthToken();
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  try {
    const response = await fetch(base + path, {
      method,
      credentials: 'include',
      signal: externalSignal
        ? AbortSignal.any([controller.signal, externalSignal])
        : controller.signal,
      headers: {
        ...(body === undefined || isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(doctor ? { 'X-Demo-Doctor': 'true' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body === undefined ? {} : { body: isFormData ? body : JSON.stringify(body) }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => null);
      throw new ApiError(result?.error?.code || 'REQUEST_FAILED', response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('NETWORK_ERROR', 0);
  } finally {
    window.clearTimeout(timeout);
  }
}
export const api = {
  config: () =>
    request<{
      demo_mode: boolean;
      phase: string;
      languages: Language[];
      normalization_provider: string;
      speech_provider: string;
      ocr_provider: string;
    }>('/config'),
  create: (body: {
    id: string;
    patient: {
      name: string;
      gender: 'female' | 'male' | 'non_binary' | 'other' | 'prefer_not_to_say';
      age_years: number;
      height_cm: number;
      weight_kg: number;
      demo_abha_id: string | null;
    };
    hospital_token: string;
    language: Language;
    journey_mode?: JourneyMode;
    hospital_id?: string;
  }) => request<Session>('/sessions', 'POST', body),
  updateJourneyMode: (id: string, journeyMode: JourneyMode) =>
    request<Session>(`/sessions/${id}/journey-mode`, 'PUT', { journey_mode: journeyMode }),
  hospitals: () => request<{ items: Hospital[] }>('/hospitals'),
  hospitalDoctors: (hospitalId: string) =>
    request<{ items: DoctorRosterItem[] }>(`/hospitals/${encodeURIComponent(hospitalId)}/doctors`),
  selectHospital: (id: string, hospitalId: string) =>
    request<Session>(`/sessions/${id}/hospital`, 'PUT', { hospital_id: hospitalId }),
  matchedDoctors: (id: string) => request<DoctorMatches>(`/sessions/${id}/doctors`),
  selectDoctor: (id: string, doctorId: string) =>
    request<{ session_id: string; hospital_id: string; doctor_id: string }>(
      `/sessions/${id}/doctor`,
      'PUT',
      { doctor_id: doctorId },
    ),
  doctorMatch: (id: string) => request<DoctorMatchResponse>(`/sessions/${id}/doctor-match`),
  selectDoctorMatch: (id: string, doctorId: string) =>
    request<DoctorMatchResponse>(`/sessions/${id}/doctor-match/selection`, 'PUT', {
      doctor_id: doctorId,
    }),
  session: (id: string) => request<Detail>('/sessions/' + id),
  consent: (id: string, agreed: boolean, voiceProcessing = false, documentProcessing = false) =>
    request<Detail['consent']>('/sessions/' + id + '/consent', 'PUT', {
      voice_processing: voiceProcessing,
      document_processing: documentProcessing,
      share_with_doctor: agreed,
    }),
  uploadDocument: (id: string, file: File, documentType?: string) => {
    const data = new FormData();
    data.append('file', file);
    if (documentType) data.append('document_type', documentType);
    return request<DocumentRecord>(
      `/sessions/${id}/documents`,
      'POST',
      data,
      false,
      undefined,
      60000,
    );
  },
  documents: (id: string) =>
    request<{ documents: DocumentRecord[]; total: number }>(
      `/sessions/${id}/documents`,
      'GET',
      undefined,
      true,
      undefined,
      30000,
    ),
  documentDetail: (id: string, documentId: string) =>
    request<DocumentRecord>(`/sessions/${id}/documents/${documentId}`, 'GET', undefined, true),
  documentFile: async (id: string, documentId: string, signal: AbortSignal) => {
    const response = await fetch(`${base}/sessions/${id}/documents/${documentId}/file`, {
      headers: { 'X-Demo-Doctor': 'true' },
      signal,
    });
    if (!response.ok) throw new ApiError('DOCUMENT_DOWNLOAD_FAILED', response.status);
    return response.blob();
  },
  verifyExtraction: (
    id: string,
    documentId: string,
    extractionId: string,
    status: 'verified' | 'rejected',
    expectedStatus: DocumentExtractionRecord['verification_status'],
    expectedVersion: number,
    notes?: string,
  ) =>
    request<DocumentExtractionRecord>(
      `/sessions/${id}/documents/${documentId}/extractions/${extractionId}/verify`,
      'POST',
      { status, expected_status: expectedStatus, expected_version: expectedVersion, notes },
      true,
    ),
  transcribeSpeech: (
    id: string,
    audioBlob: Blob,
    questionId: string,
    fixtureId?: string,
    signal?: AbortSignal,
  ) => {
    const data = new FormData();
    data.append('audio', audioBlob, audioBlob.type === 'audio/wav' ? 'recording.wav' : 'recording');
    data.append('question_id', questionId);
    if (fixtureId) data.append('fixture_id', fixtureId);
    return request<TranscriptionResponse>(
      `/sessions/${id}/interview/speech/transcribe`,
      'POST',
      data,
      false,
      signal,
      30000,
    );
  },
  synthesizeSpeech: (id: string, questionId: string) =>
    request<SpeechSynthesisResponse>(
      `/sessions/${id}/interview/speech/synthesize`,
      'POST',
      { question_id: questionId },
      false,
      undefined,
      30000,
    ),
  answer: (id: string, field: FieldName, value: string, language: Language) =>
    request<Answer>('/sessions/' + id + '/answers', 'POST', {
      question_id: field,
      field,
      value,
      raw_value: value,
      source: 'typed',
      language,
    }),
  interview: (id: string) =>
    request<InterviewState>(`/sessions/${id}/interview`, 'GET', undefined, false, undefined, 60000),
  coverage: (id: string) => request<CoverageResponse>(`/sessions/${id}/coverage`, 'GET'),
  selectFlow: (id: string, flow_id: string) =>
    request<InterviewState>(`/sessions/${id}/interview/flow`, 'PUT', { flow_id }),
  interviewAnswer: (id: string, body: Submission) =>
    request<InterviewState>(
      `/sessions/${id}/interview/answers`,
      'POST',
      body,
      false,
      undefined,
      60000,
    ),
  interviewCursor: (id: string, question_id: string, expected_revision: number) =>
    request<InterviewState>(`/sessions/${id}/interview/cursor`, 'PUT', {
      question_id,
      expected_revision,
    }),
  rapidRouting: (id: string) => request<RapidRoutingState>(`/sessions/${id}/rapid-routing`),
  mapComplaint: (
    id: string,
    body: {
      original_text: string;
      translated_text?: string;
      language: Language;
      source: 'card' | 'typed' | 'voice';
      voice_candidate?: string;
    },
  ) => request<RapidRoutingState>(`/sessions/${id}/rapid-routing/complaint/map`, 'POST', body),
  confirmComplaint: (id: string, category: ComplaintCategory, expected_revision: number) =>
    request<RapidRoutingState>(`/sessions/${id}/rapid-routing/complaint`, 'PUT', {
      category,
      confirmed: true,
      expected_revision,
    }),
  rapidAnswer: (
    id: string,
    body: {
      question_id: string;
      value: boolean | number | string;
      raw_value: string;
      source: 'typed' | 'touch' | 'voice';
      language: Language;
      expected_revision: number;
      voice_candidate?: string;
    },
  ) => request<RapidRoutingState>(`/sessions/${id}/rapid-routing/answers`, 'POST', body),
  routingLocation: (id: string) =>
    request<RoutingLocation | null>(`/sessions/${id}/routing-location`),
  saveRoutingLocation: (
    id: string,
    body: {
      source: string;
      latitude?: number;
      longitude?: number;
      locality?: string;
      postal_code?: string;
      precision?: string;
    },
  ) => request<RoutingLocation>(`/sessions/${id}/routing-location`, 'PUT', body),
  mediroute: (id: string) => request<MediRouteResponse>(`/sessions/${id}/mediroute`),
  selectFacility: (id: string, facility_id: string) =>
    request<Session>(`/sessions/${id}/mediroute/facility`, 'PUT', { facility_id }),
  complete: (id: string) => request<Session>('/sessions/' + id + '/complete', 'POST'),
  queueEstimate: (id: string) =>
    request<PatientQueueEstimate>(`/sessions/${id}/queue-estimate`, 'GET'),
  createPacket: (id: string) => request<PacketMetadata>(`/sessions/${id}/packet`, 'POST'),
  packet: (id: string) => request<PacketView>(`/sessions/${id}/packet`),
  issueHandoffToken: (id: string) =>
    request<HandoffTokenIssued>(`/sessions/${id}/packet/handoff-token`, 'POST'),
  revokePacket: (id: string) => request<PacketMetadata>(`/sessions/${id}/packet/revoke`, 'POST'),
  resolveHandoff: (token: string) =>
    request<PacketView | { status: 'AUTH_REQUIRED' }>(`/handoff/${encodeURIComponent(token)}`),
  sessions: (hospitalId?: string) =>
    request<SessionList>(
      '/doctor/sessions' + (hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : ''),
      'GET',
      undefined,
      true,
    ),
  getDoctorContext: () => request<AuthUser>('/doctor/context', 'GET', undefined, true),
  updateDoctorContext: (payload: Partial<AuthUser>) =>
    request<AuthUser>('/doctor/context', 'PUT', payload, true),
  doctorDetail: (id: string) => request<Detail>('/doctor/sessions/' + id, 'GET', undefined, true),
  updateQueue: (id: string, status: 'CALLED' | 'IN_CONSULTATION' | 'COMPLETED' | 'CANCELLED') =>
    request<{ status: string }>(`/doctor/sessions/${id}/queue`, 'PUT', { status }, true),
  medicalFacts: (id: string) =>
    request<MedicalFactsResponse>(`/doctor/sessions/${id}/medical-facts`, 'GET', undefined, true),
  timeline: (id: string) =>
    request<TimelineResponse>(`/doctor/sessions/${id}/timeline`, 'GET', undefined, true),
  discrepancies: (id: string) =>
    request<DiscrepancyResponse>(`/doctor/sessions/${id}/discrepancies`, 'GET', undefined, true),
  searchPatientEvidence: (id: string, query: string, topK = 5) =>
    request<PatientEvidenceSearchResponse>(
      `/doctor/sessions/${id}/evidence-search`,
      'POST',
      { query, top_k: topK },
      true,
    ),
  reviewMedicationFact: (
    id: string,
    factId: string,
    expectedVersion: number,
    status: 'verified' | 'rejected',
    correction?: Partial<MedicationValue>,
    notes?: string,
  ) =>
    request<MedicationFactRecord>(
      `/doctor/sessions/${id}/medical-facts/medications/${factId}`,
      'PATCH',
      { expected_version: expectedVersion, status, correction, notes },
      true,
    ),
  reviewLabFact: (
    id: string,
    factId: string,
    expectedVersion: number,
    status: 'verified' | 'rejected',
    correction?: Partial<LabValue>,
    notes?: string,
  ) =>
    request<LabFactRecord>(
      `/doctor/sessions/${id}/medical-facts/labs/${factId}`,
      'PATCH',
      { expected_version: expectedVersion, status, correction, notes },
      true,
    ),
  getSummary: (id: string) =>
    request<Summary>('/doctor/sessions/' + id + '/summary', 'GET', undefined, true),
  saveSummary: (
    id: string,
    reviewed_text: string,
    expected_version: number,
    review_notes?: string,
  ) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary',
      'PUT',
      { reviewed_text, expected_version, review_notes },
      true,
    ),
  confirm: (id: string, expected_version: number, review_notes?: string) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary/confirm',
      'POST',
      { expected_version, review_notes },
      true,
    ),
  regenerateSummary: (
    id: string,
    expected_version: number,
    review_notes?: string,
    confirm_replacement?: boolean,
  ) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary/regenerate',
      'POST',
      {
        expected_version,
        review_notes,
        confirm_replacement: Boolean(confirm_replacement),
      },
      true,
    ),
  getSummaryRevisions: (id: string) =>
    request<SummaryRevisionRecord[]>(
      '/doctor/sessions/' + id + '/summary/revisions',
      'GET',
      undefined,
      true,
    ),
  getSummaryEvidence: (id: string) =>
    request<EvidenceReference[]>(
      '/doctor/sessions/' + id + '/summary/evidence',
      'GET',
      undefined,
      true,
    ),
  amendSummary: (id: string, amended_text: string, amendment_notes: string) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary/amend',
      'POST',
      { amended_text, amendment_notes },
      true,
    ),
  getFieldVerifications: (id: string) =>
    request<{ items: FieldVerificationRecord[] }>(
      '/doctor/sessions/' + id + '/field-verifications',
      'GET',
      undefined,
      true,
    ),
  verifyField: (id: string, payload: FieldVerificationRequest) =>
    request<FieldVerificationRecord>(
      '/doctor/sessions/' + id + '/field-verifications',
      'POST',
      payload,
      true,
    ),
  getAuditTrail: (id: string) =>
    request<AuditTrailResponse>('/doctor/sessions/' + id + '/audit-trail', 'GET', undefined, true),
  getCrossReferences: (id: string) =>
    request<CrossReferenceResponse>(
      '/doctor/sessions/' + id + '/cross-references',
      'GET',
      undefined,
      true,
    ),
  getFhirExport: (id: string, bundleType: 'document' | 'collection' = 'document') =>
    request<FHIRExportResponse>(
      '/doctor/sessions/' + id + '/fhir/export?bundle_type=' + bundleType,
      'GET',
      undefined,
      true,
    ),
  getFhirBundle: (id: string, bundleType: 'document' | 'collection' = 'document') =>
    request<FHIRBundle>(
      '/doctor/sessions/' + id + '/fhir/bundle?bundle_type=' + bundleType,
      'GET',
      undefined,
      true,
    ),
  verifyAbha: (abhaInput: string, authMethod = 'mock_otp') =>
    request<ABDMVerificationResponse>('/sessions/verify-abha', 'POST', {
      abha_input: abhaInput,
      auth_method: authMethod,
    }),
  getAbdmStatus: (id: string) =>
    request<ABDMStatusResponse>('/doctor/sessions/' + id + '/abdm/status', 'GET', undefined, true),
  verifyDoctorAbha: (id: string, abhaInput: string, authMethod = 'mock_otp') =>
    request<ABDMVerificationResponse>(
      '/doctor/sessions/' + id + '/abdm/verify-abha',
      'POST',
      { abha_input: abhaInput, auth_method: authMethod },
      true,
    ),
  linkCareContext: (id: string) =>
    request<ABDMCareContextLinkResponse>(
      '/doctor/sessions/' + id + '/abdm/link-care-context',
      'POST',
      {},
      true,
    ),
  dispatchHis: (id: string, targetSystem = 'default') =>
    request<HISDispatchResponse>(
      '/doctor/sessions/' + id + '/his/dispatch',
      'POST',
      { target_system: targetSystem },
      true,
    ),
  getHisStatus: (id: string) =>
    request<{
      session_id: string;
      his_dispatch_status: string;
      his_dispatch_receipt: Record<string, unknown> | null;
      his_dispatched_at: string | null;
    }>('/doctor/sessions/' + id + '/his/status', 'GET', undefined, true),
  seedShowcase: () =>
    request<{
      session_id: string;
      patient_name: string;
      hospital_token: string;
      language: string;
      status: string;
      summary_id: string | null;
      message: string;
    }>('/doctor/demo/seed-showcase', 'POST', {}, true),
  resetDemo: () =>
    request<{
      success: boolean;
      message: string;
    }>('/doctor/demo/reset', 'POST', {}, true),
  translate: (id: string, text: string, sourceLanguage = 'auto', targetLanguage = 'en') =>
    request<TranslationResult>(
      '/doctor/sessions/' + id + '/translate',
      'POST',
      { text, source_language: sourceLanguage, target_language: targetLanguage },
      true,
    ),
  transliterate: (id: string, text: string, sourceLanguage: string, targetLanguage = 'en') =>
    request<TransliterationResult>(
      '/doctor/sessions/' + id + '/transliterate',
      'POST',
      { text, source_language: sourceLanguage, target_language: targetLanguage },
      true,
    ),
  identifyLanguage: (id: string, text: string) =>
    request<LanguageIdentificationResult>(
      '/doctor/sessions/' + id + '/identify-language',
      'POST',
      { text },
      true,
    ),
  requestOtp: (phone: string) =>
    request<OtpRequestResult>('/auth/otp/request', 'POST', { phone_number: phone }),
  verifyOtp: (phone: string, otp: string) =>
    request<LoginResult>('/auth/otp/verify', 'POST', { phone_number: phone, otp }),
  logout: () => request<LogoutResult>('/auth/logout', 'POST'),
  getMe: () => request<AuthUser>('/auth/me'),
  demoLogin: (role = 'patient', hospitalId?: string, specialty?: string) =>
    request<LoginResult>('/auth/demo-login', 'POST', {
      role,
      hospital_id: hospitalId,
      specialty,
    }),
  staffLogin: (identifier: string, password: string, hospitalId?: string, specialty?: string) =>
    request<LoginResult>('/auth/staff-login', 'POST', {
      identifier,
      password,
      hospital_id: hospitalId,
      specialty,
    }),
  staffRegister: (payload: StaffRegisterPayload) =>
    request<LoginResult>('/auth/staff-register', 'POST', payload),
  staffOtpRequest: (phone: string) =>
    request<OtpRequestResult>('/auth/staff-otp/request', 'POST', { phone_number: phone }),
  staffOtpVerify: (phone: string, otp: string) =>
    request<LoginResult>('/auth/staff-otp/verify', 'POST', { phone_number: phone, otp }),
  getDevLastOtp: (phone: string) =>
    request<{ phone_number: string; otp: string }>(
      `/auth/dev/last-otp?phone_number=${encodeURIComponent(phone)}`,
    ),
};
