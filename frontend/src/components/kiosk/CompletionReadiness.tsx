import type { Detail } from '../../api/client';

export default function CompletionReadiness({ record }: { record: Detail }) {
  return (
    <div className="card completion-readiness" aria-label="Readiness checklist">
      <h2>Ready for your visit</h2>
      <ul>
        {record.session.completed_at && <li>✓ Intake completed</li>}
        {record.session.hospital_id && <li>✓ Facility selected</li>}
        {record.session.selected_doctor_id && <li>✓ Doctor selected</li>}
        {record.answers.some((answer) =>
          answer.question_id.startsWith('document_confirmation.'),
        ) && <li>✓ Prescription information reviewed with you</li>}
        {record.summary && <li>✓ Clinical history prepared for doctor review</li>}
      </ul>
    </div>
  );
}
