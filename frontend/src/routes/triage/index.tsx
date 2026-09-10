import { useEffect, useRef, useState } from 'react';
import {
  triageApi,
  type AlertItem,
  type AlertList,
  type AlertPriority,
  type AlertStatus,
} from '../../api/triage';
import AlertCard from '../../components/triage/AlertCard';
import { getTriageCopy } from '../../i18n/triage';

export default function Triage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
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
  const t = getTriageCopy(language);

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    let reconnectTimeout: number | undefined;
    let isComponentMounted = true;

    function refreshAlerts() {
      const generation = ++refreshGeneration.current;
      return triageApi
        .getAlerts()
        .then((res: AlertList) => {
          if (!isComponentMounted || generation !== refreshGeneration.current) return;
          setAlerts(res.items);
          setError(null);
          setLoading(false);
        })
        .catch(() => {
          if (!isComponentMounted || generation !== refreshGeneration.current) return;
          setError('Failed to load triage alerts. Please retry.');
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
  }, [reloadTrigger]);

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
