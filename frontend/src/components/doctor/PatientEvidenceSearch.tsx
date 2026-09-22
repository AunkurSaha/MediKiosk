import { useState } from 'react';
import { api, type PatientEvidenceSearchResponse } from '../../api/client';

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
    <section className="card" aria-label="Patient document evidence search">
      <p className="eyebrow">Patient-scoped retrieval</p>
      <h2>Document Evidence Search</h2>
      <p className="muted">
        Searches persisted facts from this patient&apos;s uploaded documents. It does not diagnose
        or recommend treatment.
      </p>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <input
          aria-label="Evidence search query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ flex: '1 1 320px' }}
        />
        <button type="button" onClick={search} disabled={loading || query.trim().length < 2}>
          {loading ? 'Searching…' : 'Search evidence'}
        </button>
      </div>
      {error && <p className="error">Evidence search is temporarily unavailable.</p>}
      {response && (
        <div data-testid="patient-evidence-results" style={{ marginTop: '16px' }}>
          <p className="muted">
            Deterministic fallback · real persisted sources · {response.results.length} result(s)
          </p>
          {response.results.length === 0 && <p>No matching evidence was found for this patient.</p>}
          {response.results.map((result) => (
            <article key={result.fact_id} className="notice" style={{ marginTop: '10px' }}>
              <strong>{result.label}</strong>
              <dl>
                {Object.entries(result.details).map(([key, value]) =>
                  value ? (
                    <div key={key}>
                      <dt>{key.replaceAll('_', ' ')}</dt>
                      <dd>{value}</dd>
                    </div>
                  ) : null,
                )}
              </dl>
              <p>
                <strong>Source:</strong> {result.source_filename || 'Persisted clinical record'}
                {result.source_location ? ` · ${result.source_location}` : ''}
              </p>
              <p>
                <strong>Patient confirmation:</strong> {result.patient_confirmation}
              </p>
              <p className="muted">{result.verification_status.replaceAll('_', ' ')}</p>
            </article>
          ))}
          <p className="muted">{response.disclaimer}</p>
        </div>
      )}
    </section>
  );
}
