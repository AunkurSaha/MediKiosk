import type {
  AnswerValue,
  ClinicalHistory,
  InterviewState,
  SpeechSynthesisResponse,
  Submission,
  TranscriptionResponse,
} from './interview';
export type Language = 'en' | 'bn' | 'hi';
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
  demo_abha_id: string | null;
}
export interface Summary {
  id: string;
  session_id?: string;
  generated_text: string;
  reviewed_text: string | null;
  status: 'generated' | 'reviewed' | 'confirmed';
  version: number;
  confirmed_by: string | null;
  confirmed_at: string | null;
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
  items: (Session & { patient_name: string })[];
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
export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}
const base = import.meta.env.VITE_API_BASE_URL || '/api';

async function request<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  doctor = false,
  externalSignal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  try {
    const response = await fetch(base + path, {
      method,
      signal: externalSignal
        ? AbortSignal.any([controller.signal, externalSignal])
        : controller.signal,
      headers: {
        ...(body === undefined || isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(doctor ? { 'X-Demo-Doctor': 'true' } : {}),
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
  config: () => request<{ demo_mode: boolean }>('/config'),
  create: (body: {
    id: string;
    patient: { name: string; demo_abha_id: string | null };
    hospital_token: string;
    language: Language;
  }) => request<Session>('/sessions', 'POST', body),
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
    return request<DocumentRecord>(`/sessions/${id}/documents`, 'POST', data);
  },
  documents: (id: string) =>
    request<{ documents: DocumentRecord[]; total: number }>(
      `/sessions/${id}/documents`,
      'GET',
      undefined,
      true,
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
    data.append('audio', audioBlob, 'recording.webm');
    data.append('question_id', questionId);
    if (fixtureId) data.append('fixture_id', fixtureId);
    return request<TranscriptionResponse>(
      `/sessions/${id}/interview/speech/transcribe`,
      'POST',
      data,
      false,
      signal,
    );
  },
  synthesizeSpeech: (id: string, questionId: string) =>
    request<SpeechSynthesisResponse>(`/sessions/${id}/interview/speech/synthesize`, 'POST', {
      question_id: questionId,
    }),
  answer: (id: string, field: FieldName, value: string, language: Language) =>
    request<Answer>('/sessions/' + id + '/answers', 'POST', {
      question_id: field,
      field,
      value,
      raw_value: value,
      source: 'typed',
      language,
    }),
  interview: (id: string) => request<InterviewState>(`/sessions/${id}/interview`),
  selectFlow: (id: string, flow_id: string) =>
    request<InterviewState>(`/sessions/${id}/interview/flow`, 'PUT', { flow_id }),
  interviewAnswer: (id: string, body: Submission) =>
    request<InterviewState>(`/sessions/${id}/interview/answers`, 'POST', body),
  interviewCursor: (id: string, question_id: string, expected_revision: number) =>
    request<InterviewState>(`/sessions/${id}/interview/cursor`, 'PUT', {
      question_id,
      expected_revision,
    }),
  complete: (id: string) => request<Session>('/sessions/' + id + '/complete', 'POST'),
  sessions: () => request<SessionList>('/doctor/sessions', 'GET', undefined, true),
  doctorDetail: (id: string) => request<Detail>('/doctor/sessions/' + id, 'GET', undefined, true),
  medicalFacts: (id: string) =>
    request<MedicalFactsResponse>(`/doctor/sessions/${id}/medical-facts`, 'GET', undefined, true),
  timeline: (id: string) =>
    request<TimelineResponse>(`/doctor/sessions/${id}/timeline`, 'GET', undefined, true),
  discrepancies: (id: string) =>
    request<DiscrepancyResponse>(`/doctor/sessions/${id}/discrepancies`, 'GET', undefined, true),
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
  saveSummary: (id: string, reviewed_text: string, expected_version: number) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary',
      'PUT',
      { reviewed_text, expected_version },
      true,
    ),
  confirm: (id: string, expected_version: number) =>
    request<Summary>(
      '/doctor/sessions/' + id + '/summary/confirm',
      'POST',
      { expected_version },
      true,
    ),
};
