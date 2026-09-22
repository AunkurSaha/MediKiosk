import { useEffect, useRef, useState } from 'react';
import { api, type Hospital } from '../../api/client';
import {
  triageApi,
  type AlertItem,
  type AlertList,
  type AlertPriority,
  type AlertStatus,
  type WaitingPatient,
} from '../../api/triage';
import AlertCard from '../../components/triage/AlertCard';
import { getTriageCopy } from '../../i18n/triage';

function recordingPatientName(name: string) {
  return /^(synthetic|demo) patient\b/i.test(name.trim()) ? 'Patient' : name;
}

export default function Triage() {
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [selectedHospital, setSelectedHospital] = useState<Hospital | null>(() => {
    try {
      const saved = sessionStorage.getItem('triage_active_hospital');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [hospitalSearch, setHospitalSearch] = useState('');
  const [loadingHospitals, setLoadingHospitals] = useState(true);

  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [waitingPatients, setWaitingPatients] = useState<WaitingPatient[]>([]);
  const stats = {
    total: alerts.filter((a) => a.status !== 'resolved').length,
    emergency_count: alerts.filter((a) => a.status !== 'resolved' && a.priority === 'emergency')
      .length,
    urgent_count: alerts.filter((a) => a.status !== 'resolved' && a.priority === 'urgent').length,
    acknowledged_count: alerts.filter((a) => a.status === 'acknowledged').length,
  };
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [priorityFilter, setPriorityFilter] = useState<AlertPriority | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<AlertStatus | 'all'>('all');
  const [language, setLanguage] = useState<'en' | 'bn' | 'hi'>('en');
  const [wsConnected, setWsConnected] = useState(false);
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const refreshGeneration = useRef(0);
  const initialHospitalIdRef = useRef(selectedHospital?.id);
  const t = getTriageCopy(language);

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    const fetchHospitals = api.hospitals
      ? api.hospitals()
      : Promise.resolve({
          items: [
            {
              id: 'mock-hosp-1',
              name: 'MediKiosk General Hospital',
              city: 'Kolkata',
              address: 'West Bengal',
            },
          ] satisfies Hospital[],
        });
    fetchHospitals
      .then((res) => {
        if (res?.items) {
          setHospitals(res.items);
          if (initialHospitalIdRef.current) {
            const found = res.items.find((h) => h.id === initialHospitalIdRef.current);
            if (found) {
              setSelectedHospital(found);
              sessionStorage.setItem('triage_active_hospital', JSON.stringify(found));
            }
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoadingHospitals(false));
  }, []);

  const handleSelectHospital = (h: Hospital) => {
    setSelectedHospital(h);
    sessionStorage.setItem('triage_active_hospital', JSON.stringify(h));
    setLoading(true);
    setReloadTrigger((r) => r + 1);
  };

  const handleSwitchHospital = () => {
    setSelectedHospital(null);
    sessionStorage.removeItem('triage_active_hospital');
    setAlerts([]);
    setWaitingPatients([]);
  };

  useEffect(() => {
    if (!selectedHospital) return;
    const activeHospitalId = selectedHospital.id;

    let reconnectTimeout: number | undefined;
    let isComponentMounted = true;

    function refreshAlerts() {
      const generation = ++refreshGeneration.current;
      return Promise.all([
        // Safety alerts can be raised before a patient selects a facility.
        // The triage role's existing alert endpoint covers all active kiosks;
        // keep the waiting queue scoped to the selected hospital.
        triageApi.getAlerts({}),
        triageApi.getQueue(activeHospitalId),
      ])
        .then(([res, queue]: [AlertList, { items: WaitingPatient[] }]) => {
          if (!isComponentMounted || generation !== refreshGeneration.current) return;
          setAlerts(res.items);
          setWaitingPatients(queue.items);
          setError(null);
          setLoading(false);
        })
        .catch(() => {
          if (!isComponentMounted || generation !== refreshGeneration.current) return;
          setError('Failed to load triage alerts for this facility. Please retry.');
          setLoading(false);
        });
    }
    void refreshAlerts();

    async function connectWs() {
      try {
        const url = triageApi.getWebSocketUrl();
        const { ticket } = await triageApi.websocketTicket();
        if (!isComponentMounted) return;
        const ws = new WebSocket(url, ['medikiosk', ticket]);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isComponentMounted) return;
          setWsConnected(true);
          void refreshAlerts();
        };

        ws.onmessage = (event) => {
          if (!isComponentMounted) return;
          try {
            const data = JSON.parse(event.data);
            if (
              [
                'alert_created',
                'alert_updated',
                'alert_resolved',
                'alert_reactivated',
                'alert_acknowledged',
              ].includes(data.type)
            ) {
              void refreshAlerts();
            }
          } catch {
            // Ignore parse errors on ping/pong frames
          }
        };

        ws.onclose = () => {
          if (!isComponentMounted) return;
          setWsConnected(false);
          reconnectTimeout = window.setTimeout(connectWs, 3000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        if (isComponentMounted) {
          reconnectTimeout = window.setTimeout(connectWs, 5000);
        }
      }
    }

    connectWs();

    return () => {
      isComponentMounted = false;
      if (reconnectTimeout) window.clearTimeout(reconnectTimeout);
      if (wsRef.current) wsRef.current.close();
    };
  }, [reloadTrigger, selectedHospital]);

  async function handleAcknowledge(alertId: string, note?: string) {
    setAcknowledgingId(alertId);
    try {
      const updated = await triageApi.acknowledgeAlert(alertId, {
        note,
        expected_revision: alerts.find((a) => a.id === alertId)?.revision ?? 0,
      });
      refreshGeneration.current++;
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === updated.id && (updated.revision ?? 0) >= (a.revision ?? 0) ? updated : a,
        ),
      );
      setReloadTrigger((value) => value + 1);
    } finally {
      setAcknowledgingId(null);
    }
  }

  const filteredAlerts = alerts.filter((alert) => {
    if (priorityFilter !== 'all' && alert.priority !== priorityFilter) return false;
    if (statusFilter !== 'all' && alert.status !== statusFilter) return false;
    return true;
  });

  // --------------------------------------------------------------------------
  // Hospital-First Selection View
  // --------------------------------------------------------------------------
  if (!selectedHospital) {
    const matchingHospitals = hospitals.filter(
      (h) =>
        h.name.toLowerCase().includes(hospitalSearch.toLowerCase()) ||
        (h.city && h.city.toLowerCase().includes(hospitalSearch.toLowerCase())) ||
        (h.address && h.address.toLowerCase().includes(hospitalSearch.toLowerCase())),
    );

    return (
      <div
        className="triage-dashboard"
        style={{ maxWidth: '800px', margin: '40px auto', padding: '0 20px' }}
      >
        <div className="card" style={{ padding: '36px' }}>
          <div style={{ textAlign: 'center', marginBottom: '28px' }}>
            <div
              className="brand-mark"
              style={{
                width: '52px',
                height: '52px',
                fontSize: '2.4rem',
                margin: '0 auto 12px',
                background: '#e11d48',
                color: '#fff',
              }}
              aria-hidden="true"
            >
              🚨
            </div>
            <h1 style={{ fontSize: '1.85rem', margin: '0 0 8px' }}>Emergency Triage Command</h1>
            <p
              className="eyebrow"
              style={{
                color: '#9f1239',
                background: '#ffe4e6',
                display: 'inline-block',
                padding: '4px 14px',
                borderRadius: '16px',
              }}
            >
              Select Active Healthcare Facility
            </p>
            <p className="muted" style={{ marginTop: '12px', fontSize: '0.95rem' }}>
              To monitor incoming red flags and high-acuity intake sessions in real-time, please
              pick your triage hospital.
            </p>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <input
              type="text"
              placeholder="🔍 Search hospital by name, district, or city…"
              value={hospitalSearch}
              onChange={(e) => setHospitalSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '12px 16px',
                fontSize: '1rem',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.05)',
              }}
            />
          </div>

          {loadingHospitals && (
            <p role="status" style={{ textAlign: 'center' }}>
              Loading available hospitals…
            </p>
          )}

          {!loadingHospitals && matchingHospitals.length === 0 && (
            <div style={{ textAlign: 'center', padding: '30px', color: '#64748b' }}>
              <p>No hospitals found matching your search.</p>
            </div>
          )}

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '16px',
            }}
          >
            {matchingHospitals.map((h) => (
              <div
                key={h.id}
                onClick={() => handleSelectHospital(h)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') handleSelectHospital(h);
                }}
                style={{
                  border: '2px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '20px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  background: '#ffffff',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#e11d48';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(225, 29, 72, 0.12)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#e2e8f0';
                  e.currentTarget.style.transform = 'none';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '8px',
                    }}
                  >
                    <span style={{ fontSize: '1.4rem' }}>🏥</span>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        background: '#ecfdf5',
                        color: '#047857',
                        padding: '2px 8px',
                        borderRadius: '10px',
                      }}
                    >
                      Active Triage
                    </span>
                  </div>
                  <h3 style={{ margin: '0 0 6px', fontSize: '1.1rem', color: '#0f172a' }}>
                    {h.name}
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b' }}>
                    📍 {h.address || h.city || 'India'}
                  </p>
                </div>
                <div
                  style={{
                    marginTop: '16px',
                    paddingTop: '12px',
                    borderTop: '1px solid #f1f5f9',
                    display: 'flex',
                    justifyContent: 'flex-end',
                  }}
                >
                  <span style={{ color: '#e11d48', fontWeight: 600, fontSize: '0.88rem' }}>
                    Open Triage Stream →
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="triage-dashboard">
      <header className="triage-header">
        <div className="triage-title-group">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span
              style={{
                background: '#e0f2fe',
                color: '#0369a1',
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '0.82rem',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              🏥 {selectedHospital.name} ({selectedHospital.city || 'Facility'})
            </span>
            <button
              type="button"
              onClick={handleSwitchHospital}
              style={{
                background: '#f1f5f9',
                border: '1px solid #cbd5e1',
                padding: '2px 8px',
                borderRadius: '6px',
                fontSize: '0.78rem',
                cursor: 'pointer',
                color: '#475569',
                fontWeight: 500,
              }}
              title="Change facility"
            >
              ⇄ Switch Hospital
            </button>
          </div>
          <p className="eyebrow" style={{ margin: 0 }}>
            {t.dashboardSubtitle}
          </p>
          <h1>{t.dashboardTitle}</h1>
        </div>

        <div className="triage-header-controls">
          <div
            className={`ws-indicator ${wsConnected ? 'connected' : 'disconnected'}`}
            title={wsConnected ? t.liveFeedConnected : t.liveFeedConnecting}
          >
            <span className="indicator-dot" />
            <span className="indicator-text">
              {wsConnected ? t.liveFeedConnected : t.liveFeedConnecting}
            </span>
          </div>

          <div className="lang-picker">
            <button
              type="button"
              className={language === 'en' ? 'active' : ''}
              onClick={() => setLanguage('en')}
            >
              EN
            </button>
            <button
              type="button"
              className={language === 'bn' ? 'active' : ''}
              onClick={() => setLanguage('bn')}
            >
              বাং
            </button>
            <button
              type="button"
              className={language === 'hi' ? 'active' : ''}
              onClick={() => setLanguage('hi')}
            >
              हिं
            </button>
          </div>

          <button
            type="button"
            className="secondary btn-refresh"
            onClick={() => {
              setLoading(true);
              setReloadTrigger((r) => r + 1);
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </header>

      <p className="muted">
        Safety alerts from all active kiosks; waiting queue for {selectedHospital.name}.
      </p>
      {/* Metrics Row */}
      <section className="triage-metrics-row" aria-label="Triage Statistics">
        <div className="metric-card total">
          <span className="metric-count">{waitingPatients.length}</span>
          <span className="metric-label">Patients waiting</span>
        </div>
        <div className="metric-card emergency">
          <span className="metric-count">{stats.emergency_count}</span>
          <span className="metric-label">{t.statEmergency}</span>
        </div>
        <div className="metric-card urgent">
          <span className="metric-count">{stats.urgent_count}</span>
          <span className="metric-label">{t.statUrgent}</span>
        </div>
        <div className="metric-card acknowledged">
          <span className="metric-count">{stats.acknowledged_count}</span>
          <span className="metric-label">{t.statAcknowledged}</span>
        </div>
        <div className="metric-card total">
          <span className="metric-count">{stats.total}</span>
          <span className="metric-label">{t.statTotal}</span>
        </div>
      </section>

      {!loading && (
        <section
          className="card"
          aria-label="Waiting Patient Queue"
          style={{ marginBottom: '20px' }}
        >
          <h2 style={{ marginTop: 0 }}>Waiting patient queue ({waitingPatients.length})</h2>
          {waitingPatients.length === 0 ? (
            <p className="muted">No patients are currently waiting at this hospital.</p>
          ) : (
            <div style={{ display: 'grid', gap: '8px' }}>
              {waitingPatients.map((patient, index) => (
                <div
                  key={patient.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '10px 12px',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                  }}
                >
                  <span>
                    <strong>
                      {index + 1}. {recordingPatientName(patient.patient_name)}
                    </strong>
                  </span>
                  <span className="badge">WAITING</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Filters Bar */}
      <section className="triage-filter-bar">
        <div className="filter-group">
          <label htmlFor="priority-filter">{t.priority}:</label>
          <select
            id="priority-filter"
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value as AlertPriority | 'all')}
          >
            <option value="all">{t.filterAll}</option>
            <option value="emergency">{t.filterEmergency}</option>
            <option value="urgent">{t.filterUrgent}</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="status-filter">{t.status}:</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as AlertStatus | 'all')}
          >
            <option value="all">{t.allAlerts}</option>
            <option value="new">{t.filterNew}</option>
            <option value="acknowledged">{t.filterAcknowledged}</option>
            <option value="resolved">{t.filterResolved}</option>
          </select>
        </div>
      </section>

      {error && (
        <div className="error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setLoading(true);
              setReloadTrigger((r) => r + 1);
            }}
          >
            Retry
          </button>
        </div>
      )}

      {loading && <p role="status">Loading alerts...</p>}

      {!loading && filteredAlerts.length === 0 && (
        <div className="card empty-triage">
          <p>{t.noAlerts}</p>
        </div>
      )}

      {!loading && filteredAlerts.length > 0 && (
        <section className="alert-cards-grid" aria-label="Alert List">
          {filteredAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onAcknowledge={handleAcknowledge}
              isAcknowledging={acknowledgingId === alert.id}
              language={language}
            />
          ))}
        </section>
      )}
    </div>
  );
}
