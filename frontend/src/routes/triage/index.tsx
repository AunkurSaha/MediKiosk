import { useEffect, useRef, useState } from 'react';
import { triageApi, type AlertItem, type AlertList, type AlertPriority, type AlertStatus } from '../../api/triage';
import AlertCard from '../../components/triage/AlertCard';
import { getTriageCopy } from '../../i18n/triage';

export default function Triage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [stats, setStats] = useState({
    total: 0,
    emergency_count: 0,
    urgent_count: 0,
    acknowledged_count: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [priorityFilter, setPriorityFilter] = useState<AlertPriority | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<AlertStatus | 'all'>('all');
  const [language, setLanguage] = useState<'en' | 'bn' | 'hi'>('en');
  const [wsConnected, setWsConnected] = useState(false);
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const t = getTriageCopy(language);

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    let reconnectTimeout: number | undefined;
    let isComponentMounted = true;

    triageApi
      .getAlerts()
      .then((res: AlertList) => {
        if (!isComponentMounted) return;
        setAlerts(res.items);
        setStats({
          total: res.total,
          emergency_count: res.emergency_count,
          urgent_count: res.urgent_count,
          acknowledged_count: res.acknowledged_count,
        });
        setError(null);
        setLoading(false);
      })
      .catch(() => {
        if (!isComponentMounted) return;
        setError('Failed to load triage alerts. Please retry.');
        setLoading(false);
      });

    function connectWs() {
      try {
        const url = triageApi.getWebSocketUrl();
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isComponentMounted) return;
          setWsConnected(true);
        };

        ws.onmessage = (event) => {
          if (!isComponentMounted) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'alert_created') {
              const newAlert = data.alert as AlertItem;
              setAlerts((prev) => {
                const filtered = prev.filter((a) => a.id !== newAlert.id);
                return [newAlert, ...filtered];
              });
              setStats((prev) => ({
                ...prev,
                total: prev.total + 1,
                emergency_count:
                  newAlert.priority === 'emergency' ? prev.emergency_count + 1 : prev.emergency_count,
                urgent_count:
                  newAlert.priority === 'urgent' ? prev.urgent_count + 1 : prev.urgent_count,
              }));
            } else if (data.type === 'alert_acknowledged') {
              const updatedAlert = data.alert as AlertItem;
              setAlerts((prev) =>
                prev.map((a) => (a.id === updatedAlert.id ? updatedAlert : a))
              );
              setStats((prev) => ({
                ...prev,
                acknowledged_count: prev.acknowledged_count + 1,
              }));
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
  }, [reloadTrigger]);

  async function handleAcknowledge(alertId: string, acknowledgedBy: string, note?: string) {
    setAcknowledgingId(alertId);
    try {
      const updated = await triageApi.acknowledgeAlert(alertId, {
        acknowledged_by: acknowledgedBy,
        note,
      });
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setStats((prev) => ({
        ...prev,
        acknowledged_count: prev.acknowledged_count + 1,
      }));
    } finally {
      setAcknowledgingId(null);
    }
  }

  const filteredAlerts = alerts.filter((alert) => {
    if (priorityFilter !== 'all' && alert.priority !== priorityFilter) return false;
    if (statusFilter !== 'all' && alert.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="triage-dashboard">
      <header className="triage-header">
        <div className="triage-title-group">
          <p className="eyebrow">{t.dashboardSubtitle}</p>
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

      {/* Metrics Row */}
      <section className="triage-metrics-row" aria-label="Triage Statistics">
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
