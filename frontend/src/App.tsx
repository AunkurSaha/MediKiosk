import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Doctor from './routes/doctor';
import Kiosk from './routes/kiosk';
import Triage from './routes/triage';
import { copy } from './i18n';

function Shell() {
  const location = useLocation();
  const t = copy.en;
  return (
    <>
      <header className="site-header">
        <NavLink className="brand" to="/kiosk/language">
          <span className="brand-mark" aria-hidden="true">
            +
          </span>
          {t.brand}
        </NavLink>
        <nav aria-label={t.brand}>
          <NavLink to="/kiosk/language">{t.kiosk}</NavLink>
          <NavLink to="/doctor">{t.doctor}</NavLink>
          <NavLink to="/triage">{t.triage}</NavLink>
        </nav>
      </header>
      <div className="demo-bar">{t.demo}</div>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/kiosk/language" replace />} />
          <Route path="/kiosk/*" element={<Kiosk />} />
          <Route path="/doctor" element={<Doctor key={location.pathname} />} />
          <Route path="/doctor/sessions/:sessionId" element={<Doctor key={location.pathname} />} />
          <Route path="/triage" element={<Triage />} />
          <Route path="*" element={<Navigate to="/kiosk/language" replace />} />
        </Routes>
      </main>
    </>
  );
}
export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
