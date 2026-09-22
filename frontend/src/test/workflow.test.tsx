import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { api, ApiError } from '../api/client';
import type { Answer, Detail } from '../api/client';
import { questions, legacyState } from './legacy-fixture';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    api: Object.fromEntries(Object.keys(actual.api).map((key) => [key, vi.fn()])),
  };
});
const id = '11111111-1111-4111-8111-111111111111';
function detail(): Detail {
  return {
    session: {
      id,
      patient_id: 'patient',
      hospital_id: 'hospital-1',
      selected_doctor_id: 'doctor-1',
      hospital_token: 'DEMO-104',
      language: 'en',
      status: 'intake',
      created_at: '2026-09-09T00:00:00Z',
      completed_at: null,
    },
    patient: {
      id: 'patient',
      name: 'Synthetic Patient',
      gender: null,
      age_years: null,
      height_cm: null,
      weight_kg: null,
      demo_abha_id: null,
    },
    consent: { share_with_doctor: true, voice_processing: false, document_processing: false },
    answers: [],
    summary: null,
  };
}
function answered(field = questions[0].field, value = 'Synthetic answer'): Answer {
  return {
    id: 'answer-' + field,
    session_id: id,
    question_id: field,
    field,
    value,
    raw_value: value,
    source: 'typed',
    language: 'en',
    verification_status: 'patient_reported',
  };
}
function open(path: string) {
  window.history.replaceState({}, '', path);
  render(<App />);
}
async function fillDemographics(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText('Gender'), 'female');
  await user.type(screen.getByLabelText('Age (years)'), '34');
  await user.type(screen.getByLabelText('Height (cm)'), '165');
  await user.type(screen.getByLabelText('Weight (kg)'), '62');
}
beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem(
    'medikiosk.auth_user',
    JSON.stringify({
      id: 'demo-patient-0001',
      name: 'Demo Patient',
      role: 'patient',
      phone_number: '+919999999999',
      phone_verified: true,
    }),
  );
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.mocked(api.session).mockResolvedValue(detail());
  vi.mocked(api.createPacket).mockResolvedValue({
    packet_id: 'packet-1',
    session_id: id,
    packet_version: '1.0',
    status: 'ACTIVE',
    created_at: '2026-09-09T00:00:00Z',
    expires_at: '2026-09-10T00:00:00Z',
  });
  vi.mocked(api.interview).mockImplementation(async () => {
    const record = await api.session(id);
    return legacyState(record.answers.length);
  });
  vi.mocked(api.interviewAnswer).mockImplementation(async (_id, submission) =>
    legacyState(questions.findIndex((q) => q.question_id === submission.question_id) + 1),
  );
  vi.mocked(api.rapidRouting).mockResolvedValue({
    phase: 'result',
    revision: 1,
    questions_asked: [],
    questions_skipped: [],
    result: {
      id: 'routing-1',
      session_id: id,
      chief_complaint: 'FEVER',
      routing_state: 'ROUTINE_OPD',
      suggested_specialty: 'GENERAL_MEDICINE',
      triggered_red_flags: [],
      supporting_evidence_ids: [],
      questions_asked: [],
      questions_skipped: [],
      completed_at: '2026-09-09T00:00:00Z',
      routing_protocol_version: '1.0.0',
    },
  });
  vi.mocked(api.routingLocation).mockResolvedValue({
    id: 'location-1',
    session_id: id,
    patient_id: 'patient',
    source: 'MANUAL_LOCALITY',
    latitude: null,
    longitude: null,
    locality: 'Kolkata',
    postal_code: null,
    precision: null,
    revision: 1,
    captured_at: '2026-09-09T00:00:00Z',
  });
  vi.mocked(api.mediroute).mockResolvedValue({
    id: 'mediroute-1',
    session_id: id,
    clinical_routing_result_id: 'routing-1',
    status: 'COMPLETED',
    routing_state: 'ROUTINE_OPD',
    suggested_specialty: 'GENERAL_MEDICINE',
    directory_version: 'demo_facilities_v1',
    protocol_version: '1.0.0',
    required_specialty: 'GENERAL_MEDICINE',
    required_capabilities: [],
    preferred_capabilities: ['LAB'],
    generated_at: '2026-09-09T00:00:00Z',
    recommendations: [
      {
        facility_id: 'hospital-1',
        facility_name: 'MediKiosk City Hospital',
        rank: 1,
        distance_km: null,
        eligibility_reasons: ['REQUIRED_SPECIALTY_AVAILABLE'],
        ranking_reasons: ['OPEN'],
        capabilities: ['GENERAL_MEDICINE'],
        emergency_available: true,
      },
    ],
  });
  vi.mocked(api.selectFacility).mockResolvedValue(detail().session);
  vi.mocked(api.doctorMatch).mockResolvedValue({
    id: 'doctor-match-1',
    session_id: id,
    facility_id: 'hospital-1',
    required_specialty: 'GENERAL_MEDICINE',
    directory_version: 'demo_doctors_v1',
    protocol_version: '1.0.0',
    status: 'COMPLETED',
    selected_doctor_id: null,
    generated_at: '2026-09-09T00:00:00Z',
    recommendations: [
      {
        doctor_id: 'doctor-1',
        name: 'Dr. Demo',
        qualification: 'MD',
        primary_specialty: 'GENERAL_MEDICINE',
        expertise_tags: ['FEVER'],
        languages: ['en'],
        availability_status: 'AVAILABLE',
        years_of_experience: 10,
        rank: 1,
        recommended: true,
        eligibility_reasons: ['SPECIALTY_MATCH'],
        ranking_reasons: ['RELEVANT_EXPERTISE', 'AVAILABLE_FOR_CONSULTATION'],
      },
    ],
  });
  vi.mocked(api.selectDoctorMatch).mockImplementation(async () => ({
    ...(await api.doctorMatch(id)),
    selected_doctor_id: 'doctor-1',
  }));
  vi.mocked(api.complete).mockResolvedValue({ ...detail().session, status: 'ready_for_review' });
  vi.mocked(api.queueEstimate).mockResolvedValue({
    session_id: id,
    doctor_id: 'doctor-1',
    doctor_name: 'Dr. Queue',
    hospital_id: 'hospital-1',
    hospital_name: 'Synthetic Hospital',
    service_date: '2026-09-09',
    visit_token: 'MK-GENE-003',
    status: 'WAITING',
    position: 3,
    patients_ahead: 2,
    estimated_wait_minutes: 24,
    is_estimate: true,
    calculation_basis: '2 patients ahead × 12 min average consultation',
    policy_version: '1.0',
  });
  vi.mocked(api.medicalFacts).mockResolvedValue({
    medications: [],
    labs: [],
    rejected_medications: [],
    rejected_labs: [],
    counts: { unverified: 0, verified: 0, rejected: 0 },
  });
  vi.mocked(api.timeline).mockResolvedValue({ known_date: [], unknown_date: [] });
  vi.mocked(api.discrepancies).mockResolvedValue({ items: [] });
  vi.mocked(api.getAuditTrail).mockResolvedValue({ session_id: id, total: 0, items: [] });
  vi.mocked(api.getCrossReferences).mockResolvedValue({
    session_id: id,
    documents: [],
    statement_cross_references: {},
  });
  vi.mocked(api.getFieldVerifications).mockResolvedValue({ items: [] });
});
describe('Patient intake', () => {
  it('records consent, completes, and retains the queue reservation for reload', async () => {
    const user = userEvent.setup();
    const initial = { ...detail(), consent: null };
    vi.mocked(api.create).mockResolvedValue(initial.session);
    vi.mocked(api.session).mockResolvedValue(initial);
    vi.mocked(api.consent).mockResolvedValue(detail().consent);
    open('/kiosk/language');
    await user.click(screen.getByRole('button', { name: /English/ }));
    await user.click(screen.getByRole('button', { name: /Planning my visit/ }));
    await user.type(screen.getByLabelText('Patient name'), 'Synthetic Patient');
    await fillDemographics(user);
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const start = await screen.findByRole('button', { name: 'Start the interview' });
    expect(start).toBeDisabled();
    expect(api.interviewAnswer).not.toHaveBeenCalled();
    await user.click(screen.getByRole('checkbox', { name: /agree to store/i }));
    await user.click(start);
    await user.click(await screen.findByRole('button', { name: 'Find a suitable facility' }));
    await user.click(await screen.findByRole('button', { name: 'Select facility' }));
    await user.click(await screen.findByRole('button', { name: 'Select Doctor' }));
    for (let i = 0; i < questions.length; i++) {
      await screen.findByRole('heading', { name: questions[i].text.en });
      await user.type(screen.getByLabelText('Your answer'), 'Answer ' + i);
      await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    }
    await user.click(await screen.findByRole('button', { name: 'Finish intake' }));
    await screen.findByRole('heading', { name: 'Your pre-consultation intake is ready' });
    expect(await screen.findByText(/MK-GENE-003/)).toBeVisible();
    expect(screen.getByLabelText('Visit queue reservation')).toHaveTextContent('WAITING');
    expect(screen.getByLabelText('Visit queue reservation')).toHaveTextContent('24 minutes');
    expect(api.interviewAnswer).toHaveBeenCalledTimes(5);
    expect(api.complete).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem('medikiosk.session')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Start a new intake' }));
    await user.click(screen.getByRole('button', { name: /English/ }));
    await user.click(screen.getByRole('button', { name: /Planning my visit/ }));
    expect(screen.getByLabelText('Patient name')).toHaveValue('');
    expect(screen.getByText(/No hospital token is needed/i)).toBeVisible();
  });

  it('restores the same queue reservation on completed-intake reload', async () => {
    const completed = {
      ...detail(),
      session: { ...detail().session, status: 'ready_for_review' as const },
    };
    sessionStorage.setItem('medikiosk.session', id);
    vi.mocked(api.session).mockResolvedValue(completed);
    open('/kiosk/complete');
    expect(
      await screen.findByRole('heading', { name: 'Your pre-consultation intake is ready' }),
    ).toBeVisible();
    expect(await screen.findByText(/MK-GENE-003/)).toBeVisible();
    expect(api.queueEstimate).toHaveBeenCalledWith(id);
  });

  it('resumes the retained session at the first missing question without creating a patient', async () => {
    sessionStorage.setItem('medikiosk.session', id);
    vi.mocked(api.session).mockResolvedValue({ ...detail(), answers: [answered()] });
    open('/kiosk/interview');
    await screen.findByRole('heading', { name: questions[1].text.en });
    expect(api.create).not.toHaveBeenCalled();
    expect(api.session).toHaveBeenCalledWith(id);
  });

  it('keeps the current answer on failed save and retries before advancing', async () => {
    sessionStorage.setItem('medikiosk.session', id);
    vi.mocked(api.interviewAnswer)
      .mockRejectedValueOnce(new ApiError('DATABASE_UNAVAILABLE', 503))
      .mockResolvedValueOnce(legacyState(1));
    open('/kiosk/interview');
    const input = await screen.findByLabelText('Your answer');
    fireEvent.change(input, { target: { value: 'Patient wording' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await screen.findByRole('alert');
    expect(input).toHaveValue('Patient wording');
    expect(screen.getByRole('heading', { name: questions[0].text.en })).toBeInTheDocument();
    expect(api.complete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await screen.findByRole('heading', { name: questions[1].text.en });
  });

  it('does not submit blank answers or skip consent through a direct URL', async () => {
    sessionStorage.setItem('medikiosk.session', id);
    vi.mocked(api.session).mockResolvedValue({ ...detail(), consent: null });
    open('/kiosk/interview');
    expect(await screen.findByRole('button', { name: 'Start the interview' })).toBeDisabled();
    expect(api.interviewAnswer).not.toHaveBeenCalled();
  });

  it('requires an explicit answer instead of inventing a default', async () => {
    sessionStorage.setItem('medikiosk.session', id);
    open('/kiosk/interview');
    await screen.findByLabelText('Your answer');
    fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await screen.findByRole('alert');
    expect(api.interviewAnswer).not.toHaveBeenCalled();
  });

  it.each(['বাংলা', 'हिन्दी'])('offers localized identification for %s', async (language) => {
    open('/kiosk/language');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(language) }));
    fireEvent.click(screen.getByRole('button', { name: /Planning my visit/ }));
    await waitFor(() => expect(screen.getAllByRole('textbox')).toHaveLength(2));
    expect(screen.queryByLabelText('Patient name')).not.toBeInTheDocument();
  });

  it('retries identification with the same id after a lost response', async () => {
    vi.mocked(api.create)
      .mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 0))
      .mockResolvedValue(detail().session);
    vi.mocked(api.session).mockResolvedValue({ ...detail(), consent: null });
    open('/kiosk/identify');
    fireEvent.change(screen.getByLabelText('Patient name'), { target: { value: 'Synthetic' } });
    fireEvent.change(screen.getByLabelText('Gender'), { target: { value: 'male' } });
    fireEvent.change(screen.getByLabelText('Age (years)'), { target: { value: '41' } });
    fireEvent.change(screen.getByLabelText('Height (cm)'), { target: { value: '178' } });
    fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '79' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByRole('button', { name: 'Start the interview' });
    expect(vi.mocked(api.create).mock.calls[0][0].id).toBe(
      vi.mocked(api.create).mock.calls[1][0].id,
    );
  });
});

