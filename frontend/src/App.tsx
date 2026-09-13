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
import StaffLogin from './routes/staff-login';
import Triage from './routes/triage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { copy } from './i18n';
import { BrandLogo } from './components/BrandLogo';

export function Shell() {
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
          <BrandLogo compact />
        </NavLink>
        <nav aria-label={t.brand}>
          {(!user || user.role === 'patient') && <NavLink to="/kiosk/language">{t.kiosk}</NavLink>}
          {user?.role === 'doctor' && <NavLink to="/doctor">{t.doctor}</NavLink>}
          {user?.role === 'triage' && <NavLink to="/triage">{t.triage}</NavLink>}

          {user ? (
            <div className="account-menu">
              <span className="role-pill">
                {user.role === 'doctor'
                  ? 'Clinician'
                  : user.role === 'triage'
                    ? 'Triage staff'
                    : user.phone_number || 'Patient'}
              </span>
              <button type="button" className="text-button nav-logout" onClick={handleLogout}>
                {t.logout}
              </button>
            </div>
          ) : (
            <NavLink to="/login" className="nav-login">
              Login
            </NavLink>
          )}
        </nav>
      </header>
      <div className="demo-bar">{t.demo}</div>
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/staff/login" element={<StaffLogin />} />
          <Route path="/management/login" element={<Navigate to="/staff/login" replace />} />
          <Route
            path="/kiosk/*"
            element={
              <ProtectedRoute allowedRoles={['patient']}>
                <Kiosk />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor"
            element={
              <ProtectedRoute allowedRoles={['doctor']}>
                <Doctor key={location.pathname} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor/sessions/:sessionId"
            element={
              <ProtectedRoute allowedRoles={['doctor']}>
                <Doctor key={location.pathname} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/triage"
            element={
              <ProtectedRoute allowedRoles={['triage']}>
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
