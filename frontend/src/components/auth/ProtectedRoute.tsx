import React, { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: 'patient' | 'doctor' | 'staff';
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
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

  useEffect(() => {
    if (demoMode && requiredRole === 'doctor' && user?.id === 'demo-patient-0001') {
      demoLogin('doctor').catch(() => {});
    }
  }, [demoMode, requiredRole, user, demoLogin]);

  if (loading || (demoMode && requiredRole === 'doctor' && user?.id === 'demo-patient-0001')) {
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

  if (requiredRole === 'doctor' && user.role !== 'doctor') {
    const handleDoctorSwitch = async () => {
      setSwitching(true);
      try {
        await demoLogin('doctor');
        navigate(location.pathname, { replace: true });
      } finally {
        setSwitching(false);
      }
    };

    return (
      <div className="card" style={{ maxWidth: '560px', margin: '60px auto', textAlign: 'center' }}>
        <h2 style={{ fontSize: '1.4rem', color: '#842029', marginBottom: '12px' }}>
          Doctor Access Required
        </h2>
        <div
          role="alert"
          style={{
            background: '#f8d7da',
            color: '#842029',
            padding: '12px 16px',
            borderRadius: '8px',
            marginBottom: '16px',
            fontSize: '0.92rem',
          }}
        >
          This clinical workspace requires verified staff authorization. Your current account role
          is <strong>{user.role}</strong>. A patient mobile verification cannot grant doctor
          privileges.
        </div>
        <p className="muted" style={{ marginBottom: '24px' }}>
          Please sign in with staff credentials or return to your patient intake.
        </p>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
          {demoMode && (
            <button
              type="button"
              onClick={handleDoctorSwitch}
              disabled={switching}
              style={{ minHeight: '44px', padding: '10px 18px' }}
            >
              {switching ? 'Switching…' : 'Sign in as Demo Doctor'}
            </button>
          )}
          <a
            href="/kiosk/language"
            className="btn secondary"
            style={{ textDecoration: 'none', padding: '10px 18px' }}
          >
            Go to Patient Intake
          </a>
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
