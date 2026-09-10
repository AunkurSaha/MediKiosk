import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../../api/client';
import type {
  DiscrepancyRecord,
  LabFactRecord,
  LabValue,
  MedicalFactsResponse,
  MedicationFactRecord,
  MedicationValue,
  TimelineEntry,
  TimelineResponse,
} from '../../api/client';

type Evidence = {
  facts: MedicalFactsResponse;
  timeline: TimelineResponse;
  discrepancies: { items: DiscrepancyRecord[] };
};

function sourceBadge(source: { document_filename: string | null; source_type: string }) {
  return source.document_filename || source.source_type.replace('_', ' ');
}

function SourceReference({ source }: { source: MedicationFactRecord['source'] }) {
  return (
    <div className="fact-source">
      <span className="source-badge">Source: {sourceBadge(source)}</span>
      {source.document_id && <a href="#document-viewer-panel">View source document</a>}
      {source.source_location && <span>{source.source_location}</span>}
      {source.raw_text && (
        <details>
          <summary>Raw source</summary>
          <pre className="raw-ocr-text">{source.raw_text}</pre>
        </details>
      )}
    </div>
  );
}

function statusLabel(status: string) {
  return status === 'unverified'
    ? 'Needs verification'
    : status === 'verified'
      ? 'Verified'
      : 'Rejected';
}

function valueOrUnknown(value: string | null) {
  return value || 'Not reported';
}

