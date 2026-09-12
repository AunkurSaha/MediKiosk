import React, { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'patient' | 'doctor' | 'triage';
  allowedRoles?: ('patient' | 'doctor' | 'triage')[];
}

export function ProtectedRoute({ children, requiredRole, allowedRoles }: ProtectedRouteProps) {
  const { user, loading, demoLogin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [demoMode, setDemoMode] = useState(true);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    try {
      const cfgPromise = api.config?.();
      if (cfgPromise && typeof cfgPromise.then === 'function') {
        cfgPromise
          .then((cfg) => {
            if (cfg) setDemoMode(Boolean(cfg.demo_mode));
          })
          .catch(() => {});
      }
    } catch {
      // Ignore if config not available in mock/unit tests
    }
  }, []);

  if (loading) {
    return (
      <div className="card" style={{ maxWidth: '500px', margin: '60px auto', textAlign: 'center' }}>
        <p className="loading">Checking authentication…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <Navigate
        to={`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  }

  const effectiveAllowedRoles: ('patient' | 'doctor' | 'triage')[] = allowedRoles || (requiredRole ? [requiredRole] : ['patient', 'doctor', 'triage']);
  const isAuthorized = effectiveAllowedRoles.includes(user.role as 'patient' | 'doctor' | 'triage');

  if (!isAuthorized) {
    const isDoctorRequired = effectiveAllowedRoles.length === 1 && effectiveAllowedRoles[0] === 'doctor';
    const isTriageRequired = effectiveAllowedRoles.length === 1 && effectiveAllowedRoles[0] === 'triage';
    const isPatientRequired = effectiveAllowedRoles.length === 1 && effectiveAllowedRoles[0] === 'patient';

    const handleRoleSwitch = async (targetRole: 'doctor' | 'triage') => {
      setSwitching(true);
      try {
        await demoLogin(targetRole);
        navigate(location.pathname, { replace: true });
      } finally {
        setSwitching(false);
      }
    };

    return (
      <div className="card" style={{ maxWidth: '580px', margin: '60px auto', textAlign: 'center' }}>
        <h2 style={{ fontSize: '1.4rem', color: '#842029', marginBottom: '12px' }}>
          {isDoctorRequired
            ? 'Doctor Access Required'
            : isTriageRequired
            ? 'Triage Access Required'
            : isPatientRequired
            ? 'Patient Intake Access Only'
            : 'Access Denied'}
        </h2>
        <div
          role="alert"
          style={{
            background: '#f8d7da',
            color: '#842029',
            padding: '14px 18px',
            borderRadius: '8px',
            marginBottom: '16px',
            fontSize: '0.92rem',
            lineHeight: 1.5,
          }}
        >
          {isDoctorRequired ? (
            <>
              This clinical workspace requires verified staff authorization. Your current account role
              is <strong>{user.role}</strong>. A patient mobile verification cannot grant doctor
              privileges.
            </>
          ) : isTriageRequired ? (
            <>
              This emergency dashboard requires verified triage staff authorization. Your current account
              role is <strong>{user.role}</strong>. Patient accounts cannot access triage alerts.
            </>
          ) : isPatientRequired ? (
            <>
              The kiosk intake journey is reserved for patients. Hospital staff (<strong>{user.role}</strong>)
              should work from their designated clinical workstation.
            </>
          ) : (
            <>
              You are not authorized to view this page. Required role:{' '}
              <strong>{effectiveAllowedRoles.join(' or ')}</strong>. Your role is{' '}
              <strong>{user.role}</strong>.
            </>
          )}
        </div>
        <p className="muted" style={{ marginBottom: '24px' }}>
          {isPatientRequired
            ? 'Please return to your doctor workspace or emergency triage board.'
            : 'Please sign in with authorized staff credentials or return to your patient intake.'}
        </p>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
          {demoMode && isDoctorRequired && (
            <button
              type="button"
              onClick={() => handleRoleSwitch('doctor')}
              disabled={switching}
              style={{ minHeight: '44px', padding: '10px 18px' }}
            >
              {switching ? 'Switching…' : 'Sign in as Demo Doctor'}
            </button>
          )}
          {demoMode && isTriageRequired && (
            <button
              type="button"
              onClick={() => handleRoleSwitch('triage')}
              disabled={switching}
              style={{ minHeight: '44px', padding: '10px 18px' }}
            >
              {switching ? 'Switching…' : 'Sign in as Demo Triage Staff'}
            </button>
          )}
          {!isPatientRequired && (
            <a
              href="/kiosk/language"
              className="btn secondary"
              style={{ textDecoration: 'none', padding: '10px 18px' }}
            >
              Go to Patient Intake
            </a>
          )}
          {user.role === 'doctor' && (
            <a
              href="/doctor"
              className="btn secondary"
              style={{ textDecoration: 'none', padding: '10px 18px' }}
            >
              Go to Doctor Workspace
            </a>
          )}
          {user.role === 'triage' && (
            <a
              href="/triage"
              className="btn secondary"
              style={{ textDecoration: 'none', padding: '10px 18px' }}
            >
              Go to Triage Dashboard
            </a>
          )}
          <a
            href="/login"
            className="btn secondary"
            style={{ textDecoration: 'none', padding: '10px 18px' }}
          >
            Switch Account
          </a>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
