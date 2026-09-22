import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import CompletionReadiness from '../components/kiosk/CompletionReadiness';
import type { Detail } from '../api/client';

const ready = {
  session: {
    completed_at: '2026-09-21T00:00:00Z',
    hospital_id: 'facility-1',
    selected_doctor_id: 'doctor-1',
  },
  answers: [{ question_id: 'document_confirmation.medication-1' }],
  summary: { id: 'summary-1' },
} as Detail;

it('shows only readiness steps supported by current state', () => {
  const { rerender } = render(<CompletionReadiness record={ready} />);
  expect(screen.getByLabelText('Readiness checklist')).toHaveTextContent('Intake completed');
  expect(screen.getByLabelText('Readiness checklist')).toHaveTextContent('Facility selected');
  expect(screen.getByLabelText('Readiness checklist')).toHaveTextContent('Doctor selected');
  expect(screen.getByLabelText('Readiness checklist')).toHaveTextContent(
    'Prescription information reviewed with you',
  );
  expect(screen.getByLabelText('Readiness checklist')).toHaveTextContent(
    'Clinical history prepared for doctor review',
  );

  rerender(
    <CompletionReadiness
      record={
        {
          ...ready,
          session: { ...ready.session, selected_doctor_id: null },
          answers: [],
          summary: null,
        } as Detail
      }
    />,
  );
  expect(screen.getByLabelText('Readiness checklist')).not.toHaveTextContent('Doctor selected');
  expect(screen.getByLabelText('Readiness checklist')).not.toHaveTextContent(
    'Prescription information reviewed with you',
  );
  expect(screen.getByLabelText('Readiness checklist')).not.toHaveTextContent(
    'Clinical history prepared for doctor review',
  );
});
