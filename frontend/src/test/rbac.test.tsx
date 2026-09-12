import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProtectedRoute } from '../components/auth/ProtectedRoute';
import { AuthProvider } from '../context/AuthContext';
import { Shell } from '../App';
import { api, type AuthUser } from '../api/client';
import { triageApi } from '../api/triage';

describe('Role-Based Access Control (RBAC) - Frontend Guards', () => {
  const patientUser: AuthUser = {
    id: 'patient-123',
    phone_number: '+919876543210',
    phone_verified: true,
    name: 'Patient User',
    role: 'patient',
  };

  const doctorUser: AuthUser = {
    id: 'doctor-123',
    phone_number: null,
    phone_verified: true,
    name: 'Dr. Sharma',
    role: 'doctor',
  };

  const triageUser: AuthUser = {
    id: 'triage-123',
    phone_number: null,
    phone_verified: true,
    name: 'Demo Triage Staff',
    role: 'triage',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    sessionStorage.removeItem('medikiosk.logged_out');
    vi.spyOn(api, 'config').mockResolvedValue({
      demo_mode: true,
      phase: '12',
      languages: ['en', 'bn', 'hi'],
      normalization_provider: 'mock',
      speech_provider: 'mock',
      ocr_provider: 'mock',
    });
  });

  it('blocks patient from doctor route and displays Doctor Access Required', async () => {
    sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(patientUser));
    sessionStorage.setItem('medikiosk.auth.token', 'mock-patient-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(patientUser);

    render(
      <MemoryRouter initialEntries={['/doctor']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/doctor"
              element={
                <ProtectedRoute allowedRoles={['doctor']}>
                  <div>Doctor Secret Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Doctor Access Required')).toBeInTheDocument();
    expect(screen.queryByText('Doctor Secret Content')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Go to Patient Intake/i })).toBeInTheDocument();
  });

  it('blocks patient from triage route and displays Triage Access Required', async () => {
    sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(patientUser));
    sessionStorage.setItem('medikiosk.auth.token', 'mock-patient-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(patientUser);

    render(
      <MemoryRouter initialEntries={['/triage']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/triage"
              element={
                <ProtectedRoute allowedRoles={['triage']}>
                  <div>Triage Secret Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Triage Access Required')).toBeInTheDocument();
    expect(screen.queryByText('Triage Secret Content')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Go to Patient Intake/i })).toBeInTheDocument();
  });

  it('blocks triage staff from doctor route and displays Doctor Access Required', async () => {
    sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(triageUser));
    sessionStorage.setItem('medikiosk.auth.token', 'mock-triage-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(triageUser);

    render(
      <MemoryRouter initialEntries={['/doctor']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/doctor"
              element={
                <ProtectedRoute allowedRoles={['doctor']}>
                  <div>Doctor Secret Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Doctor Access Required')).toBeInTheDocument();
    expect(screen.queryByText('Doctor Secret Content')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Go to Triage Dashboard/i })).toBeInTheDocument();
  });

  it('allows doctor to access doctor protected route', async () => {
    sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(doctorUser));
    sessionStorage.setItem('medikiosk.auth.token', 'mock-doctor-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(doctorUser);

    render(
      <MemoryRouter initialEntries={['/doctor']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/doctor"
              element={
                <ProtectedRoute allowedRoles={['doctor']}>
                  <div>Doctor Secret Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Doctor Secret Content')).toBeInTheDocument();
  });

  it('allows triage staff to access triage protected route', async () => {
    sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(triageUser));
    sessionStorage.setItem('medikiosk.auth.token', 'mock-triage-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(triageUser);

    render(
      <MemoryRouter initialEntries={['/triage']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/triage"
              element={
                <ProtectedRoute allowedRoles={['triage']}>
                  <div>Triage Secret Content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Triage Secret Content')).toBeInTheDocument();
  });

  describe('Header Navigation Role Filtering', () => {
    it('renders only kiosk links for patient; hides doctor and triage navigation', async () => {
      sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(patientUser));
      sessionStorage.setItem('medikiosk.auth.token', 'mock-patient-token');
      vi.spyOn(api, 'getMe').mockResolvedValue(patientUser);

      render(
        <MemoryRouter initialEntries={['/kiosk/language']}>
          <AuthProvider>
            <Shell />
          </AuthProvider>
        </MemoryRouter>,
      );

      const nav = await screen.findByRole('navigation', { name: /MediKiosk/i });
      expect(within(nav).getByRole('link', { name: /Patient intake/i })).toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Doctor workspace/i })).not.toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Triage/i })).not.toBeInTheDocument();
    });

    it('renders only doctor link for doctor; hides kiosk and triage navigation', async () => {
      sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(doctorUser));
      sessionStorage.setItem('medikiosk.auth.token', 'mock-doctor-token');
      vi.spyOn(api, 'getMe').mockResolvedValue(doctorUser);
      vi.spyOn(api, 'sessions').mockResolvedValue({ items: [] });

      render(
        <MemoryRouter initialEntries={['/doctor']}>
          <AuthProvider>
            <Shell />
          </AuthProvider>
        </MemoryRouter>,
      );

      const nav = await screen.findByRole('navigation', { name: /MediKiosk/i });
      expect(within(nav).getByRole('link', { name: /Doctor workspace/i })).toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Patient intake/i })).not.toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Triage/i })).not.toBeInTheDocument();
    });

    it('renders only triage link for triage staff; hides doctor and kiosk navigation', async () => {
      sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(triageUser));
      sessionStorage.setItem('medikiosk.auth.token', 'mock-triage-token');
      vi.spyOn(api, 'getMe').mockResolvedValue(triageUser);
      vi.spyOn(triageApi, 'getAlerts').mockResolvedValue({
        items: [],
        total: 0,
        emergency_count: 0,
        urgent_count: 0,
        acknowledged_count: 0,
      });
      vi.spyOn(triageApi, 'websocketTicket').mockResolvedValue({
        ticket: 'mock-ticket',
      });

      render(
        <MemoryRouter initialEntries={['/triage']}>
          <AuthProvider>
            <Shell />
          </AuthProvider>
        </MemoryRouter>,
      );

      const nav = await screen.findByRole('navigation', { name: /MediKiosk/i });
      expect(within(nav).getByRole('link', { name: /Triage/i })).toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Doctor workspace/i })).not.toBeInTheDocument();
      expect(within(nav).queryByRole('link', { name: /Patient intake/i })).not.toBeInTheDocument();
    });
  });
});
