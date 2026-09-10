import { useState, useEffect } from 'react';
import type { FC } from 'react';
import { api } from '../../api/client';
import type { FHIRExportResponse } from '../../api/client';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  patientName?: string;
  hospitalToken?: string;
}

export const FHIRExportModal: FC<Props> = ({
  isOpen,
  onClose,
  sessionId,
  patientName,
  hospitalToken,
}) => {
  const [bundleType, setBundleType] = useState<'document' | 'collection'>('document');
  const [exportData, setExportData] = useState<FHIRExportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    if (!isOpen || !sessionId) return;
    api
      .getFhirExport(sessionId, bundleType)
      .then((data) => {
        if (active) {
          setExportData(data);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to export FHIR bundle.');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isOpen, sessionId, bundleType]);

  if (!isOpen) return null;

  const handleCopy = async () => {
    if (!exportData?.bundle) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(exportData.bundle, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Failed to copy to clipboard.');
    }
  };

  const handleDownload = () => {
    if (!exportData?.bundle) return;
    const jsonStr = JSON.stringify(exportData.bundle, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/fhir+json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `fhir-bundle-${exportData.bundle_type}-${sessionId.slice(0, 8)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const validationErrors = (exportData?.validation?.issue || []).filter(
    (i) => i.severity === 'error' || i.severity === 'fatal'
  );
  const validationWarnings = (exportData?.validation?.issue || []).filter(
    (i) => i.severity === 'warning'
  );

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
          maxWidth: '850px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px' }}>📦</span>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: '#1e293b' }}>
                HL7 FHIR R4 Bundle Export
              </h3>
            </div>
            <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
              Standardized clinical data package for{' '}
              <strong>{patientName || 'Patient'}</strong> ({hospitalToken || sessionId.slice(0, 8)})
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-secondary"
            aria-label="Close"
            style={{
              padding: '4px 8px',
              fontSize: '18px',
              lineHeight: 1,
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              color: '#64748b',
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {error && (
            <div
              style={{
                padding: '10px 14px',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                color: '#b91c1c',
                fontSize: '13px',
              }}
            >
              <strong>Export Error:</strong> {error}
            </div>
          )}

          {/* Bundle Type Selector & Action Bar */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '10px',
              backgroundColor: '#f8fafc',
              padding: '10px 14px',
              borderRadius: '6px',
              border: '1px solid #e2e8f0',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>Bundle Format:</span>
              <button
                type="button"
                className={`btn btn-sm ${bundleType === 'document' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setBundleType('document')}
                style={{
                  padding: '4px 10px',
                  fontSize: '12px',
                  borderRadius: '4px',
                  backgroundColor: bundleType === 'document' ? '#2563eb' : '#ffffff',
                  color: bundleType === 'document' ? '#ffffff' : '#334155',
                  border: '1px solid #cbd5e1',
                  cursor: 'pointer',
                }}
              >
                Document (Composition LOINC 34105-7)
              </button>
              <button
                type="button"
                className={`btn btn-sm ${bundleType === 'collection' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setBundleType('collection')}
                style={{
                  padding: '4px 10px',
                  fontSize: '12px',
                  borderRadius: '4px',
                  backgroundColor: bundleType === 'collection' ? '#2563eb' : '#ffffff',
                  color: bundleType === 'collection' ? '#ffffff' : '#334155',
                  border: '1px solid #cbd5e1',
                  cursor: 'pointer',
                }}
              >
                Collection (Flat)
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={handleCopy}
                disabled={loading || !exportData}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  borderRadius: '4px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #cbd5e1',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                {copied ? '✓ Copied!' : '📋 Copy JSON'}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={handleDownload}
                disabled={loading || !exportData}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  borderRadius: '4px',
                  backgroundColor: '#059669',
                  color: '#ffffff',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                ⬇ Download JSON
              </button>
            </div>
          </div>

          {/* Conformance & Validation Badge */}
          {exportData && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                borderRadius: '6px',
                backgroundColor: validationErrors.length > 0 ? '#fef2f2' : '#f0fdf4',
                border: `1px solid ${validationErrors.length > 0 ? '#fca5a5' : '#bbf7d0'}`,
                fontSize: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '14px' }}>
                  {validationErrors.length > 0 ? '❌' : '✅'}
                </span>
                <span style={{ fontWeight: 600, color: validationErrors.length > 0 ? '#991b1b' : '#166534' }}>
                  {validationErrors.length > 0
                    ? `${validationErrors.length} Conformance Issues Found`
                    : 'HL7 FHIR R4 Conformance Validated'}
                </span>
                <span style={{ color: '#64748b' }}>
                  ({exportData.compliance_profile})
                </span>
              </div>
              <span style={{ color: '#475569', fontSize: '11px' }}>
                Total Entries: <strong>{exportData.bundle.entry.length}</strong>
              </span>
            </div>
          )}

          {/* Validation Warnings/Errors List if any */}
          {validationErrors.length > 0 && (
            <div style={{ backgroundColor: '#fff1f2', padding: '8px 12px', borderRadius: '6px', border: '1px solid #fecdd3' }}>
              <div style={{ fontWeight: 600, fontSize: '12px', color: '#9f1239', marginBottom: '4px' }}>Issues:</div>
              <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '12px', color: '#be123c' }}>
                {validationErrors.map((issue, idx) => (
                  <li key={idx}>
                    [{issue.code}] {issue.diagnostics} {issue.expression?.join(', ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {validationWarnings.length > 0 && (
            <div style={{ backgroundColor: '#fffbeb', padding: '8px 12px', borderRadius: '6px', border: '1px solid #fef3c7' }}>
              <div style={{ fontWeight: 600, fontSize: '12px', color: '#92400e', marginBottom: '4px' }}>Warnings:</div>
              <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '12px', color: '#b45309' }}>
                {validationWarnings.map((issue, idx) => (
                  <li key={idx}>
                    [{issue.code}] {issue.diagnostics}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Resource Breakdown Badges */}
          {exportData && (
            <div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Resource Inventory:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {Object.entries(exportData.resource_counts).map(([type, count]) => (
                  <span
                    key={type}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '3px 8px',
                      borderRadius: '12px',
                      fontSize: '11px',
                      backgroundColor: '#e0f2fe',
                      color: '#0369a1',
                      border: '1px solid #bae6fd',
                      fontWeight: 500,
                    }}
                  >
                    <span>{type}:</span>
                    <strong>{count}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* JSON Preview Container */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Bundle JSON:</span>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                MIME: <code>application/fhir+json</code>
              </span>
            </div>
            {loading ? (
              <div
                style={{
                  height: '240px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '6px',
                  color: '#64748b',
                  fontSize: '13px',
                }}
              >
                Assembling and validating FHIR R4 bundle...
              </div>
            ) : (
              <pre
                data-testid="fhir-json-preview"
                style={{
                  margin: 0,
                  padding: '12px',
                  backgroundColor: '#0f172a',
                  color: '#e2e8f0',
                  borderRadius: '6px',
                  fontSize: '11px',
                  lineHeight: 1.4,
                  overflowX: 'auto',
                  maxHeight: '260px',
                  fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                }}
              >
                {exportData?.bundle ? JSON.stringify(exportData.bundle, null, 2) : '// No bundle generated'}
              </pre>
            )}
          </div>

          {/* Safety Guardrail Disclaimer */}
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '6px',
              backgroundColor: '#f1f5f9',
              border: '1px solid #e2e8f0',
              fontSize: '11px',
              color: '#475569',
              lineHeight: 1.4,
            }}
          >
            🛡 <strong>Non-Diagnostic Boundary:</strong> Condition resources contained in this bundle represent provisional, patient-reported intake symptoms only. This export does not constitute an autonomous diagnosis or treatment prescription. Clinician review required before clinical decision making.
          </div>
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
            backgroundColor: '#f8fafc',
            borderBottomLeftRadius: '8px',
            borderBottomRightRadius: '8px',
          }}
        >
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              borderRadius: '4px',
              backgroundColor: '#ffffff',
              border: '1px solid #cbd5e1',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
