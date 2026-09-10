import { useState } from 'react';
import type { FC, FormEvent } from 'react';
import { api } from '../../api/client';
import type { Summary } from '../../api/client';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  confirmedText: string;
  onAmendmentSaved: (updatedSummary: Summary) => void;
}

export const SummaryAmendmentModal: FC<Props> = ({
  isOpen,
  onClose,
  sessionId,
  confirmedText,
  onAmendmentSaved,
}) => {
  const [amendedText, setAmendedText] = useState(
    confirmedText ? `${confirmedText}\n\n## Clinical Addendum\n` : ''
  );
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!amendedText.trim()) {
      setError('Amended summary text is required.');
      return;
    }
    if (!notes.trim() || notes.trim().length < 3) {
      setError('A clinical justification note (minimum 3 characters) is required.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const updated = await api.amendSummary(sessionId, amendedText, notes.trim());
      onAmendmentSaved(updated);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to file amendment.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="modal-backdrop"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '16px',
      }}
    >
      <div
        className="modal-dialog card"
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          maxWidth: '700px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
        }}
      >
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#1e293b' }}>
            File Clinical Summary Amendment
          </h3>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.25rem',
              cursor: 'pointer',
              color: '#64748b',
            }}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', overflowY: 'auto', maxHeight: 'calc(90vh - 140px)' }}>
            <div
              style={{
                backgroundColor: '#eff6ff',
                border: '1px solid #bfdbfe',
                borderRadius: '6px',
                padding: '10px 12px',
                marginBottom: '14px',
                fontSize: '0.85rem',
                color: '#1e40af',
              }}
            >
              <strong>Notice:</strong> The original confirmed record remains permanently preserved in audit history.
              The amendment is attached as an official clinical addendum with server-authenticated clinician provenance.
            </div>

            {error && (
              <div
                style={{
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  marginBottom: '12px',
                  fontSize: '0.85rem',
                  color: '#b91c1c',
                }}
              >
                {error}
              </div>
            )}

            <div style={{ marginBottom: '14px' }}>
              <label
                htmlFor="amendment-notes-input"
                style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: '4px', color: '#334155' }}
              >
                Clinical Justification Notes (required):
              </label>
              <input
                id="amendment-notes-input"
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. ECG reviewed post-consultation; patient clarifies onset timing"
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: '4px',
                  border: '1px solid #cbd5e1',
                  fontSize: '0.9rem',
                }}
                required
              />
            </div>

            <div>
              <label
                htmlFor="amended-text-textarea"
                style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: '4px', color: '#334155' }}
              >
                Amended Summary / Addendum Content:
              </label>
              <textarea
                id="amended-text-textarea"
                value={amendedText}
                onChange={(e) => setAmendedText(e.target.value)}
                rows={12}
                style={{
                  width: '100%',
                  padding: '10px',
                  borderRadius: '4px',
                  border: '1px solid #cbd5e1',
                  fontFamily: 'monospace',
                  fontSize: '0.85rem',
                  lineHeight: '1.4',
                }}
                required
              />
            </div>
          </div>

          <div
            style={{
              padding: '12px 20px',
              borderTop: '1px solid #e2e8f0',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '10px',
              backgroundColor: '#f8fafc',
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              style={{
                padding: '8px 14px',
                borderRadius: '4px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '8px 16px',
                borderRadius: '4px',
                border: 'none',
                backgroundColor: '#2563eb',
                color: '#ffffff',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.85rem',
              }}
            >
              {loading ? 'Filing Amendment...' : 'Save Clinical Amendment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
