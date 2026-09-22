import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { DoctorMatchResponse } from '../../api/client';
import { errorText } from '../../i18n';

const reasonLabel: Record<string, string> = {
  FACILITY_MATCH: 'Works at the selected facility',
  ACTIVE: 'Active clinician listing',
  ACCEPTING_PATIENTS: 'Accepting patients',
  CONSULTATION_TYPE_MATCH: 'Supports this consultation type',
  SPECIALTY_MATCH: 'Specialty matches the required care',
  RELEVANT_EXPERTISE: 'Relevant expertise for the reported concern',
  AVAILABLE_FOR_CONSULTATION: 'Available for consultation',
  LANGUAGE_MATCH: 'Speaks your selected language',
  EXPERIENCE_RELEVANT: 'Relevant clinical experience',
  CONTINUITY_RELEVANT: 'Previously involved in your confirmed care',
};

export default function DoctorRecommendations({
  sessionId,
  onSelected,
  onChooseFacility,
}: {
  sessionId: string;
  onSelected: (doctorId: string) => void;
  onChooseFacility: () => void;
}) {
  const [match, setMatch] = useState<DoctorMatchResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .doctorMatch(sessionId)
      .then((result) => {
        if (!active) return;
        setMatch(result);
        if (result.status === 'COMPLETED' && result.selected_doctor_id)
          onSelected(result.selected_doctor_id);
      })
      .catch(() => {
        if (active) setError('Doctor recommendations could not be loaded.');
      });
    return () => {
      active = false;
    };
  }, [sessionId, onSelected]);

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  if (!match) return <p role="status">Finding clinically suitable doctors…</p>;
  if (match.status === 'DOCTOR_MATCHING_BYPASSED_EMERGENCY') {
    return (
      <div className="kiosk-safety-advisory emergency" role="alert">
        <h1>Immediate clinical assessment recommended</h1>
        <p>
          Normal doctor matching is not used for emergency routing. Please proceed with the selected
          emergency-capable facility.
        </p>
      </div>
    );
  }
  if (match.status === 'NO_ELIGIBLE_DOCTOR') {
    return (
      <div className="card empty">
        <h1>No suitable doctor is currently available at this facility.</h1>
        <p>No specialty requirement was relaxed. Choose another recommended facility.</p>
        <button onClick={onChooseFacility}>View next recommended facility</button>
      </div>
    );
  }
  return (
    <section aria-labelledby="doctor-recommendations-title">
      <h1 id="doctor-recommendations-title">Choose a clinically suitable doctor</h1>
      <p>
        Recommended specialty: <strong>{match.required_specialty.replaceAll('_', ' ')}</strong>
      </p>
      <div className="doctor-card-grid">
        {match.recommendations.slice(0, 3).map((doctor) => (
          <article
            className={`doctor-match-card${doctor.recommended ? ' recommended' : ''}`}
            key={doctor.doctor_id}
          >
            {doctor.recommended && <span className="recommended-label">Recommended</span>}
            <h2>{doctor.name}</h2>
            <p className="doctor-specialty">{doctor.primary_specialty.replaceAll('_', ' ')}</p>
            {doctor.qualification && <p>{doctor.qualification}</p>}
            <p>
              Availability: <strong>{doctor.availability_status.replaceAll('_', ' ')}</strong>
            </p>
            <p>Experience: {doctor.years_of_experience} years</p>
            <p>Languages: {doctor.languages.join(', ') || 'Not listed'}</p>
            <details className="match-explanation">
              <summary>Why this match?</summary>
              <div className="match-explanation-body">
                <p className="eyebrow">Eligibility</p>
                <ul>
                  {doctor.eligibility_reasons
                    .filter((reason) => reasonLabel[reason])
                    .map((reason) => (
                      <li key={reason}>✓ {reasonLabel[reason]}</li>
                    ))}
                </ul>
                {doctor.ranking_reasons.some((reason) => reasonLabel[reason]) && (
                  <>
                    <p className="eyebrow">Ranking factors</p>
                    <ul>
                      {doctor.ranking_reasons
                        .filter((reason) => reasonLabel[reason])
                        .map((reason) => (
                          <li key={reason}>• {reasonLabel[reason]}</li>
                        ))}
                    </ul>
                  </>
                )}
              </div>
            </details>
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError('');
                try {
                  await api.selectDoctorMatch(sessionId, doctor.doctor_id);
                  onSelected(doctor.doctor_id);
                } catch (err) {
                  setError(`Doctor selection could not be saved. ${errorText(err)}`);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Select Doctor
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