function MedicationFactCard({
  sessionId,
  fact,
  locked,
  onSaved,
}: {
  sessionId: string;
  fact: MedicationFactRecord;
  locked: boolean;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<MedicationValue>(fact.current);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function review(status: 'verified' | 'rejected') {
    setBusy(true);
    setError('');
    try {
      const correction =
        status === 'verified' && JSON.stringify(draft) !== JSON.stringify(fact.current)
          ? draft
          : undefined;
      await api.reviewMedicationFact(
        sessionId,
        fact.id,
        fact.review_version,
        status,
        correction,
        notes || undefined,
      );
      setEditing(false);
      setNotes('');
      await onSaved();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === 'FACT_VERSION_CONFLICT'
          ? 'This fact changed. Reload and review again.'
          : 'Fact review could not be saved.',
      );
    } finally {
      setBusy(false);
    }
  }
  const fields: Array<[keyof MedicationValue, string]> = [
    ['name', 'Medication'],
    ['dosage', 'Dosage'],
    ['unit', 'Unit'],
    ['route', 'Route'],
    ['frequency', 'Frequency'],
    ['duration', 'Duration'],
  ];
  return (
    <article className={`medical-fact-card status-${fact.verification_status}`}>
      <div className="fact-heading">
        <h4>{fact.current.name}</h4>
        <span className={`verification-tag status-${fact.verification_status}`}>
          {statusLabel(fact.verification_status)}
        </span>
      </div>
      {editing ? (
        <div className="fact-edit-grid">
          {fields.map(([field, label]) => (
            <label key={field}>
              {label}
              <input
                value={draft[field] || ''}
                onChange={(event) => setDraft({ ...draft, [field]: event.target.value || null })}
              />
            </label>
          ))}
        </div>
      ) : (
        <dl className="fact-values">
          {fields.slice(1).map(([field, label]) => (
            <div key={field}>
              <dt>{label}</dt>
              <dd>{valueOrUnknown(draft[field])}</dd>
            </div>
          ))}
        </dl>
      )}
      {fact.revisions.length > 0 && (
        <p className="fact-history-note">
          Original extraction retained · Review version {fact.review_version}
        </p>
      )}
      <SourceReference source={fact.source} />
      {!locked && fact.verification_status !== 'rejected' && (
        <div className="fact-review-controls">
          <label>
            Review notes
            <input value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <div className="actions">
            <button className="secondary" type="button" onClick={() => setEditing(!editing)}>
              {editing ? 'Cancel correction' : 'Correct fields'}
            </button>
            <button type="button" disabled={busy} onClick={() => void review('verified')}>
              Verify{editing ? ' and save correction' : ''}
            </button>
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={() => void review('rejected')}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </article>
  );
}

function LabFactCard({
  sessionId,
  fact,
  locked,
  onSaved,
}: {
  sessionId: string;
  fact: LabFactRecord;
  locked: boolean;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LabValue>(fact.current);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function review(status: 'verified' | 'rejected') {
    setBusy(true);
    setError('');
    try {
      const correction =
        status === 'verified' && JSON.stringify(draft) !== JSON.stringify(fact.current)
          ? draft
          : undefined;
      await api.reviewLabFact(
        sessionId,
        fact.id,
        fact.review_version,
        status,
        correction,
        notes || undefined,
      );
      setEditing(false);
      setNotes('');
      await onSaved();
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === 'FACT_VERSION_CONFLICT'
          ? 'This fact changed. Reload and review again.'
          : 'Fact review could not be saved.',
      );
    } finally {
      setBusy(false);
    }
  }
  const fields: Array<[keyof LabValue, string]> = [
    ['test_name', 'Test'],
    ['value', 'Value'],
    ['unit', 'Unit'],
    ['reference_range', 'Reference range'],
    ['flag', 'Source flag'],
  ];
  return (
    <article className={`medical-fact-card status-${fact.verification_status}`}>
      <div className="fact-heading">
        <h4>{fact.current.test_name}</h4>
        <span className={`verification-tag status-${fact.verification_status}`}>
          {statusLabel(fact.verification_status)}
        </span>
      </div>
      {editing ? (
        <div className="fact-edit-grid">
          {fields.map(([field, label]) => (
            <label key={field}>
              {label}
              <input
                value={draft[field] || ''}
                onChange={(event) => setDraft({ ...draft, [field]: event.target.value || null })}
              />
            </label>
          ))}
        </div>
      ) : (
        <dl className="fact-values">
          {fields.slice(1).map(([field, label]) => (
            <div key={field}>
              <dt>{label}</dt>
              <dd>{valueOrUnknown(draft[field])}</dd>
            </div>
          ))}
        </dl>
      )}
      {fact.revisions.length > 0 && (
        <p className="fact-history-note">
          Original extraction retained · Review version {fact.review_version}
        </p>
      )}
      <SourceReference source={fact.source} />
      {!locked && fact.verification_status !== 'rejected' && (
        <div className="fact-review-controls">
          <label>
            Review notes
            <input value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <div className="actions">
            <button className="secondary" type="button" onClick={() => setEditing(!editing)}>
              {editing ? 'Cancel correction' : 'Correct fields'}
            </button>
            <button type="button" disabled={busy} onClick={() => void review('verified')}>
              Verify{editing ? ' and save correction' : ''}
            </button>
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={() => void review('rejected')}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </article>
  );
}

function timelineIcon(eventType: string) {
  const t = eventType.toLowerCase();
  if (t.includes('medication')) return '💊';
  if (t.includes('lab')) return '🧪';
  if (t.includes('interview') || t.includes('patient')) return '🗣️';
  if (t.includes('vital')) return '💓';
  return '📋';
}

function TimelineList({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="timeline-list">
      {entries.map((entry) => (
        <li key={entry.id}>
          <div
            className="timeline-marker"
            aria-hidden="true"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            <span style={{ fontSize: '10px' }}>{timelineIcon(entry.event_type)}</span>
          </div>
          <div>
            <div className="fact-heading">
              <strong>{entry.canonical_label}</strong>
              <span className="source-badge">{sourceBadge(entry.source)}</span>
            </div>
            <p className="muted">
              {entry.event_timestamp
                ? new Date(entry.event_timestamp).toLocaleDateString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : 'Date not reported'}{' '}
              ·{' '}
              <span style={{ textTransform: 'capitalize' }}>
                {entry.event_type.replaceAll('_', ' ')}
              </span>{' '}
              · Status: {statusLabel(entry.verification_status)}
            </p>
            {entry.source.raw_text && (
              <details>
                <summary>Source reference</summary>
                <pre className="raw-ocr-text">{entry.source.raw_text}</pre>
              </details>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function DiscrepancyCard({ item }: { item: DiscrepancyRecord }) {
  return (
    <article className="discrepancy-card">
      <p className="eyebrow">{item.type.replaceAll('_', ' ')}</p>
      <h4>Possible discrepancy — requires clinician review.</h4>
      <p>{item.reason}</p>
      <div className="discrepancy-sides">
        {[item.source_a, item.source_b].map((source) => (
          <div key={source.source_id}>
            <strong>{source.label}</strong>
            <p>{source.displayed_value}</p>
            <span className="source-badge">{source.source_type.replace('_', ' ')}</span>
            {source.document_id && <a href="#document-viewer-panel">View source document</a>}
          </div>
        ))}
      </div>
    </article>
  );
}

export default function ClinicalEvidencePanel({
  sessionId,
  locked,
}: {
  sessionId: string;
  locked: boolean;
}) {
  const [data, setData] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const fetchEvidence = useCallback(async () => {
    const [facts, timeline, discrepancies] = await Promise.all([
      api.medicalFacts(sessionId),
      api.timeline(sessionId),
      api.discrepancies(sessionId),
    ]);
    return { facts, timeline, discrepancies };
  }, [sessionId]);
  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await fetchEvidence());
    } catch {
      setError('Clinical facts, timeline, and discrepancies could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [fetchEvidence]);
  useEffect(() => {
    let active = true;
    fetchEvidence()
      .then((result) => {
        if (active) setData(result);
      })
      .catch(() => {
        if (active) setError('Clinical facts, timeline, and discrepancies could not be loaded.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [fetchEvidence]);
  if (loading)
    return (
      <section className="card evidence-panel">
        <p role="status">Loading clinical evidence…</p>
      </section>
    );
  if (error)
    return (
      <section className="card evidence-panel">
        <p role="alert" className="error">
          {error}
        </p>
        <button type="button" onClick={() => void refresh()}>
          Retry
        </button>
      </section>
    );
  if (!data) return null;
  const activeFacts = data.facts.medications.length + data.facts.labs.length;
  return (
    <div className="clinical-evidence-stack">
      <section className="card evidence-panel" aria-labelledby="medical-facts-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Source-linked evidence</p>
            <h2 id="medical-facts-heading">Medical facts</h2>
          </div>
          <span className="source-badge">{data.facts.counts.unverified} need verification</span>
        </div>
        {activeFacts === 0 && (
          <p className="muted">No active medication or lab facts are available.</p>
        )}
        {data.facts.medications.length > 0 && (
          <>
            <h3>Medications</h3>
            <div className="medical-facts-grid">
              {data.facts.medications.map((fact) => (
                <MedicationFactCard
                  key={fact.id}
                  sessionId={sessionId}
                  fact={fact}
                  locked={locked}
                  onSaved={refresh}
                />
              ))}
            </div>
          </>
        )}
        {data.facts.labs.length > 0 && (
          <>
            <h3>Laboratory observations</h3>
            <div className="medical-facts-grid">
              {data.facts.labs.map((fact) => (
                <LabFactCard
                  key={fact.id}
                  sessionId={sessionId}
                  fact={fact}
                  locked={locked}
                  onSaved={refresh}
                />
              ))}
            </div>
          </>
        )}
        {data.facts.counts.rejected > 0 && (
          <details>
            <summary>Rejected facts ({data.facts.counts.rejected})</summary>
            <p className="muted">
              Rejected facts remain in review history and are excluded from the active timeline and
              discrepancy checks.
            </p>
            <div className="medical-facts-grid rejected-facts-grid">
              {data.facts.rejected_medications.map((fact) => (
                <MedicationFactCard
                  key={fact.id}
                  sessionId={sessionId}
                  fact={fact}
                  locked={true}
                  onSaved={refresh}
                />
              ))}
              {data.facts.rejected_labs.map((fact) => (
                <LabFactCard
                  key={fact.id}
                  sessionId={sessionId}
                  fact={fact}
                  locked={true}
                  onSaved={refresh}
                />
              ))}
            </div>
          </details>
        )}
      </section>
      <section className="card evidence-panel" aria-labelledby="timeline-heading">
        <p className="eyebrow">Computed from explicit source dates</p>
        <h2 id="timeline-heading">Timeline</h2>
        {data.timeline.known_date.length === 0 ? (
          <p className="muted">No known-date clinical events are available.</p>
        ) : (
          <TimelineList entries={data.timeline.known_date} />
        )}
        <h3>Unknown date</h3>
        {data.timeline.unknown_date.length === 0 ? (
          <p className="muted">No unknown-date events.</p>
        ) : (
          <TimelineList entries={data.timeline.unknown_date} />
        )}
      </section>
      <section className="card evidence-panel" aria-labelledby="discrepancies-heading">
        <p className="eyebrow">Deterministic comparison</p>
        <h2 id="discrepancies-heading">Discrepancies</h2>
        {data.discrepancies.items.length === 0 ? (
          <p className="muted">
            No comparable discrepancies were found. Missing evidence is not treated as agreement.
          </p>
        ) : (
          <div className="discrepancy-list">
            {data.discrepancies.items.map((item) => (
              <DiscrepancyCard key={item.discrepancy_id} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
