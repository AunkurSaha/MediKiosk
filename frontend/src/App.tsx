import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import Doctor from './routes/doctor';
import Kiosk from './routes/kiosk';
import Login from './routes/login';
import Triage from './routes/triage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { copy } from './i18n';

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const t = copy.en;

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      <header className="site-header">
        <NavLink className="brand" to="/kiosk/language">
          <span className="brand-mark" aria-hidden="true">
            +
          </span>
          {t.brand}
        </NavLink>
        <nav aria-label={t.brand} style={{ alignItems: 'center' }}>
          <NavLink to="/kiosk/language">{t.kiosk}</NavLink>
          <NavLink to="/doctor">{t.doctor}</NavLink>
          <NavLink to="/triage">{t.triage}</NavLink>

          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '12px' }}>
              <span
                style={{
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  color: '#1b5e52',
                  background: '#eef5f2',
                  padding: '4px 10px',
                  borderRadius: '12px',
                }}
              >
                {user.role === 'doctor' ? '👨‍⚕️ Clinician' : `👤 ${user.phone_number || 'Patient'}`}
              </span>
              <button
                type="button"
                className="text-button"
                onClick={handleLogout}
                style={{
                  fontSize: '0.85rem',
                  padding: '4px 8px',
                  minHeight: 'auto',
                  cursor: 'pointer',
                }}
              >
                {t.logout}
              </button>
            </div>
          ) : (
            <NavLink
              to="/login"
              style={{
                background: '#17685c',
                color: '#fff',
                padding: '6px 14px',
                borderRadius: '6px',
                fontWeight: 600,
                textDecoration: 'none',
              }}
            >
              Login
            </NavLink>
          )}
        </nav>
      </header>
      <div className="demo-bar">{t.demo}</div>
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/kiosk/*"
            element={
              <ProtectedRoute requiredRole="patient">
                <Kiosk />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor"
            element={
              <ProtectedRoute requiredRole="doctor">
                <Doctor key={location.pathname} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor/sessions/:sessionId"
            element={
              <ProtectedRoute requiredRole="doctor">
                <Doctor key={location.pathname} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/triage"
            element={
              <ProtectedRoute requiredRole="doctor">
                <Triage />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/kiosk/language" replace />} />
          <Route path="*" element={<Navigate to="/kiosk/language" replace />} />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
