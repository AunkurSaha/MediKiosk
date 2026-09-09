import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, ApiError } from '../api/client';
import type { InterviewState, Question } from '../api/interview';
import Interview from '../components/kiosk/Interview';
import QuestionRenderer from '../components/kiosk/QuestionRenderer';
import { legacyState } from './legacy-fixture';

vi.mock('../api/client', async (original) => {
  const actual = await original<typeof import('../api/client')>();
  return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map((k) => [k, vi.fn()])) };
});
const label = { en: 'Prototype question', bn: 'নমুনা প্রশ্ন', hi: 'नमूना प्रश्न' };
function question(type: Question['type']): Question {
  return {
    question_id: 'example.parent',
    field: 'example.parent',
    type,
    text: label,
    required: true,
    allow_unknown: true,
    constraints: { minimum: 0, maximum: 10, max_length: 100, integer: type === 'severity' },
    options: [
      { value: 'a', label: { en: 'Choice A', bn: 'বিকল্প ক', hi: 'विकल्प क' }, exclusive: false },
      { value: 'b', label: { en: 'Choice B', bn: 'বিকল্প খ', hi: 'विकल्प ख' }, exclusive: false },
      { value: 'none', label: { en: 'None', bn: 'কোনোটিই নয়', hi: 'कोई नहीं' }, exclusive: true },
    ],
  };
}
beforeEach(() => {
  vi.resetAllMocks();
});

it.each([
  'short_text',
  'number',
  'duration',
  'severity',
  'boolean',
  'single_choice',
  'multiple_choice',
] as const)('renders and submits %s with typed values', (type) => {
  const save = vi.fn();
  render(
    <QuestionRenderer
      question={question(type)}
      initial={null}
      language="en"
      busy={false}
      onSave={save}
    />,
  );
  if (type === 'short_text')
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: '  My words  ' } });
  else if (['number', 'severity', 'duration'].includes(type))
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: '3' } });
  else if (type === 'boolean') fireEvent.click(screen.getByLabelText('No'));
  else fireEvent.click(screen.getByLabelText('Choice A'));
  if (type === 'multiple_choice') fireEvent.click(screen.getByLabelText('Choice B'));
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  const expected = {
    short_text: '  My words  ',
    number: 3,
    severity: 3,
    duration: { amount: 3, unit: 'days' },
    boolean: false,
    single_choice: 'a',
    multiple_choice: ['a', 'b'],
  };
  expect(save).toHaveBeenCalledWith(
    expect.objectContaining({ value: expected[type], status: 'answered' }),
  );
});

it('requires a real boolean choice and validates numeric bounds', () => {
  const save = vi.fn();
  const { rerender } = render(
    <QuestionRenderer
      question={question('boolean')}
      initial={null}
      language="en"
      busy={false}
      onSave={save}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  expect(screen.getByRole('alert')).toBeVisible();
  expect(save).not.toHaveBeenCalled();
  rerender(
    <QuestionRenderer
      key="number"
      question={question('severity')}
      initial={null}
      language="en"
      busy={false}
      onSave={save}
    />,
  );
  fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: '11' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  expect(save).not.toHaveBeenCalled();
});

it('separates unknown, not reported and optional skipping from negative answers', () => {
  const save = vi.fn();
  const { rerender } = render(
    <QuestionRenderer
      question={question('boolean')}
      initial={null}
      language="en"
      busy={false}
      onSave={save}
    />,
  );
  expect(screen.queryByText('Skip optional question')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Unknown' }));
  expect(save).toHaveBeenLastCalledWith({
    value: null,
    status: 'unknown',
    raw_value: 'Unknown',
    source: 'touch',
  });
  fireEvent.click(screen.getByRole('button', { name: 'Prefer not to report' }));
  expect(save).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: 'not_reported', value: null }),
  );
  rerender(
    <QuestionRenderer
      question={{ ...question('short_text'), required: false }}
      initial={null}
      language="en"
      busy={false}
      onSave={save}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Skip optional question' }));
  expect(save).toHaveBeenLastCalledWith(
    expect.objectContaining({ status: 'skipped', value: null }),
  );
});

it('handles exclusive multiple-choice options without contradictory selections', () => {
  render(
    <QuestionRenderer
      question={question('multiple_choice')}
      initial={null}
      language="en"
      busy={false}
      onSave={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByLabelText('Choice A'));
  fireEvent.click(screen.getByLabelText('None'));
  expect(screen.getByLabelText('Choice A')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Choice B'));
  expect(screen.getByLabelText('None')).not.toBeChecked();
});

it.each(['en', 'bn', 'hi'] as const)(
  'renders server translations with the same question ID in %s',
  (language) => {
    render(
      <QuestionRenderer
        question={question('boolean')}
        initial={null}
        language={language}
        busy={false}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: label[language] })).toBeVisible();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
  },
);

