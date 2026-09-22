import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { CoverageResponse } from '../../api/interview';

const labels = {
  CONFIRMED: 'Confirmed',
  DOCUMENT_SUPPORTED_UNCONFIRMED: 'Document-supported · needs patient confirmation',
  CONFLICTED: 'Needs clarification',
  MISSING: 'Missing',
  NOT_APPLICABLE: 'Not applicable',
};

export default function ClinicalCoveragePanel({ sessionId }: { sessionId: string }) {
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    if (typeof api.coverage !== 'function') {
      return () => {
        active = false;
      };
    }
    const request = api.coverage(sessionId);
    Promise.resolve(request)
      .then((result) => {
        if (!result) throw new Error('Coverage unavailable');
        if (active) setCoverage(result);
      })
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [sessionId]);
  if (failed) {
    return (
      <section className="card">
        <h2>Clinical coverage</h2>
        <p>Coverage could not be loaded.</p>
      </section>
    );
  }
  if (!coverage)
    return (
      <section className="card" role="status">
        Loading clinical coverage…
      </section>
    );
  const relevant = coverage.fields.filter((field) => field.state !== 'NOT_APPLICABLE');
  return (
    <section className="card" aria-label="Clinical coverage">
      <h2>Clinical coverage</h2>
      <p>
        <strong>
          {coverage.confirmed} / {coverage.required}
        </strong>{' '}
        required areas confirmed
      </p>
      <p className="coverage-summary">
        Confirmed: {coverage.confirmed} · Document-supported:{' '}
        {coverage.document_supported_unconfirmed} · Needs clarification: {coverage.conflicted} ·
        Missing: {coverage.missing}
      </p>
      <ul>
        {relevant.map((field) => (
          <li key={field.field}>
            <strong>{field.label}</strong> — {labels[field.state]}
            {field.provenance.map((source) => (
              <div className="muted" key={source.evidence_id}>
                {source.original_extracted_value && (
                  <span>{source.original_extracted_value}. </span>
                )}
                Source: {source.document_filename || 'uploaded document'}
                {source.page_number ? `, page ${source.page_number}` : ''}. Evidence status:{' '}
                {source.verification_state.replaceAll('_', ' ').toLowerCase()}.
                {field.patient_answer_id && ' Patient confirmation recorded separately.'}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}