describe('Doctor review', () => {
  beforeEach(() => {
    sessionStorage.setItem(
      'medikiosk.auth_user',
      JSON.stringify({
        id: '00000000-0000-4000-8000-000000000001',
        name: 'Demo Doctor',
        role: 'doctor',
        phone_number: null,
        phone_verified: false,
      }),
    );
  });

  function reviewDetail(): Detail {
    return {
      ...detail(),
      session: { ...detail().session, status: 'ready_for_review' },
      answers: [answered()],
      summary: {
        id: 'summary',
        generated_text: 'Original patient-reported draft',
        reviewed_text: null,
        status: 'generated',
        version: 1,
        confirmed_at: null,
        confirmed_by: null,
      },
    };
  }
  it('requires a saved review, confirms it and preserves the original draft', async () => {
    const result = reviewDetail();
    const saved = {
      ...result.summary!,
      reviewed_text: 'Doctor reviewed text',
      status: 'reviewed' as const,
      version: 2,
    };
    vi.mocked(api.doctorDetail).mockResolvedValue(result);
    vi.mocked(api.saveSummary).mockResolvedValue(saved);
    vi.mocked(api.confirm).mockResolvedValue({
      ...saved,
      status: 'confirmed',
      confirmed_by: 'demo-doctor',
      confirmed_at: '2026-09-09T00:00:00Z',
    });
    open('/doctor/sessions/' + id);
    const editor = await screen.findByLabelText('Reviewed summary');
    expect(screen.getByRole('button', { name: 'Confirm reviewed record' })).toBeDisabled();
    fireEvent.change(editor, { target: { value: 'Doctor reviewed text' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save review' }));
    await screen.findByText('Review saved.');
    expect(api.saveSummary).toHaveBeenCalledWith(id, 'Doctor reviewed text', 1);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reviewed record' }));
    await screen.findByText('Record confirmed.');
    expect(editor).toHaveAttribute('readonly');
    expect(screen.getByText('Original patient-reported draft')).toBeInTheDocument();
    expect(api.confirm).toHaveBeenCalledWith(id, 2);
  });

  it('keeps edits and shows a version conflict without claiming success', async () => {
    vi.mocked(api.doctorDetail).mockResolvedValue(reviewDetail());
    vi.mocked(api.saveSummary).mockRejectedValue(new ApiError('VERSION_CONFLICT', 409));
    open('/doctor/sessions/' + id);
    const editor = await screen.findByLabelText('Reviewed summary');
    fireEvent.change(editor, { target: { value: 'Unsaved changes' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save review' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Another edit was saved');
    expect(editor).toHaveValue('Unsaved changes');
    expect(screen.queryByText('Review saved.')).not.toBeInTheDocument();
    expect(api.confirm).not.toHaveBeenCalled();
  });
});
