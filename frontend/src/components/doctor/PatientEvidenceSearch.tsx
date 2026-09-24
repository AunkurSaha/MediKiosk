import { useState } from 'react';
import { api, type PatientEvidenceSearchResponse } from '../../api/client';

const quickActions = [
  'Current medications',
  'Allergies',
  'Recent labs',
  'Uploaded documents',
  'Conflicts',
  'Timeline',
];

 function provenanceRows(item: PatientEvidenceSearchResponse['evidence'][number]) {
   const candidates = [
     ['Canonical record', item.source_record_id],
     ['Document', item.document_id],
     ['Document extraction', item.provenance.document_extraction_id],
     ['Original document evidence', item.metadata.document_evidence_id],
     ['Confirmation source', item.provenance.source_id],
     ['Extractor', item.provenance.extractor],
     ['Extractor version', item.provenance.extractor_version],
     ['OCR confidence', item.provenance.ocr_confidence],
   ] as const;

   const rows: [string, string][] = [];
   for (const [label, value] of candidates) {
     if (value !== null && value !== undefined) {
       rows.push([label, String(value)]);
     }
   }
   return rows;
 }

export default function PatientEvidenceSearch({ sessionId }: { sessionId: string }) {
  const [query, setQuery] = useState('Show medication evidence');
  const [response, setResponse] = useState<PatientEvidenceSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function search() {
    setLoading(true);
    setError(false);
    try {
      setResponse(await api.searchPatientEvidence(sessionId, query));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card" aria-label="Patient clinical evidence search">
      <p className="eyebrow">Patient-scoped retrieval</p>
      <h2>Clinical Evidence Search</h2>
      <p className="muted">
        Searches this patient&apos;s persisted interviews, evidence, documents, facts, history, and
        summaries. It does not diagnose or recommend treatment.
      </p>
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
        {quickActions.map((action) => (
          <button
            key={action}
            type="button"
            className="text-button"
            onClick={() => setQuery(action)}
          >
            {action}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <input
          aria-label="Evidence search query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ flex: '1 1 320px' }}
        />
        <button type="button" onClick={search} disabled={loading || query.trim().length < 2}>
          {loading ? 'Searchingâ€¦' : 'Search evidence'}
        </button>
      </div>
      {error && <p className="error">Evidence search is temporarily unavailable.</p>}
      {response && (
        <div data-testid="patient-evidence-results" style={{ marginTop: '16px' }}>
          <p className="notice" aria-live="polite">
            {response.answer}
          </p>
          <p className="muted">
            Patient-scoped hybrid retrieval Â· {response.evidence.length} source(s)
          </p>
          {response.evidence.length > 0 && <h3>Supporting Evidence</h3>}
          {response.evidence.map((item) => (
            <article key={item.chunk_id} className="notice" style={{ marginTop: '10px' }}>
              <strong>{item.source_type.replaceAll('_', ' ')}</strong>
              <p style={{ whiteSpace: 'pre-line' }}>{item.text}</p>
              <p>
                <strong>Source:</strong> {item.source_filename || 'Persisted clinical record'}
                {item.page_number ? ` Â· page ${item.page_number}` : ''}
              </p>
              <p>
                <strong>Verification:</strong> {item.verification_status.replaceAll('_', ' ')}
                {item.is_conflicted ? ' Â· Potential conflict' : ''}
              </p>
              <details>
                <summary>Why is this here?</summary>
                <dl>
                  {provenanceRows(item).map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                  {item.timestamp && (
                    <div>
                      <dt>Recorded</dt>
                      <dd>{new Date(item.timestamp).toLocaleString()}</dd>
                    </div>
                  )}
                </dl>
              </details>
            </article>
          ))}
          <p className="muted">{response.disclaimer}</p>
        </div>
      )}
    </section>
  );
}
