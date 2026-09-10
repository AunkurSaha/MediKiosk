import { useEffect, useState } from 'react';
import type { FC } from 'react';
import { api } from '../../api/client';
import type { AuditTrailItem } from '../../api/client';

interface Props {
  sessionId: string;
}

export const AuditTrailViewer: FC<Props> = ({ sessionId }) => {
  const [events, setEvents] = useState<AuditTrailItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterActor, setFilterActor] = useState<string>('all');

  useEffect(() => {
    let active = true;
    const promise = api.getAuditTrail?.(sessionId);
    if (promise && typeof promise.then === 'function') {
      promise
        .then((res) => {
          if (active) {
            setEvents(res?.items || []);
            setLoading(false);
          }
        })
        .catch((err: unknown) => {
          if (active) {
            setError(err instanceof Error ? err.message : 'Failed to load audit trail');
            setLoading(false);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [sessionId]);

  const filteredEvents = events.filter((ev) => {
    if (filterActor === 'all') return true;
    return ev.actor_type.toLowerCase() === filterActor.toLowerCase();
  });

  const getActorBadgeColor = (actor: string) => {
    switch (actor.toLowerCase()) {
      case 'doctor':
        return { bg: '#dbeafe', color: '#1e40af' };
      case 'patient':
        return { bg: '#dcfce7', color: '#166534' };
      default:
        return { bg: '#f1f5f9', color: '#475569' };
    }
  };

  return (
    <section
      className="card audit-trail-section"
      data-testid="audit-trail-viewer"
      style={{ marginTop: '20px' }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '14px',
          borderBottom: '1px solid #e2e8f0',
          paddingBottom: '10px',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#1e293b' }}>
            📜 Session Audit Trail ({events.length})
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: '0.8rem', color: '#64748b' }}>
            Immutable chronological record of all patient, staff, and system events
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label htmlFor="audit-filter-select" style={{ fontSize: '0.8rem', color: '#475569' }}>
            Filter Actor:
          </label>
          <select
            id="audit-filter-select"
            value={filterActor}
            onChange={(e) => setFilterActor(e.target.value)}
            style={{
              padding: '4px 8px',
              borderRadius: '4px',
              border: '1px solid #cbd5e1',
              fontSize: '0.8rem',
            }}
          >
            <option value="all">All Actors</option>
            <option value="doctor">Doctor Only</option>
            <option value="patient">Patient Only</option>
            <option value="system">System Only</option>
          </select>
        </div>
      </div>

      {loading && <p style={{ fontSize: '0.85rem', color: '#64748b' }}>Loading audit events...</p>}
      {error && <p style={{ fontSize: '0.85rem', color: '#b91c1c' }}>{error}</p>}

      {!loading && !error && filteredEvents.length === 0 && (
        <p style={{ fontSize: '0.85rem', color: '#64748b' }}>No audit events found.</p>
      )}

      {!loading && !error && filteredEvents.length > 0 && (
        <div
          className="audit-timeline-list"
          style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}
        >
          {filteredEvents.map((ev) => {
            const actorStyle = getActorBadgeColor(ev.actor_type);
            return (
              <div
                key={ev.id}
                className="audit-item card"
                style={{
                  padding: '10px 14px',
                  borderRadius: '6px',
                  border: '1px solid #e2e8f0',
                  backgroundColor: '#ffffff',
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: '8px',
                  fontSize: '0.85rem',
                }}
              >
                <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      gap: '8px',
                      marginBottom: '4px',
                    }}
                  >
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        backgroundColor: actorStyle.bg,
                        color: actorStyle.color,
                        textTransform: 'uppercase',
                      }}
                    >
                      {ev.actor_type}
                    </span>
                    <strong style={{ color: '#0f172a' }}>{ev.action.replace(/_/g, ' ')}</strong>
                    <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                      (Entity: {ev.entity_type})
                    </span>
                  </div>

                  {ev.metadata && Object.keys(ev.metadata).length > 0 && (
                    <div
                      style={{
                        fontSize: '0.75rem',
                        color: '#334155',
                        backgroundColor: '#f8fafc',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        marginTop: '4px',
                        display: 'inline-block',
                        maxWidth: '100%',
                        overflowWrap: 'anywhere',
                      }}
                    >
                      {Object.entries(ev.metadata).map(([k, v]) => (
                        <span key={k} style={{ marginRight: '10px' }}>
                          <span style={{ color: '#64748b' }}>{k}:</span>{' '}
                          <strong>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</strong>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div
                  style={{
                    fontSize: '0.75rem',
                    color: '#94a3b8',
                    whiteSpace: 'nowrap',
                    marginLeft: 'auto',
                  }}
                >
                  {new Date(ev.timestamp).toLocaleString()}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