it('shows loading, offers recovery after a failed load, and keeps AYUSH separate', async () => {
  let reject!: (reason: unknown) => void;
  vi.mocked(api.interview).mockReturnValueOnce(
    new Promise((_, failure) => {
      reject = failure;
    }),
  );
  const selection: InterviewState = {
    ...legacyState(),
    question: null,
    flow_id: null,
    selection_required: true,
    flows: [
      { flow_id: 'standard.example', namespace: 'standard', version: '1.0.0', label },
      {
        flow_id: 'ayush_demo.history',
        namespace: 'ayush_demo',
        version: '1.0.0',
        label: { en: 'AYUSH example', bn: 'AYUSH', hi: 'AYUSH' },
      },
    ],
  };
  vi.mocked(api.interview).mockResolvedValueOnce(selection);
  vi.mocked(api.selectFlow).mockResolvedValue({ ...legacyState(), question: question('boolean') });
  render(<Interview sessionId="session" language="en" onComplete={vi.fn()} />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading');
  reject(new ApiError('NETWORK_ERROR', 0));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Reload saved interview' }));
  await screen.findByRole('heading', { name: 'Choose your main concern' });
  expect(screen.getByRole('heading', { name: 'AYUSH demonstration only' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: label.en }));
  await screen.findByRole('heading', { name: label.en });
  expect(api.selectFlow).toHaveBeenCalledWith('session', 'standard.example');
});

it('retains input and reuses the exact request ID after a lost save response', async () => {
  vi.mocked(api.interview).mockResolvedValue({
    ...legacyState(),
    question: question('short_text'),
  });
  vi.mocked(api.interviewAnswer)
    .mockRejectedValueOnce(new ApiError('NETWORK_ERROR', 0))
    .mockResolvedValueOnce(legacyState(1));
  render(<Interview sessionId="session" language="en" onComplete={vi.fn()} />);
  const input = await screen.findByLabelText('Your answer');
  fireEvent.change(input, { target: { value: 'Original words' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  await screen.findByRole('alert');
  expect(input).toHaveValue('Original words');
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  await waitFor(() => expect(api.interviewAnswer).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.interviewAnswer).mock.calls[0][1]).toEqual(
    vi.mocked(api.interviewAnswer).mock.calls[1][1],
  );
});

it('uses server navigation and branch recalculation after editing an earlier answer', async () => {
  const parent = question('boolean');
  const child = {
    ...question('short_text'),
    question_id: 'example.child',
    text: { ...label, en: 'Dependent question' },
  };
  const childState = {
    ...legacyState(1),
    question: child,
    previous_question_id: parent.question_id,
  };
  vi.mocked(api.interview).mockResolvedValue(childState);
  vi.mocked(api.interviewCursor).mockResolvedValue({
    ...legacyState(),
    revision: 2,
    question: parent,
  });
  vi.mocked(api.interviewAnswer).mockResolvedValue({
    ...legacyState(5),
    revision: 3,
    inactive_question_ids: [child.question_id],
  });
  render(<Interview sessionId="session" language="en" onComplete={vi.fn()} />);
  await screen.findByRole('heading', { name: 'Dependent question' });
  fireEvent.click(screen.getByRole('button', { name: 'Back' }));
  await screen.findByRole('heading', { name: label.en });
  expect(api.interviewCursor).toHaveBeenCalledWith('session', parent.question_id, 1);
  fireEvent.click(screen.getByLabelText('No'));
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  await screen.findByRole('heading', { name: 'Check your saved answers' });
  expect(screen.queryByRole('heading', { name: 'Dependent question' })).not.toBeInTheDocument();
});

it('blocks stale submission until the user reloads and retains review on completion failure', async () => {
  vi.mocked(api.interview)
    .mockResolvedValueOnce(legacyState())
    .mockResolvedValueOnce(legacyState(5));
  vi.mocked(api.interviewAnswer).mockRejectedValue(new ApiError('INTERVIEW_CONFLICT', 409));
  const complete = vi
    .fn()
    .mockRejectedValueOnce(new ApiError('DATABASE_UNAVAILABLE', 503))
    .mockResolvedValueOnce(undefined);
  render(<Interview sessionId="session" language="en" onComplete={complete} />);
  fireEvent.change(await screen.findByLabelText('Your answer'), {
    target: { value: 'Stale words' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: 'Save and continue' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Reload saved interview' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Finish intake' }));
  await screen.findByRole('alert');
  expect(screen.getByRole('heading', { name: 'Check your saved answers' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Finish intake' }));
  await waitFor(() => expect(complete).toHaveBeenCalledTimes(2));
});
