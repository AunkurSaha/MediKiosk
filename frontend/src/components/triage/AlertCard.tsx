import { useState } from 'react';
import type { AlertItem } from '../../api/triage';
import { getTriageCopy } from '../../i18n/triage';

interface AlertCardProps {
  alert: AlertItem;
  onAcknowledge: (alertId: string, acknowledgedBy: string, note?: string) => Promise<void>;
  isAcknowledging?: boolean;
  language?: string;
}

export default function AlertCard({
  alert,
  onAcknowledge,
  isAcknowledging = false,
  language = 'en',
}: AlertCardProps) {
  const [showForm, setShowForm] = useState(false);
  const [staffName, setStaffName] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  const t = getTriageCopy(language);

  const isEmergency = alert.priority === 'emergency';
  const isNew = alert.status === 'new';

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (!staffName.trim()) {
      setError('Staff member name or ID is required.');
      return;
    }
    setError(null);
    try {
      await onAcknowledge(alert.id, staffName.trim(), note.trim() || undefined);
      setShowForm(false);
    } catch {
      setError('Failed to acknowledge alert. Please retry.');
    }
  }

  function formatTime(iso: string | null) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso;
    }
  }

  return (
    <article
      className={`alert-card ${alert.priority} status-${alert.status}`}
      data-testid={`alert-card-${alert.id}`}
      aria-labelledby={`alert-heading-${alert.id}`}
    >
      <div className="alert-card-header">
        <div className="alert-badge-group">
          <span className={`priority-badge ${alert.priority}`}>
            {isEmergency && <span className="pulse-dot" aria-hidden="true" />}
            {alert.priority.toUpperCase()}
          </span>
          <span className={`status-badge status-${alert.status}`}>
            {alert.status === 'new'
              ? t.filterNew
              : alert.status === 'acknowledged'
                ? t.filterAcknowledged
                : t.filterResolved}
          </span>
          <span className="category-tag">{alert.category}</span>
        </div>
        <div className="alert-time">
          <span className="time-label">{t.detectedAt}:</span> {formatTime(alert.created_at)}
        </div>
      </div>

      <div className="alert-patient-row">
        <div className="patient-token-badge">{alert.hospital_token || 'NO-TOKEN'}</div>
        <div className="patient-name-wrapper">
          <h3 id={`alert-heading-${alert.id}`}>{alert.patient_name || 'Patient'}</h3>
          <span className="rule-id-label">{alert.rule_id}</span>
        </div>
      </div>

      <p className="alert-reason">{alert.reason}</p>

      {alert.triggering_facts && alert.triggering_facts.length > 0 && (
        <div className="triggering-facts-section">
          <h4>{t.triggeringFacts}</h4>
          <ul className="triggering-facts-list">
            {alert.triggering_facts.map((fact, idx) => (
              <li key={idx} className="fact-item">
                <span className="fact-field">{fact.field}:</span>{' '}
                <strong className="fact-value">{String(fact.raw_value ?? fact.value)}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}

      {alert.status === 'acknowledged' && (
        <div className="acknowledgement-info">
          <p>
            ✓ <strong>{t.acknowledgedBy}:</strong> {alert.acknowledged_by} (
            {formatTime(alert.acknowledged_at)})
          </p>
          {alert.acknowledgement_note && (
            <p className="acknowledgement-note">
              <em>"{alert.acknowledgement_note}"</em>
            </p>
          )}
        </div>
      )}

      {isNew && !showForm && (
        <div className="alert-card-actions">
          <button
            type="button"
            className={`btn-acknowledge ${alert.priority}`}
            onClick={() => setShowForm(true)}
            disabled={isAcknowledging}
          >
            {t.actionAcknowledge}
          </button>
        </div>
      )}

      {isNew && showForm && (
        <form className="acknowledge-form" onSubmit={handleConfirm}>
          <h4>{t.actionAcknowledge}</h4>
          {error && <p className="form-error">{error}</p>}
          <div className="form-group">
            <input
              type="text"
              id={`staff-name-${alert.id}`}
              placeholder={t.staffNamePlaceholder}
              value={staffName}
              onChange={(e) => setStaffName(e.target.value)}
              disabled={isAcknowledging}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <input
              type="text"
              id={`staff-note-${alert.id}`}
              placeholder={t.notePlaceholder}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={isAcknowledging}
            />
          </div>
          <div className="form-buttons">
            <button
              type="submit"
              className="btn-confirm"
              disabled={isAcknowledging || !staffName.trim()}
            >
              {isAcknowledging ? t.acknowledging : t.confirmAcknowledge}
            </button>
            <button
              type="button"
              className="secondary btn-cancel"
              onClick={() => {
                setShowForm(false);
                setError(null);
              }}
              disabled={isAcknowledging}
            >
              {t.cancel}
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
