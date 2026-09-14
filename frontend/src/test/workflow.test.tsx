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
  vi.mocked(api.interview).mockImplementation(async () => {
    const record = await api.session(id);
    return legacyState(record.answers.length);
  });
  vi.mocked(api.interviewAnswer).mockImplementation(async (_id, submission) =>
    legacyState(questions.findIndex((q) => q.question_id === submission.question_id) + 1),
  );
  vi.mocked(api.complete).mockResolvedValue({ ...detail().session, status: 'ready_for_review' });
  vi.mocked(api.queueEstimate).mockResolvedValue({
    session_id: id,
    doctor_id: 'doctor-1',
    doctor_name: 'Dr. Queue',
    position: 3,
    estimated_wait_minutes: 15,
    expected_meeting_at: '2026-09-09T00:15:00Z',
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
  it('records consent, saves all answers, completes and clears the kiosk', async () => {
    const user = userEvent.setup();
    const initial = { ...detail(), consent: null };
    vi.mocked(api.create).mockResolvedValue(initial.session);
    vi.mocked(api.session).mockResolvedValue(initial);
    vi.mocked(api.consent).mockResolvedValue(detail().consent);
    open('/kiosk/language');
    await user.click(screen.getByRole('button', { name: /English/ }));
    await user.type(screen.getByLabelText('Patient name'), 'Synthetic Patient');
    await fillDemographics(user);
    await user.type(screen.getByLabelText('Hospital token'), 'DEMO-104');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const start = await screen.findByRole('button', { name: 'Start the interview' });
    expect(start).toBeDisabled();
    expect(api.interviewAnswer).not.toHaveBeenCalled();
    await user.click(screen.getByRole('checkbox', { name: /agree to store/i }));
    await user.click(start);
    for (let i = 0; i < questions.length; i++) {
      await screen.findByRole('heading', { name: questions[i].text.en });
      await user.type(screen.getByLabelText('Your answer'), 'Answer ' + i);
      await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    }
    await user.click(await screen.findByRole('button', { name: 'Finish intake' }));
    await screen.findByRole('heading', { name: 'Ready for your doctor' });
    expect(await screen.findByText('15 minutes')).toBeVisible();
    expect(screen.getByText('Estimated total wait time:')).toBeVisible();
    expect(api.interviewAnswer).toHaveBeenCalledTimes(5);
    expect(api.complete).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem('medikiosk.session')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Start a new intake' }));
    await user.click(screen.getByRole('button', { name: /English/ }));
    expect(screen.getByLabelText('Patient name')).toHaveValue('');
    expect(screen.getByLabelText('Hospital token')).toHaveValue('');
  });

  it('explains a temporary wait-time failure and retries the estimate', async () => {
    const completed = {
      ...detail(),
      session: { ...detail().session, status: 'ready_for_review' as const },
    };
    sessionStorage.setItem('medikiosk.session', id);
    vi.mocked(api.session).mockResolvedValue(completed);
    vi.mocked(api.queueEstimate)
      .mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 0))
      .mockResolvedValueOnce({
        session_id: id,
        doctor_id: 'doctor-1',
        doctor_name: 'Dr. Queue',
        position: 2,
        estimated_wait_minutes: 10,
        expected_meeting_at: '2026-09-09T00:10:00Z',
      });

    open('/kiosk/complete');
    expect(await screen.findByText(/wait-time estimate could not be loaded/i)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('10 minutes')).toBeVisible();
    expect(api.queueEstimate).toHaveBeenCalledTimes(2);
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
    await waitFor(() => expect(screen.getAllByRole('textbox')).toHaveLength(3));
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
    fireEvent.change(screen.getByLabelText('Hospital token'), { target: { value: 'DEMO-104' } });
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
