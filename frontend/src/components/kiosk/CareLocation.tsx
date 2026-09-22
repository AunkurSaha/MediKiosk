import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { MediRouteResponse } from '../../api/client';

const facilityReasonLabel: Record<string, string> = {
  ACTIVE_FACILITY: 'Facility passed eligibility checks',
  REQUIRED_CAPABILITY_AVAILABLE: 'Required clinical capability available',
  ELIGIBLE_DOCTOR_AVAILABLE: 'An eligible doctor is available at this facility',
  EMERGENCY_CAPABLE: 'Emergency care capability available',
  OPEN: 'Available for this visit',
  CLOSER_ELIGIBLE_OPTION: 'Matches the selected location and distance criteria',
};

export default function CareLocation({
  sessionId,
  onSelected,
}: {
  sessionId: string;
  onSelected: (emergency: boolean) => void;
}) {
  const [locality, setLocality] = useState('');
  const [postal, setPostal] = useState('');
  const [result, setResult] = useState<MediRouteResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const emergency = result?.routing_state === 'EMERGENCY';

  useEffect(() => {
    api
      .routingLocation(sessionId)
      .then((location) => {
        if (location) {
          setLocality(location.locality || '');
          setPostal(location.postal_code || '');
          return api.mediroute(sessionId).then(setResult);
        }
      })
      .catch(() => undefined);
  }, [sessionId]);

  async function save(body: Parameters<typeof api.saveRoutingLocation>[1]) {
    setBusy(true);
    setError('');
    try {
      await api.saveRoutingLocation(sessionId, body);
      setResult(await api.mediroute(sessionId));
      setSelectedIndex(0);
    } catch {
      setError('Location or facility recommendations could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  function browserLocation() {
    if (!navigator.geolocation) {
      setError('Browser location is unavailable. Enter a locality or PIN.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        void save({
          source: 'BROWSER_GEOLOCATION',
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          precision: 'browser',
        }),
      () => setError('Location permission was denied. Enter a locality or PIN instead.'),
    );
  }

  if (result) {
    const carePathway = result.required_specialty.replaceAll('_', ' ');
    const selectedArea = locality || postal;
    return (
      <>
        {emergency && (
          <p className="kiosk-safety-advisory emergency" role="alert">
            Potential emergency symptoms detected. Immediate clinical assessment recommended.
          </p>
        )}
        <h1>{emergency ? 'Suitable emergency-capable facilities' : 'Recommended facilities'}</h1>
        {selectedArea && <p className="muted">Selected search area: {selectedArea}</p>}
        {result.status === 'NO_ELIGIBLE_FACILITY' ? (
          <p role="alert">
            No eligible facility in the current demo directory is available for the required care
            pathway. Clinical requirements were not relaxed.
          </p>
        ) : (
          result.recommendations.slice(0, 3).map((item, index) => (
            <article className="saved-answer facility-card" key={item.facility_id}>
              {index === selectedIndex && (
                <p className="eyebrow">Recommended for this care pathway</p>
              )}
              <h2>{item.facility_name}</h2>
              <ul className="match-highlights" aria-label={`Reasons for ${item.facility_name}`}>
                {item.eligibility_reasons.includes('REQUIRED_SPECIALTY_AVAILABLE') && (
                  <li>✓ {carePathway} available</li>
                )}
                {item.ranking_reasons.includes('OPEN') && <li>✓ Available for this visit</li>}
                {item.ranking_reasons.includes('CLOSER_ELIGIBLE_OPTION') && selectedArea && (
                  <li>✓ Matches your search near {selectedArea}</li>
                )}
              </ul>
              {item.distance_km != null && (
                <p>Approx. straight-line distance: {item.distance_km.toFixed(1)} km</p>
              )}
              <p>{item.capabilities.join(' · ')}</p>
              <details className="match-explanation">
                <summary>Why this facility?</summary>
                <div className="match-explanation-body">
                  <p className="eyebrow">Your need</p>
                  <p>
                    {emergency ? 'Immediate clinical assessment' : 'Routine clinical assessment'}
                  </p>
                  <p className="eyebrow">Care required</p>
                  <p>{carePathway}</p>
                  <p className="eyebrow">Matched facility</p>
                  <p>{item.facility_name}</p>
                  <p className="eyebrow">Why it qualified</p>
                  <ul>
                    {item.eligibility_reasons.includes('REQUIRED_SPECIALTY_AVAILABLE') && (
                      <li>✓ Required specialty is available</li>
                    )}
                    {item.eligibility_reasons.includes('ACTIVE_FACILITY') && (
                      <li>✓ {facilityReasonLabel.ACTIVE_FACILITY}</li>
                    )}
                    {[...item.eligibility_reasons, ...item.ranking_reasons]
                      .filter(
                        (reason) =>
                          reason !== 'ACTIVE_FACILITY' &&
                          reason !== 'REQUIRED_SPECIALTY_AVAILABLE' &&
                          facilityReasonLabel[reason],
                      )
                      .map((reason) => (
                        <li key={reason}>✓ {facilityReasonLabel[reason]}</li>
                      ))}
                  </ul>
                </div>
              </details>
              <button
                disabled={busy}
                onClick={() =>
                  void api
                    .selectFacility(sessionId, item.facility_id)
                    .then(() => onSelected(emergency))
                    .catch(() => setError('Facility selection failed.'))
                }
              >
                Select facility
              </button>
              {index === selectedIndex && result.recommendations.slice(0, 3).length > 1 && (
                <div className="actions">
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      setSelectedIndex(
                        (current) => (current + 1) % result.recommendations.slice(0, 3).length,
                      )
                    }
                  >
                    See next option
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => setResult(null)}
                  >
                    Change search
                  </button>
                </div>
              )}
            </article>
          ))
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </>
    );
  }

  return (
    <>
      <p className="eyebrow">Find care</p>
      <h1>Where would you like us to search for care?</h1>
      <p className="muted">Use your device location or search by locality or PIN.</p>
      <div className="location-choice-grid">
        <section className="location-choice-card">
          <span className="location-choice-icon" aria-hidden="true">
            ⌖
          </span>
          <h2>Use my location</h2>
          <p>Allow this browser to share your current coordinates for this search.</p>
          <button disabled={busy} onClick={browserLocation}>
            Use my current location
          </button>
        </section>
        <section className="location-choice-card">
          <span className="location-choice-icon" aria-hidden="true">
            ⌕
          </span>
          <h2>Search an area</h2>
          <label htmlFor="care-locality">Locality</label>
          <div className="field-action-row">
            <input
              id="care-locality"
              value={locality}
              onChange={(event) => setLocality(event.target.value)}
              placeholder="For example, Kolkata"
            />
            <button
              disabled={busy || !locality.trim()}
              onClick={() => void save({ source: 'MANUAL_LOCALITY', locality: locality.trim() })}
            >
              Search by locality
            </button>
          </div>
          <label htmlFor="care-postal">PIN code</label>
          <div className="field-action-row">
            <input
              id="care-postal"
              value={postal}
              onChange={(event) => setPostal(event.target.value)}
              inputMode="numeric"
            />
            <button
              disabled={busy || !postal.trim()}
              onClick={() =>
                void save({ source: 'MANUAL_POSTAL_CODE', postal_code: postal.trim() })
              }
            >
              Search by PIN
            </button>
          </div>
        </section>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
