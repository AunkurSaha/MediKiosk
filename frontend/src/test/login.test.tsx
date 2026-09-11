import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/client';
import { AuthProvider, useAuth } from '../context/AuthContext';
import Login from '../routes/login';

function renderLogin() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </BrowserRouter>,
  );
}

describe('Login Component & Auth Flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
    sessionStorage.setItem('medikiosk.logged_out', 'true');
    vi.spyOn(api, 'config').mockResolvedValue({
      demo_mode: true,
      phase: '12',
      languages: ['en', 'bn', 'hi'],
      normalization_provider: 'mock',
      speech_provider: 'mock',
      ocr_provider: 'mock',
    });
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('AUTH_REQUIRED'));
  });

  it('renders phone input screen with Indian +91 prefix and Send OTP button', async () => {
    renderLogin();
    expect(await screen.findByRole('heading', { name: /MediKiosk/ })).toBeVisible();
    expect(screen.getByText('Patient Login')).toBeVisible();
    expect(screen.getByLabelText('Mobile Number')).toBeVisible();
    expect(screen.getByText('+91')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Send OTP' })).toBeVisible();
  });

  it('rejects empty or invalid phone numbers with clear error message', async () => {
    renderLogin();
    const input = await screen.findByLabelText('Mobile Number');
    const submitBtn = screen.getByRole('button', { name: 'Send OTP' });

    // Try sending with empty input
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.click(submitBtn);

    expect(
      await screen.findByText('Please enter a valid 10-digit Indian mobile number.'),
    ).toBeVisible();
  });

  it('transitions to 6-digit OTP screen upon successful OTP request', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue({
      success: true,
      message: 'OTP sent',
      expires_in: 300,
      cooldown_seconds: 60,
      delivery_mode: 'mock',
      masked_phone: '+91******3210',
    });

    renderLogin();
    const input = await screen.findByLabelText('Mobile Number');
    fireEvent.change(input, { target: { value: '9876543210' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }));

    expect(await screen.findByText('+91******3210')).toBeVisible();
    expect(screen.getByText(/Development Mode · Mock SMS delivery active/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Verify OTP' })).toBeVisible();
    expect(screen.getByRole('button', { name: /Resend OTP/ })).toBeDisabled();

    // 6 digit boxes present
    for (let i = 1; i <= 6; i++) {
      expect(screen.getByLabelText(`Digit ${i}`)).toBeVisible();
    }
  });

  it('allows filling OTP digits and submitting verification', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue({
      success: true,
      message: 'OTP sent',
      expires_in: 300,
      cooldown_seconds: 60,
      delivery_mode: 'mock',
      masked_phone: '+91******3210',
    });
    vi.spyOn(api, 'verifyOtp').mockResolvedValue({
      success: true,
      user: {
        id: 'patient-uuid',
        name: 'Patient',
        role: 'patient',
        phone_number: '+91******3210',
        phone_verified: true,
      },
      token: 'session-token-xyz',
    });

    renderLogin();
    const phoneInput = await screen.findByLabelText('Mobile Number');
    fireEvent.change(phoneInput, { target: { value: '9876543210' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send OTP' }));

    await screen.findByText('+91******3210');

    // Fill each digit
    for (let i = 1; i <= 6; i++) {
      const box = screen.getByLabelText(`Digit ${i}`);
      fireEvent.change(box, { target: { value: String(i) } });
    }

    const verifyBtn = screen.getByRole('button', { name: 'Verify OTP' });
    expect(verifyBtn).not.toBeDisabled();
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(api.verifyOtp).toHaveBeenCalledWith('9876543210', '123456');
    });
  });

  it('supports quick demo login when demo mode is enabled', async () => {
    vi.spyOn(api, 'demoLogin').mockResolvedValue({
      success: true,
      user: {
        id: 'demo-doctor-id',
        name: 'Synthetic Doctor',
        role: 'doctor',
        phone_number: null,
        phone_verified: false,
      },
      token: 'demo-token',
    });

    renderLogin();
    const demoDoctorBtn = await screen.findByRole('button', { name: 'Quick Demo Doctor Login' });
    expect(demoDoctorBtn).toBeVisible();

    fireEvent.click(demoDoctorBtn);
    await waitFor(() => {
      expect(api.demoLogin).toHaveBeenCalledWith('doctor');
    });
  });

  it('provides logout action that resets session state', async () => {
    vi.spyOn(api, 'logout').mockResolvedValue({ success: true, message: 'Logged out' });

    function TestConsumer() {
      const { user, logout } = useAuth();
      return (
        <div>
          <span data-testid="role">{user?.role || 'anonymous'}</span>
          <button onClick={logout}>Do Logout</button>
        </div>
      );
    }

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>,
    );

    const btn = screen.getByRole('button', { name: 'Do Logout' });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId('role')).toHaveTextContent('anonymous');
      expect(sessionStorage.getItem('medikiosk.logged_out')).toBe('true');
    });
  });
});
