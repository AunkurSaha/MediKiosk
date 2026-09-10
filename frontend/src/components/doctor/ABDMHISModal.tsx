import React, { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { ABDMStatusResponse, HISDispatchResponse } from '../../api/client';

interface ABDMHISModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  patientName: string;
  hospitalToken: string;
  demoAbhaId?: string | null;
}

export const ABDMHISModal: React.FC<ABDMHISModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  patientName,
  hospitalToken,
  demoAbhaId,
}) => {
  const [statusData, setStatusData] = useState<ABDMStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // M1 Verification State
  const [abhaInput, setAbhaInput] = useState(demoAbhaId || 'patient@abdm');
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);

  // M2 Linking State
  const [linkLoading, setLinkLoading] = useState(false);
  const [linkMessage, setLinkMessage] = useState<string | null>(null);

  // HIS Dispatch State
  const [targetSystem, setTargetSystem] = useState('Central Hospital OPD HIS');
  const [dispatchLoading, setDispatchLoading] = useState(false);
  const [dispatchResponse, setDispatchResponse] = useState<HISDispatchResponse | null>(null);
  const [dispatchMessage, setDispatchMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!isOpen || !sessionId) return;

    api
      .getAbdmStatus(sessionId)
      .then((data) => {
        if (active) {
          setStatusData(data);
          if (data.abha_address) {
            setAbhaInput(data.abha_address);
          }
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load ABDM status');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isOpen, sessionId]);

  if (!isOpen) return null;

  const handleVerifyAbha = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!abhaInput.trim()) return;
    setVerifyLoading(true);
    setVerifyMessage(null);
    try {
      const res = await api.verifyDoctorAbha(sessionId, abhaInput.trim());
      if (res.success && res.profile) {
        setVerifyMessage(`✓ ABHA verified: ${res.profile.name} (${res.profile.abha_number})`);
        const updated = await api.getAbdmStatus(sessionId);
        setStatusData(updated);
      } else {
        setVerifyMessage(`⚠️ ${res.message}`);
      }
    } catch (err: unknown) {
      setVerifyMessage(`Error: ${err instanceof Error ? err.message : 'Verification failed'}`);
    } finally {
      setVerifyLoading(false);
    }
  };

  const handleLinkCareContext = async () => {
    setLinkLoading(true);
    setLinkMessage(null);
    try {
      const res = await api.linkCareContext(sessionId);
      if (res.success) {
        setLinkMessage(`✓ Linked care context: ${res.care_context_reference}`);
        const updated = await api.getAbdmStatus(sessionId);
        setStatusData(updated);
      } else {
        setLinkMessage(`⚠️ ${res.message}`);
      }
    } catch (err: unknown) {
      setLinkMessage(`Error: ${err instanceof Error ? err.message : 'Care context linking failed'}`);
    } finally {
      setLinkLoading(false);
    }
  };

  const handleDispatchHis = async () => {
    setDispatchLoading(true);
    setDispatchMessage(null);
    try {
      const res = await api.dispatchHis(sessionId, targetSystem);
      if (res.success) {
        setDispatchResponse(res);
        setDispatchMessage(`✓ Dispatched to ${targetSystem} (Receipt: ${res.receipt_reference})`);
        const updated = await api.getAbdmStatus(sessionId);
        setStatusData(updated);
      } else {
        setDispatchMessage(`⚠️ ${res.message}`);
      }
    } catch (err: unknown) {
      setDispatchMessage(`Error: ${err instanceof Error ? err.message : 'HIS dispatch failed'}`);
    } finally {
      setDispatchLoading(false);
    }
  };

  const isVerified = statusData?.abha_status === 'mock_verified' || statusData?.abha_status === 'verified';
  const isLinked = statusData?.care_context_status === 'linked';
  const isDispatched = statusData?.his_dispatch_status === 'dispatched';

  return (
    <div
      className="modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '1rem',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      data-testid="abdm-his-modal"
    >
      <div
        className="modal-card"
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '1rem',
          maxWidth: '850px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '1.25rem 1.75rem',
            borderBottom: '1px solid #e2e8f0',
            backgroundColor: '#f8fafc',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '1.5rem' }}>🏥</span>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                ABDM & HIS Interoperability Hub
              </h2>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  backgroundColor: '#e0e7ff',
                  color: '#3730a3',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '9999px',
                }}
              >
                Sandbox Demonstration
              </span>
            </div>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>
              Patient: <strong>{patientName}</strong> · Token: <strong>{hospitalToken}</strong> · Session: <code>{sessionId.slice(0, 8)}</code>
            </p>
          </div>
          <button
            onClick={onClose}
            data-testid="close-abdm-modal-btn"
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.5rem',
              color: '#64748b',
              cursor: 'pointer',
              padding: '0.25rem',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
          {/* Disclaimer banner */}
          <div
            style={{
              padding: '0.75rem 1rem',
              backgroundColor: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: '0.5rem',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontSize: '0.85rem',
              color: '#1e40af',
            }}
          >
            <span style={{ fontSize: '1.1rem' }}>ℹ️</span>
            <div>
              <strong>ABDM Sandbox & Simulated HIS Gateway:</strong> Synthetic local demonstration of National Health Stack M1, M2 & OPD HIS dispatch. No real Aadhaar or production NHA gateway authentication claimed.
            </div>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
              <p>Loading ABDM and HIS integration status...</p>
            </div>
          ) : error ? (
            <div style={{ padding: '1rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '0.5rem', color: '#b91c1c' }}>
              <p><strong>Error loading status:</strong> {error}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Section 1: ABDM M1 (ABHA Verification) */}
              <div
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '0.75rem',
                  padding: '1.25rem',
                  backgroundColor: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>🪪</span>
                    <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#1e293b' }}>
                      Milestone 1 (M1): ABHA Identity & Verification
                    </h3>
                  </div>
                  <span
                    data-testid="abha-status-badge"
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      padding: '0.2rem 0.6rem',
                      borderRadius: '9999px',
                      backgroundColor: isVerified ? '#dcfce7' : '#fef9c3',
                      color: isVerified ? '#166534' : '#854d0e',
                    }}
                  >
                    {isVerified ? '✓ Verified (Sandbox Mock)' : '⚠️ Unverified'}
                  </span>
                </div>

                <div style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '1rem' }}>
                  <p style={{ margin: '0.25rem 0' }}>
                    <strong>ABHA Address:</strong> {statusData?.abha_address || 'None configured'}
                  </p>
                  <p style={{ margin: '0.25rem 0' }}>
                    <strong>ABHA Number:</strong> {statusData?.abha_number || 'None'}
                  </p>
                </div>

                {/* Inline verification form */}
                <form onSubmit={handleVerifyAbha} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <input
                    type="text"
                    value={abhaInput}
                    onChange={(e) => setAbhaInput(e.target.value)}
                    placeholder="e.g. patient@abdm or 91-1234-5678-9012"
                    data-testid="abha-input"
                    style={{
                      flex: 1,
                      padding: '0.5rem 0.75rem',
                      borderRadius: '0.5rem',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setAbhaInput('patient@abdm')}
                    style={{
                      padding: '0.4rem 0.6rem',
                      backgroundColor: '#f1f5f9',
                      border: '1px solid #cbd5e1',
                      borderRadius: '0.375rem',
                      fontSize: '0.75rem',
                      color: '#475569',
                      cursor: 'pointer',
                    }}
                  >
                    Demo Address
                  </button>
                  <button
                    type="button"
                    onClick={() => setAbhaInput('91-1234-5678-9012')}
                    style={{
                      padding: '0.4rem 0.6rem',
                      backgroundColor: '#f1f5f9',
                      border: '1px solid #cbd5e1',
                      borderRadius: '0.375rem',
                      fontSize: '0.75rem',
                      color: '#475569',
                      cursor: 'pointer',
                    }}
                  >
                    Demo 14-Digit
                  </button>
                  <button
                    type="submit"
                    disabled={verifyLoading || !abhaInput.trim()}
                    data-testid="doctor-verify-abha-btn"
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '0.5rem',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      cursor: verifyLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {verifyLoading ? 'Verifying...' : 'Verify ABHA'}
                  </button>
                </form>

                {verifyMessage && (
                  <p
                    data-testid="verify-message"
                    style={{
                      margin: '0.5rem 0 0 0',
                      fontSize: '0.85rem',
                      color: verifyMessage.startsWith('✓') ? '#166534' : '#b91c1c',
                    }}
                  >
                    {verifyMessage}
                  </p>
                )}
              </div>

              {/* Section 2: ABDM M2 (Care Context Linking) */}
              <div
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '0.75rem',
                  padding: '1.25rem',
                  backgroundColor: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>🔗</span>
                    <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#1e293b' }}>
                      Milestone 2 (M2): Care Context Linking
                    </h3>
                  </div>
                  <span
                    data-testid="care-context-badge"
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      padding: '0.2rem 0.6rem',
                      borderRadius: '9999px',
                      backgroundColor: isLinked ? '#dcfce7' : '#f1f5f9',
                      color: isLinked ? '#166534' : '#475569',
                    }}
                  >
                    {isLinked ? '✓ Care Context Linked' : 'Unlinked'}
                  </span>
                </div>

                <div style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '1rem' }}>
                  <p style={{ margin: '0.25rem 0' }}>
                    <strong>Reference ID:</strong> <code>{statusData?.care_context_reference || 'Not generated'}</code>
                  </p>
                  <p style={{ margin: '0.25rem 0' }}>
                    <strong>Display Name:</strong> {statusData?.care_context_display || `MediKiosk OPD Intake - Token ${hospitalToken}`}
                  </p>
                  {statusData?.care_context_linked_at && (
                    <p style={{ margin: '0.25rem 0' }}>
                      <strong>Linked At:</strong> {new Date(statusData.care_context_linked_at).toLocaleString()}
                    </p>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <button
                    type="button"
                    onClick={handleLinkCareContext}
                    disabled={linkLoading}
                    data-testid="link-care-context-btn"
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: isLinked ? '#10b981' : '#0284c7',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '0.5rem',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      cursor: linkLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {linkLoading ? 'Linking...' : isLinked ? 'Re-link Care Context (M2)' : '🔗 Link Care Context (M2)'}
                  </button>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                    Registers MediKiosk OPD encounter to patient health record under ABDM.
                  </span>
                </div>

                {linkMessage && (
                  <p
                    data-testid="link-message"
                    style={{
                      margin: '0.5rem 0 0 0',
                      fontSize: '0.85rem',
                      color: linkMessage.startsWith('✓') ? '#166534' : '#b91c1c',
                    }}
                  >
                    {linkMessage}
                  </p>
                )}
              </div>

              {/* Section 3: HIS Interoperability */}
              <div
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '0.75rem',
                  padding: '1.25rem',
                  backgroundColor: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>📤</span>
                    <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#1e293b' }}>
                      Hospital Information System (HIS / EMR) Interoperability
                    </h3>
                  </div>
                  <span
                    data-testid="his-status-badge"
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      padding: '0.2rem 0.6rem',
                      borderRadius: '9999px',
                      backgroundColor: isDispatched ? '#dcfce7' : '#f1f5f9',
                      color: isDispatched ? '#166534' : '#475569',
                    }}
                  >
                    {isDispatched ? '✓ Dispatched & Acknowledged' : 'Not Dispatched'}
                  </span>
                </div>

                <div style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '1rem' }}>
                  <p style={{ margin: '0.25rem 0' }}>
                    <strong>Attached Payload:</strong> Phase 10 HL7 FHIR R4 Document Bundle (LOINC <code>34105-7</code>)
                  </p>
                  {statusData?.his_dispatch_receipt && (
                    <div
                      style={{
                        margin: '0.5rem 0',
                        padding: '0.5rem 0.75rem',
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '0.375rem',
                        fontSize: '0.85rem',
                      }}
                    >
                      <div><strong>Receipt ID:</strong> <code>{String(statusData.his_dispatch_receipt.receipt_id || '')}</code></div>
                      <div><strong>Target System:</strong> {String(statusData.his_dispatch_receipt.target_system || '')}</div>
                      <div><strong>Status:</strong> {String(statusData.his_dispatch_receipt.status || '')}</div>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <input
                    type="text"
                    value={targetSystem}
                    onChange={(e) => setTargetSystem(e.target.value)}
                    placeholder="Target HIS System"
                    style={{
                      flex: 1,
                      padding: '0.5rem 0.75rem',
                      borderRadius: '0.5rem',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleDispatchHis}
                    disabled={dispatchLoading}
                    data-testid="dispatch-his-btn"
                    style={{
                      padding: '0.5rem 1.25rem',
                      backgroundColor: isDispatched ? '#10b981' : '#059669',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '0.5rem',
                      fontWeight: 600,
                      fontSize: '0.9rem',
                      cursor: dispatchLoading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {dispatchLoading ? 'Dispatching...' : isDispatched ? 'Re-dispatch to HIS' : '📤 Dispatch to Hospital HIS'}
                  </button>
                </div>

                {(dispatchMessage || dispatchResponse) && (
                  <p
                    data-testid="dispatch-message"
                    style={{
                      margin: '0.5rem 0 0 0',
                      fontSize: '0.85rem',
                      color: '#166534',
                    }}
                  >
                    {dispatchMessage || (dispatchResponse && `✓ Receipt: ${dispatchResponse.receipt_reference}`)}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '1rem 1.75rem',
            borderTop: '1px solid #e2e8f0',
            backgroundColor: '#f8fafc',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '0.5rem 1.25rem',
              backgroundColor: '#64748b',
              color: '#ffffff',
              border: 'none',
              borderRadius: '0.5rem',
              fontWeight: 600,
              fontSize: '0.9rem',
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
