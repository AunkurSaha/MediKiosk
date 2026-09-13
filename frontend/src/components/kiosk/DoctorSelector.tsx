import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { DoctorMatches } from '../../api/client';
import { errorText } from '../../i18n';

export default function DoctorSelector({
  sessionId,
  onSelected,
}: {
  sessionId: string;
  onSelected: (doctorId: string) => void;
}) {
  const [matches, setMatches] = useState<DoctorMatches | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    api
      .matchedDoctors(sessionId)
      .then((result) => active && setMatches(result))
      .catch((err) => active && setError(err));
    return () => {
      active = false;
    };
  }, [sessionId, attempt]);
  if (error)
    return (
      <div className="error" role="alert">
        <p>{errorText(error)}</p>
        <button
          className="secondary"
          onClick={() => {
            setError(null);
            setMatches(null);
            setAttempt((value) => value + 1);
          }}
        >
          Retry
        </button>
      </div>
    );
  if (!matches) return <p role="status">Finding available doctors…</p>;
  if (!matches.items.length)
    return (
      <div className="card empty">
        <h2>No suitable doctor is currently available at this hospital.</h2>
        <p>Please contact the hospital help desk or registration desk.</p>
        <button className="secondary" onClick={() => setAttempt((value) => value + 1)}>
          Refresh
        </button>
      </div>
    );
  return (
    <section aria-labelledby="choose-doctor-title">
      <h1 id="choose-doctor-title">Choose your doctor</h1>
      <p className="muted">
        Suitable for: {matches.specialty_codes.join(', ').replaceAll('_', ' ')}
      </p>
      {matches.fallback_used && (
        <p className="notice">
          No exact-specialty doctor is available. Showing the configured clinical service fallback.
        </p>
      )}
      <div className="language-grid" data-testid="doctor-match-list">
        {matches.items.map((doctor) => (
          <article
            className="language-card"
            key={doctor.doctor_id}
            data-testid={`doctor-${doctor.doctor_id}`}
          >
            <h2>{doctor.name}</h2>
            <p>{doctor.matched_specialty.replaceAll('_', ' ')}</p>
            {doctor.qualification && <p className="muted">{doctor.qualification}</p>}
            <p>
              {doctor.waiting_count} {doctor.waiting_count === 1 ? 'patient' : 'patients'} waiting
            </p>
            {doctor.recommended && <strong>★ Recommended — shortest queue</strong>}
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await api.selectDoctor(sessionId, doctor.doctor_id);
                  onSelected(doctor.doctor_id);
                } catch (err) {
                  setError(err);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Choose
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
