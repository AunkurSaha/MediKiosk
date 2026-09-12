import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { copy } from '../../i18n';

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { requestOtp, verifyOtp, demoLogin } = useAuth();
  const t = copy.en;

  const [step, setStep] = useState<'phone' | 'otp'>('phone');
  const [phone, setPhone] = useState('');
  const [maskedPhone, setMaskedPhone] = useState('');
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [isMockDelivery, setIsMockDelivery] = useState(false);
  const [demoMode, setDemoMode] = useState(false);

  const digitInputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const redirectTarget = searchParams.get('redirect') || '/kiosk/language';
  const reason = searchParams.get('reason');

  // Check config for demo mode
  useEffect(() => {
    api
      .config()
      .then((cfg) => {
        setDemoMode(Boolean(cfg.demo_mode));
      })
      .catch(() => {});
  }, []);

  // Countdown timer for resend
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const handlePhoneSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const cleaned = phone.replace(/[\s\-()]/g, '');
    if (!cleaned) {
      setError(t.enterValidPhone);
      return;
    }

    setBusy(true);
    try {
      const res = await requestOtp(cleaned);
      if (res.success) {
        setMaskedPhone(res.masked_phone);
        setIsMockDelivery(res.delivery_mode === 'mock');
        setCountdown(res.cooldown_seconds || 60);
        setStep('otp');
        setOtpDigits(['', '', '', '', '', '']);
        // Focus first OTP input after render
        setTimeout(() => {
          digitInputRefs.current[0]?.focus();
        }, 100);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === 'INVALID_PHONE') {
          setError(t.enterValidPhone);
        } else if (err.code === 'COOLDOWN_ACTIVE') {
          setError('Please wait before requesting another OTP.');
        } else if (err.code === 'RATE_LIMITED') {
          setError('Too many OTP requests. Please try again later.');
        } else {
          setError(`Request failed (${err.code}).`);
        }
      } else {
        setError('Network error. Check connection and try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleOtpChange = (index: number, value: string) => {
    const digit = value.replace(/\D/g, '').slice(-1);
    const updated = [...otpDigits];
    updated[index] = digit;
    setOtpDigits(updated);

    if (digit && index < 5) {
      digitInputRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) {
      digitInputRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpPaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!pasted) return;
    const updated = [...otpDigits];
    for (let i = 0; i < 6; i++) {
      updated[i] = pasted[i] || '';
    }
    setOtpDigits(updated);
    const nextIdx = Math.min(pasted.length, 5);
    digitInputRefs.current[nextIdx]?.focus();
  };

  const handleOtpSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const fullOtp = otpDigits.join('');
    if (fullOtp.length !== 6) {
      setError(t.enterValidOtp);
      return;
    }

    setBusy(true);
    try {
      const res = await verifyOtp(phone, fullOtp);
      if (res.success) {
        navigate(redirectTarget, { replace: true });
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.code === 'INVALID_OTP') {
          setError('Invalid OTP. Please check the code and try again.');
        } else if (err.code === 'OTP_EXPIRED') {
          setError('The OTP has expired. Please request a new one.');
        } else if (err.code === 'TOO_MANY_ATTEMPTS') {
          setError('Maximum attempts exceeded. Please request a new OTP.');
        } else {
          setError(`Verification failed (${err.code}).`);
        }
      } else {
        setError('Network error. Check connection and try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleResend = async () => {
    if (countdown > 0 || busy) return;
    setError(null);
    setBusy(true);
    try {
      const res = await requestOtp(phone);
      if (res.success) {
        setCountdown(res.cooldown_seconds || 60);
        setOtpDigits(['', '', '', '', '', '']);
        digitInputRefs.current[0]?.focus();
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Resend failed (${err.code}).`);
      } else {
        setError('Network error.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleFillDevOtp = async () => {
    try {
      const res = await api.getDevLastOtp(phone);
      if (res.otp && res.otp.length === 6) {
        const digits = res.otp.split('');
        setOtpDigits(digits);
        digitInputRefs.current[5]?.focus();
      }
    } catch {
      setError('Could not retrieve dev OTP.');
    }
  };

  const handleDemoLogin = async (role: 'doctor' | 'triage') => {
    setError(null);
    setBusy(true);
    try {
      await demoLogin(role);
      navigate(role === 'doctor' ? '/doctor' : '/triage', { replace: true });
    } catch {
      setError('Demo login failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="kiosk" style={{ maxWidth: '500px', margin: '40px auto' }}>
      <div className="card" style={{ padding: '36px' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div
            className="brand-mark"
            style={{ width: '48px', height: '48px', fontSize: '2.2rem', margin: '0 auto 12px' }}
            aria-hidden="true"
          >
            +
          </div>
          <h1 style={{ fontSize: '1.8rem', margin: '0 0 6px' }}>{t.brand}</h1>
          <p className="eyebrow" style={{ margin: 0 }}>
            {step === 'phone' ? t.loginTitle : t.verifyMobile}
          </p>
        </div>

        {reason === 'session_expired' && !error && (
          <div
            role="status"
            style={{
              background: '#fefce8',
              border: '1px solid #fef08a',
              color: '#854d0e',
              padding: '12px 16px',
              borderRadius: '8px',
              fontSize: '0.9rem',
              marginBottom: '20px',
            }}
          >
            Your session has expired. Please log in again with your mobile number.
          </div>
        )}

        {error && (
          <div
            role="alert"
            style={{
              background: '#fdf2f2',
              border: '1px solid #f8b4b4',
              color: '#9b1c1c',
              padding: '12px 16px',
              borderRadius: '8px',
              fontSize: '0.9rem',
              marginBottom: '20px',
            }}
          >
            {error}
          </div>
        )}

        {isMockDelivery && step === 'otp' && (
          <div
            style={{
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              color: '#166534',
              padding: '10px 14px',
              borderRadius: '8px',
              fontSize: '0.85rem',
              marginBottom: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>{t.mockDeliveryNotice}</span>
            <button
              type="button"
              className="text-button"
              onClick={handleFillDevOtp}
              style={{
                color: '#15803d',
                fontWeight: 600,
                textDecoration: 'underline',
                cursor: 'pointer',
                padding: '2px 6px',
                minHeight: 'auto',
              }}
            >
              Fill Test OTP
            </button>
          </div>
        )}

        {step === 'phone' ? (
          <form onSubmit={handlePhoneSubmit}>
            <p className="muted" style={{ marginBottom: '20px', textAlign: 'center' }}>
              {t.loginSubtitle}
            </p>

            <div style={{ marginBottom: '24px' }}>
              <label
                htmlFor="mobile-input"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '8px',
                  fontSize: '0.9rem',
                }}
              >
                {t.mobileNumber}
              </label>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  border: '1px solid #b6cbc0',
                  borderRadius: '10px',
                  overflow: 'hidden',
                  background: '#fafcfb',
                }}
              >
                <span
                  style={{
                    padding: '12px 14px',
                    background: '#eef5f2',
                    fontWeight: 600,
                    color: '#225c53',
                    borderRight: '1px solid #b6cbc0',
                    fontSize: '1rem',
                  }}
                >
                  +91
                </span>
                <input
                  id="mobile-input"
                  type="tel"
                  inputMode="numeric"
                  placeholder="98765 43210"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  disabled={busy}
                  style={{
                    flex: 1,
                    border: 'none',
                    padding: '12px 14px',
                    fontSize: '1.1rem',
                    outline: 'none',
                    background: 'transparent',
                    letterSpacing: '0.05em',
                  }}
                  autoFocus
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              style={{ width: '100%', minHeight: '52px', fontSize: '1rem' }}
            >
              {busy ? t.sendingOtp : t.sendOtp}
            </button>
          </form>
        ) : (
          <form onSubmit={handleOtpSubmit}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <p className="muted" style={{ margin: '0 0 6px' }}>
                {t.otpSentTo}
              </p>
              <p
                style={{ fontSize: '1.2rem', fontWeight: 700, margin: '0 0 8px', color: '#17685c' }}
              >
                {maskedPhone}
              </p>
              <button
                type="button"
                className="text-button"
                onClick={() => setStep('phone')}
                style={{
                  color: '#4b6358',
                  fontSize: '0.85rem',
                  textDecoration: 'underline',
                  padding: 0,
                  minHeight: 'auto',
                }}
              >
                {t.changeNumber}
              </button>
            </div>

            <div style={{ marginBottom: '24px' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  gap: '8px',
                  marginBottom: '16px',
                }}
              >
                {otpDigits.map((digit, idx) => (
                  <input
                    key={idx}
                    ref={(el) => {
                      digitInputRefs.current[idx] = el;
                    }}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleOtpChange(idx, e.target.value)}
                    onKeyDown={(e) => handleOtpKeyDown(idx, e)}
                    onPaste={idx === 0 ? handleOtpPaste : undefined}
                    disabled={busy}
                    aria-label={`Digit ${idx + 1}`}
                    style={{
                      width: '46px',
                      height: '54px',
                      fontSize: '1.4rem',
                      fontWeight: 700,
                      textAlign: 'center',
                      borderRadius: '8px',
                      border: digit ? '2px solid #17685c' : '1px solid #b6cbc0',
                      background: digit ? '#f7faf9' : '#fff',
                      outline: 'none',
                    }}
                  />
                ))}
              </div>

              <div style={{ textAlign: 'center' }}>
                <button
                  type="button"
                  className="text-button"
                  disabled={countdown > 0 || busy}
                  onClick={handleResend}
                  style={{
                    fontSize: '0.9rem',
                    color: countdown > 0 ? '#8a9e96' : '#17685c',
                    fontWeight: 600,
                    minHeight: 'auto',
                    padding: '4px 8px',
                  }}
                >
                  {countdown > 0 ? `Resend OTP (${countdown}s)` : t.resendOtp}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={busy || otpDigits.join('').length !== 6}
              style={{ width: '100%', minHeight: '52px', fontSize: '1rem' }}
            >
              {busy ? t.verifyingOtp : t.verifyOtp}
            </button>
          </form>
        )}

        {/* Option to switch to management / specialist portal */}
        <div
          style={{
            marginTop: '28px',
            padding: '16px 20px',
            borderRadius: '10px',
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            textAlign: 'center',
          }}
        >
          <p style={{ margin: '0 0 4px', fontWeight: 600, fontSize: '0.92rem', color: '#1e293b' }}>
            👨‍⚕️ Clinical Specialist & Staff Portal
          </p>
          <p style={{ margin: '0 0 12px', fontSize: '0.82rem', color: '#64748b' }}>
            Physician consultation workspace & emergency triage management.
          </p>
          <Link
            to="/staff/login"
            className="btn secondary"
            style={{
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 16px',
              fontSize: '0.88rem',
              fontWeight: 600,
            }}
          >
            Staff Password Login →
          </Link>
        </div>

        {demoMode && (
          <div
            style={{
              marginTop: '32px',
              paddingTop: '24px',
              borderTop: '1px solid #e0e9e4',
              textAlign: 'center',
            }}
          >
            <p className="eyebrow" style={{ fontSize: '0.7rem', marginBottom: '12px' }}>
              {t.orLoginWithDemo}
            </p>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
              <button
                type="button"
                className="secondary"
                onClick={() => handleDemoLogin('doctor')}
                disabled={busy}
                style={{ fontSize: '0.85rem', padding: '10px 14px', minHeight: '44px' }}
              >
                {t.demoDoctorLogin}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => handleDemoLogin('triage')}
                disabled={busy}
                style={{ fontSize: '0.85rem', padding: '10px 14px', minHeight: '44px' }}
              >
                Quick Triage Demo
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
