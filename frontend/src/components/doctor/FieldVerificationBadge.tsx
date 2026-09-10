import { useState } from 'react';
import { api } from '../../api/client';
import type {
  FieldVerificationRecord,
  FieldVerificationStatus,
  FieldVerificationType,
} from '../../api/client';

interface Props {
  sessionId: string;
  fieldType: FieldVerificationType;
  fieldId: string;
  currentStatus?: FieldVerificationStatus;
  currentNotes?: string | null;
  disabled?: boolean;
  onVerificationChanged?: (record: FieldVerificationRecord) => void;
}

export const FieldVerificationBadge: React.FC<Props> = ({
  sessionId,
  fieldType,
  fieldId,
  currentStatus = 'unverified',
  currentNotes = null,
  disabled = false,
  onVerificationChanged,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<FieldVerificationStatus>(currentStatus);
  const [notes, setNotes] = useState<string>(currentNotes || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async (newStatus: FieldVerificationStatus) => {
    setLoading(true);
    setError(null);
    try {
      const updated = await api.verifyField(sessionId, {
        field_type: fieldType,
        field_id: fieldId,
        status: newStatus,
        notes: notes.trim() || undefined,
      });
      setStatus(updated.status);
      setIsOpen(false);
      onVerificationChanged?.(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setLoading(false);
    }
  };

  const getBadgeClass = () => {
    switch (status) {
      case 'verified':
        return 'badge-verified';
      case 'flagged':
        return 'badge-flagged';
      default:
        return 'badge-unverified';
    }
  };

  const getBadgeLabel = () => {
    switch (status) {
      case 'verified':
        return '✓ Verified';
      case 'flagged':
        return '⚠️ Flagged';
      default:
        return 'Unverified';
    }
  };

  return (
    <div
      className="field-verification-container"
      style={{ display: 'inline-block', position: 'relative' }}
    >
      <button
        type="button"
        className={`field-verification-badge ${getBadgeClass()}`}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        title={notes ? `Notes: ${notes}` : 'Click to verify or flag'}
        style={{
          cursor: disabled ? 'default' : 'pointer',
          border: '1px solid #cbd5e1',
          borderRadius: '4px',
          padding: '2px 6px',
          fontSize: '0.75rem',
          fontWeight: 600,
          background:
            status === 'verified' ? '#dcfce7' : status === 'flagged' ? '#fef3c7' : '#f1f5f9',
          color: status === 'verified' ? '#166534' : status === 'flagged' ? '#92400e' : '#475569',
        }}
      >
        {getBadgeLabel()}
      </button>

      {isOpen && (
        <div
          className="field-verification-popover"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            zIndex: 50,
            width: '240px',
            padding: '12px',
            backgroundColor: '#ffffff',
            borderRadius: '6px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            border: '1px solid #e2e8f0',
            marginTop: '4px',
          }}
        >
          <div
            style={{ fontWeight: 600, fontSize: '0.8rem', marginBottom: '8px', color: '#1e293b' }}
          >
            Clinician Verification
          </div>

          {error && (
            <div style={{ color: '#dc2626', fontSize: '0.75rem', marginBottom: '6px' }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: '8px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.7rem',
                color: '#64748b',
                marginBottom: '2px',
              }}
            >
              Clinician Note (optional):
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Verified with patient"
              style={{
                width: '100%',
                padding: '4px 6px',
                fontSize: '0.75rem',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: '4px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleSave('verified')}
              style={{
                backgroundColor: '#16a34a',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              Verify
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleSave('flagged')}
              style={{
                backgroundColor: '#d97706',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              Flag
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleSave('unverified')}
              style={{
                backgroundColor: '#94a3b8',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                padding: '4px 8px',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              Reset
            </button>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              style={{
                backgroundColor: 'transparent',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
                padding: '4px 6px',
                fontSize: '0.75rem',
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
