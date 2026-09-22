import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type AuthUser } from '../api/client';
import { AuthProvider } from '../context/AuthContext';
import StaffLogin from '../routes/staff-login';
import Login from '../routes/login';
import { Shell } from '../App';

describe('Staff & Specialist Password Login System', () => {
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
    vi.spyOn(api, 'hospitals').mockResolvedValue({
      items: [
        {
          id: '10000000-0000-4000-8000-000000000001',
          name: 'MediKiosk City Hospital',
          city: 'Kolkata',
          address: 'Central Kolkata',
        },
        {
          id: '10000000-0000-4000-8000-000000000002',
          name: 'MediKiosk Lake Medical Centre',
          city: 'Kolkata',
          address: 'South Kolkata',
        },
      ],
    });
    vi.spyOn(api, 'hospitalDoctors').mockImplementation(async (hospitalId) => ({
      items:
        hospitalId === '10000000-0000-4000-8000-000000000001'
          ? [
              { doctor_id: 'a', name: 'Dr. Ananya Sen', waiting_count: 2 },
              { doctor_id: 'b', name: 'Dr. Rahul Das', waiting_count: 5 },
              { doctor_id: 'c', name: 'Dr. Ishan Gupta', waiting_count: 1 },
              { doctor_id: 'e', name: 'Dr. Nandini Bose', waiting_count: 3 },
              { doctor_id: 'f', name: 'Dr. Arjun Mehta', waiting_count: 4 },
            ]
          : [
              { doctor_id: 'd', name: 'Dr. Mira Roy', waiting_count: 4 },
              { doctor_id: 'g', name: 'Dr. Kabir Khan', waiting_count: 2 },
              { doctor_id: 'h', name: 'Dr. Priyanka Pal', waiting_count: 5 },
              { doctor_id: 'i', name: 'Dr. Sayan Ghosh', waiting_count: 1 },
              { doctor_id: 'j', name: 'Dr. Leena Iyer', waiting_count: 3 },
            ],
    }));
  });

  it('renders staff login page with phone/identifier and password inputs', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Hospital Staff & Specialist Portal')).toBeInTheDocument();
    expect(screen.getByLabelText(/Phone Number or Staff ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign In to Staff Workspace/i })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Switch to Patient Kiosk Intake/i }),
    ).toBeInTheDocument();
  });

  it('populates fields when Doctor quick-fill button is clicked', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    const docFillBtn = await screen.findByRole('button', { name: /Clinician Dr\. Ananya Sen/i });
    fireEvent.click(docFillBtn);

    const idInput = screen.getByLabelText(/Phone Number or Staff ID/i) as HTMLInputElement;
    const passInput = screen.getByLabelText(/^Password$/i) as HTMLInputElement;

    expect(idInput.value).toBe('9876500001');
    expect(passInput.value).toBe('Doctor@123');
  });

  it('shows five demo doctors for each selected hospital with their patient load', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    const cityGroup = await screen.findByTestId('demo-doctor-buttons');
    expect(
      screen.getByRole('button', { name: /MediKiosk City Hospital.*Central Kolkata/i }),
    ).toHaveAttribute('aria-pressed', 'true');
    const lakeHospital = screen.getByRole('button', {
      name: /MediKiosk Lake Medical Centre.*South Kolkata/i,
    });
    expect(cityGroup.querySelectorAll('button[aria-label^="Clinician"]')).toHaveLength(5);
    expect(
      screen.getByRole('button', { name: /Dr\. Rahul Das, 5 waiting patients/i }),
    ).toBeInTheDocument();

    fireEvent.click(lakeHospital);

    expect(lakeHospital).toHaveAttribute('aria-pressed', 'true');
    expect(cityGroup.querySelectorAll('button[aria-label^="Clinician"]')).toHaveLength(5);
    const lakeDoctor = await screen.findByRole('button', {
      name: /Dr\. Priyanka Pal, 5 waiting patients/i,
    });
    fireEvent.click(lakeDoctor);
    expect(screen.getByLabelText(/Phone Number or Staff ID/i)).toHaveValue('9876500023');
    expect(screen.getByLabelText(/Clinical Specialisation/i)).toHaveValue('NEUROLOGY');
  });

  it('keeps both demo hospitals available when the hospital request fails', async () => {
    vi.mocked(api.hospitals).mockRejectedValueOnce(new Error('backend unavailable'));

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('button', { name: /MediKiosk City Hospital.*Central Kolkata/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /MediKiosk Lake Medical Centre.*South Kolkata/i }),
    ).toBeInTheDocument();
  });

  it('populates fields when Triage quick-fill button is clicked', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    const triageFillBtn = await screen.findByRole('button', { name: /Triage: Sister Priya/i });
    fireEvent.click(triageFillBtn);

    const idInput = screen.getByLabelText(/Phone Number or Staff ID/i) as HTMLInputElement;
    const passInput = screen.getByLabelText(/^Password$/i) as HTMLInputElement;

    expect(idInput.value).toBe('9876500002');
    expect(passInput.value).toBe('Triage@123');
  });

  it('authenticates doctor and redirects to /doctor', async () => {
    const mockDoctorUser: AuthUser = {
      id: 'mock-doc-1',
      name: 'Dr. Test Sharma',
      role: 'doctor',
      phone_number: '+919876500001',
      phone_verified: true,
    };

    const staffLoginSpy = vi.spyOn(api, 'staffLogin').mockResolvedValue({
      success: true,
      user: mockDoctorUser,
      token: 'mock-doctor-token',
    });

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/staff/login" element={<StaffLogin />} />
            <Route path="/doctor" element={<div>Doctor Workspace Loaded</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/Phone Number or Staff ID/i), {
      target: { value: '9876500001' },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/i), {
      target: { value: 'Doctor@123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Staff Workspace/i }));

    await waitFor(() => {
      expect(staffLoginSpy).toHaveBeenCalledWith(
        '9876500001',
        'Doctor@123',
        expect.anything(),
        expect.anything(),
      );
      expect(screen.getByText('Doctor Workspace Loaded')).toBeInTheDocument();
    });
  });

  it('authenticates triage staff and redirects to /triage', async () => {
    const mockTriageUser: AuthUser = {
      id: 'mock-triage-1',
      name: 'Sister Test Priya',
      role: 'triage',
      phone_number: '+919876500002',
      phone_verified: true,
    };

    const staffLoginSpy = vi.spyOn(api, 'staffLogin').mockResolvedValue({
      success: true,
      user: mockTriageUser,
      token: 'mock-triage-token',
    });

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/staff/login" element={<StaffLogin />} />
            <Route path="/triage" element={<div>Triage Dashboard Loaded</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    // Switch role to triage
    fireEvent.click(screen.getByRole('button', { name: /Triage Staff/i }));

    fireEvent.change(await screen.findByLabelText(/Phone Number or Staff ID/i), {
      target: { value: '9876500002' },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/i), {
      target: { value: 'Triage@123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Staff Workspace/i }));

    await waitFor(() => {
      expect(staffLoginSpy).toHaveBeenCalledWith('9876500002', 'Triage@123', undefined, undefined);
      expect(screen.getByText('Triage Dashboard Loaded')).toBeInTheDocument();
    });
  });

  it('shows error banner when staff credentials are invalid', async () => {
    vi.spyOn(api, 'staffLogin').mockRejectedValue(new Error('Invalid staff credentials.'));

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <StaffLogin />
        </AuthProvider>
      </MemoryRouter>,
    );

    fireEvent.change(await screen.findByLabelText(/Phone Number or Staff ID/i), {
      target: { value: '9876500001' },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/i), {
      target: { value: 'WrongPassword' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Staff Workspace/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid staff credentials.');
  });

  it('provides switcher link to staff login on patient login page', async () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Login />
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Clinical Specialist & Staff Portal/i)).toBeInTheDocument();
    const staffLink = screen.getByRole('link', { name: /Staff Password Login →/i });
    expect(staffLink).toBeInTheDocument();
    expect(staffLink).toHaveAttribute('href', '/staff/login');
  });

  it('switches to Phone OTP tab and completes staff OTP login', async () => {
    const mockDoctorUser: AuthUser = {
      id: 'doc-otp-1',
      name: 'Dr. OTP Sharma',
      role: 'doctor',
      phone_number: '+919876500001',
      phone_verified: true,
    };

    const otpReqSpy = vi.spyOn(api, 'staffOtpRequest').mockResolvedValue({
      success: true,
      message: 'OTP sent',
      expires_in: 300,
      cooldown_seconds: 30,
      delivery_mode: 'mock',
      masked_phone: '+91******0001',
    });

    const otpVerifySpy = vi.spyOn(api, 'staffOtpVerify').mockResolvedValue({
      success: true,
      user: mockDoctorUser,
      token: 'mock-otp-token',
    });

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/staff/login" element={<StaffLogin />} />
            <Route path="/doctor" element={<div>Doctor Workspace Via OTP</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    // Switch to Phone OTP tab
    fireEvent.click(await screen.findByRole('button', { name: /Phone OTP/i }));
    expect(screen.getByLabelText(/Registered Staff Mobile Number/i)).toBeInTheDocument();

    // Fill phone number and request OTP
    fireEvent.change(screen.getByLabelText(/Registered Staff Mobile Number/i), {
      target: { value: '9876500001' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Send One-Time Password|Send Staff OTP/i }));

    await waitFor(() => {
      expect(otpReqSpy).toHaveBeenCalledWith('9876500001');
      expect(screen.getByText(/Enter 6-Digit Code/i)).toBeInTheDocument();
    });

    // Fill 6 digits
    for (let i = 0; i < 6; i++) {
      fireEvent.change(screen.getByLabelText(`Staff OTP Digit ${i + 1}`), {
        target: { value: '1' },
      });
    }

    fireEvent.click(screen.getByRole('button', { name: /Verify & Enter Workspace/i }));

    await waitFor(() => {
      expect(otpVerifySpy).toHaveBeenCalledWith('9876500001', '111111');
      expect(screen.getByText('Doctor Workspace Via OTP')).toBeInTheDocument();
    });
  });

  it('switches to Sign Up tab and registers new staff member', async () => {
    const mockNewDoctor: AuthUser = {
      id: 'new-doc-1',
      name: 'Dr. New Clinician',
      role: 'doctor',
      phone_number: '+919999988888',
      phone_verified: true,
    };

    const registerSpy = vi.spyOn(api, 'staffRegister').mockResolvedValue({
      success: true,
      user: mockNewDoctor,
      token: 'new-doc-token',
    });

    render(
      <MemoryRouter initialEntries={['/staff/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/staff/login" element={<StaffLogin />} />
            <Route path="/doctor" element={<div>New Doctor Registered</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    // Switch to Sign Up tab
    fireEvent.click(await screen.findByRole('button', { name: /Sign Up/i }));
    expect(screen.getByLabelText(/Full Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Create Password/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Full Name/i), {
      target: { value: 'Dr. New Clinician' },
    });
    fireEvent.change(screen.getByLabelText(/Mobile Number/i), { target: { value: '9999988888' } });
    fireEvent.change(screen.getByLabelText(/Official Email/i), {
      target: { value: 'new@hospital.gov.in' },
    });
    fireEvent.change(screen.getByLabelText(/Create Password/i), { target: { value: 'Secret123' } });

    fireEvent.click(screen.getByRole('button', { name: /Create Staff Account & Sign In/i }));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Dr. New Clinician',
          role: 'doctor',
          phone_number: '9999988888',
          email: 'new@hospital.gov.in',
          password: 'Secret123',
        }),
      );
      expect(screen.getByText('New Doctor Registered')).toBeInTheDocument();
    });
  });

  it('does NOT show Patient intake in navbar when doctor is logged in', async () => {
    sessionStorage.setItem(
      'medikiosk.auth_user',
      JSON.stringify({
        id: 'doc-user-id',
        name: 'Dr. Test Clinician',
        role: 'doctor',
        phone_number: '+919876500001',
        phone_verified: true,
      }),
    );

    render(
      <MemoryRouter initialEntries={['/doctor']}>
        <AuthProvider>
          <Shell />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /Doctor workspace/i })).toBeInTheDocument();
    });

    // Patient intake MUST NOT be in the navigation header for doctor!
    expect(screen.queryByRole('link', { name: /Patient intake/i })).not.toBeInTheDocument();
  });
});
