import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../../api/client';
import { BrandLogo } from '../../components/BrandLogo';
import type { Hospital } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

type TabMode = 'password' | 'otp' | 'register';

const DEMO_HOSPITAL_OPTIONS: Hospital[] = [
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
];

const SPECIALTY_OPTIONS = [
  { code: 'CARDIOLOGY', label: '❤️ Cardiology (Heart & Chest Pain)' },
  { code: 'NEUROLOGY', label: '🧠 Neurology (Headache & Neurological)' },
  { code: 'GENERAL_MEDICINE', label: '🩺 General Medicine (Fever & General Care)' },
  { code: 'PULMONOLOGY', label: '🫁 Pulmonology (Cough, Breathlessness, Lungs)' },
  { code: 'GASTROENTEROLOGY', label: '🧪 Gastroenterology (Abdominal Pain, GI)' },
  { code: 'AYUSH', label: '🌿 AYUSH (Integrative & Traditional)' },
  { code: 'ORTHOPEDICS', label: '🦴 Orthopedics (Bone & Joint Care)' },
];

const DEMO_DOCTOR_PERSONAS = [
  {
    name: 'Dr. Ananya Sen',
    phone: '9876500001',
    hospitalId: '10000000-0000-4000-8000-000000000001',
    specialty: 'CARDIOLOGY',
    waiting: 2,
  },
  {
    name: 'Dr. Rahul Das',
    phone: '9876500011',
    hospitalId: '10000000-0000-4000-8000-000000000001',
    specialty: 'CARDIOLOGY',
    waiting: 5,
  },
  {
    name: 'Dr. Ishan Gupta',
    phone: '9876500012',
    hospitalId: '10000000-0000-4000-8000-000000000001',
    specialty: 'GENERAL_MEDICINE',
    waiting: 1,
  },
  {
    name: 'Dr. Nandini Bose',
    phone: '9876500013',
    hospitalId: '10000000-0000-4000-8000-000000000001',
    specialty: 'PULMONOLOGY',
    waiting: 3,
  },
  {
    name: 'Dr. Arjun Mehta',
    phone: '9876500014',
    hospitalId: '10000000-0000-4000-8000-000000000001',
    specialty: 'GASTROENTEROLOGY',
    waiting: 4,
  },
  {
    name: 'Dr. Mira Roy',
    phone: '9876500021',
    hospitalId: '10000000-0000-4000-8000-000000000002',
    specialty: 'CARDIOLOGY',
    waiting: 4,
  },
  {
    name: 'Dr. Kabir Khan',
    phone: '9876500022',
    hospitalId: '10000000-0000-4000-8000-000000000002',
    specialty: 'GENERAL_MEDICINE',
    waiting: 2,
  },
  {
    name: 'Dr. Priyanka Pal',
    phone: '9876500023',
    hospitalId: '10000000-0000-4000-8000-000000000002',
    specialty: 'NEUROLOGY',
    waiting: 5,
  },
  {
    name: 'Dr. Sayan Ghosh',
    phone: '9876500024',
    hospitalId: '10000000-0000-4000-8000-000000000002',
    specialty: 'PULMONOLOGY',
    waiting: 1,
  },
  {
    name: 'Dr. Leena Iyer',
    phone: '9876500025',
    hospitalId: '10000000-0000-4000-8000-000000000002',
    specialty: 'AYUSH',
    waiting: 3,
  },
] as const;

export default function StaffLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const { staffLogin, staffOtpRequest, staffOtpVerify, staffRegister } = useAuth();

  const [activeTab, setActiveTab] = useState<TabMode>('password');

  // Common UI states
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(true);
  const [hospitals, setHospitals] = useState<Hospital[]>(DEMO_HOSPITAL_OPTIONS);
  const [waitingCounts, setWaitingCounts] = useState<Record<string, number> | null>(null);

  // Doctor Clinical Affiliation State
  const [loginRole, setLoginRole] = useState<'doctor' | 'triage'>('doctor');
  const [selectedHospitalId, setSelectedHospitalId] = useState<string>(DEMO_HOSPITAL_OPTIONS[0].id);
  const [selectedSpecialty, setSelectedSpecialty] = useState<string>('CARDIOLOGY');

  // Tab 1: Password State
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Tab 2: OTP State
  const [otpStep, setOtpStep] = useState<'request' | 'verify'>('request');
  const [otpPhone, setOtpPhone] = useState('');
  const [maskedPhone, setMaskedPhone] = useState('');
  const [otpDigits, setOtpDigits] = useState<string[]>(['', '', '', '', '', '']);
  const digitInputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Tab 3: Register State
  const [regName, setRegName] = useState('');
  const [regRole, setRegRole] = useState<'doctor' | 'triage'>('doctor');
  const [regPhone, setRegPhone] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regQualification, setRegQualification] = useState('MD, Cardiology');
  const [showRegPassword, setShowRegPassword] = useState(false);

  const queryParams = new URLSearchParams(location.search);
  const redirectParam = queryParams.get('redirect');

  useEffect(() => {
    api
      .config?.()
      .then((cfg) => {
        if (cfg) setDemoMode(Boolean(cfg.demo_mode));
      })
      .catch(() => {});

    api
      .hospitals?.()
      .then((res) => {
        if (res?.items?.length) {
          setHospitals(res.items);
          setSelectedHospitalId(res.items[0].id);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    api
      .hospitalDoctors(selectedHospitalId)
      .then((result) => {
        if (active) {
          setWaitingCounts(
            Object.fromEntries(result.items.map((doctor) => [doctor.name, doctor.waiting_count])),
          );
        }
      })
      .catch(() => {
        if (active) setWaitingCounts({});
      });
    return () => {
      active = false;
    };
  }, [selectedHospitalId]);

  const handleRoleRedirect = (role: string) => {
    if (redirectParam && redirectParam.startsWith('/')) {
      navigate(redirectParam, { replace: true });
    } else if (role === 'doctor') {
      navigate('/doctor', { replace: true });
    } else if (role === 'triage') {
      navigate('/triage', { replace: true });
    } else {
      navigate('/kiosk/language', { replace: true });
    }
  };

  // --------------------------------------------------------------------------
  // Tab 1: Password Login Submit
  // --------------------------------------------------------------------------
  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier.trim() || !password) {
      setError('Please provide your mobile number (or staff ID) and password.');
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const result = await staffLogin(
        identifier.trim(),
        password,
        loginRole === 'doctor' ? selectedHospitalId : undefined,
        loginRole === 'doctor' ? selectedSpecialty : undefined,
      );
      if (result.success && result.user) {
        handleRoleRedirect(result.user.role);
      } else {
        setError('Authentication failed. Please verify your credentials.');
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Invalid staff credentials or unauthorized account.');
      }
    } finally {
      setBusy(false);
    }
  };

  // --------------------------------------------------------------------------
  // Tab 2: OTP Login Flow
  // --------------------------------------------------------------------------
  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanPhone = otpPhone.replace(/\D/g, '');
    if (cleanPhone.length < 10) {
      setError('Please enter a valid 10-digit Indian mobile number.');
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const res = await staffOtpRequest(cleanPhone);
      setMaskedPhone(res.masked_phone || cleanPhone);
      setOtpStep('verify');
      setTimeout(() => digitInputRefs.current[0]?.focus(), 100);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('No staff account found for this mobile number.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleOtpChange = (index: number, val: string) => {
    const digit = val.replace(/\D/g, '').slice(-1);
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

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = otpDigits.join('');
    if (code.length !== 6) {
      setError('Please enter the complete 6-digit OTP.');
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const res = await staffOtpVerify(otpPhone.replace(/\D/g, ''), code);
      if (res.success && res.user) {
        handleRoleRedirect(res.user.role);
      } else {
        setError('Verification failed. Please check your OTP.');
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Invalid OTP code or expired challenge.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleAutoFillDevOtp = async () => {
    try {
      setBusy(true);
      const res = await api.getDevLastOtp(otpPhone.replace(/\D/g, ''));
      if (res.otp && res.otp.length === 6) {
        const arr = res.otp.split('');
        setOtpDigits(arr);
      }
    } catch {
      setError('Unable to fetch dev OTP sink.');
    } finally {
      setBusy(false);
    }
  };

  // --------------------------------------------------------------------------
  // Tab 3: Staff Registration Submit
  // --------------------------------------------------------------------------
  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName.trim()) {
      setError('Please enter the full name.');
      return;
    }
    const cleanPhone = regPhone.replace(/\D/g, '');
    if (cleanPhone.length < 10) {
      setError('Please enter a valid 10-digit mobile number.');
      return;
    }
    if (!regPassword || regPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const result = await staffRegister({
        name: regName.trim(),
        role: regRole,
        phone_number: cleanPhone,
        email: regEmail.trim() || undefined,
        password: regPassword,
        hospital_id: regRole === 'doctor' ? selectedHospitalId : undefined,
        specialty: regRole === 'doctor' ? selectedSpecialty : undefined,
        qualification: regRole === 'doctor' ? regQualification : undefined,
      });

      if (result.success && result.user) {
        handleRoleRedirect(result.user.role);
      } else {
        setError('Registration failed.');
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Registration failed. Mobile or email may already be in use.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleQuickFill = (
    demoId: string,
    demoPass: string,
    role: 'doctor' | 'triage',
    hospitalId?: string,
    specialty?: string,
  ) => {
    setIdentifier(demoId);
    setPassword(demoPass);
    setLoginRole(role);
    if (hospitalId) setSelectedHospitalId(hospitalId);
    if (specialty) setSelectedSpecialty(specialty);
    setError(null);
  };

  return (
    <div className="kiosk" style={{ maxWidth: '720px', margin: '40px auto' }}>
      <div className="card" style={{ padding: '32px' }}>
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <BrandLogo className="auth-brand-logo" />
          <h1 style={{ fontSize: '1.75rem', margin: '0 0 6px' }}>MediKiosk</h1>
          <p
            className="eyebrow"
            style={{
              margin: 0,
              display: 'inline-block',
              background: '#e0f2fe',
              color: '#0369a1',
              padding: '4px 14px',
              borderRadius: '16px',
              fontWeight: 600,
            }}
          >
            Hospital Staff & Specialist Portal
          </p>
        </div>

        <p
          className="muted"
          style={{ marginBottom: '20px', textAlign: 'center', fontSize: '0.88rem' }}
        >
          Authorized access for consulting physicians, medical officers, and emergency triage
          personnel.
        </p>

        {/* Tab Selection */}
        <div
          style={{
            display: 'flex',
            background: '#f1f5f9',
            padding: '4px',
            borderRadius: '8px',
            marginBottom: '22px',
          }}
        >
          <button
            type="button"
            onClick={() => {
              setActiveTab('password');
              setError(null);
            }}
            style={{
              flex: 1,
              padding: '8px 12px',
              fontSize: '0.85rem',
              fontWeight: activeTab === 'password' ? 600 : 500,
              background: activeTab === 'password' ? '#fff' : 'transparent',
              color: activeTab === 'password' ? '#0f172a' : '#64748b',
              border: 'none',
              borderRadius: '6px',
              boxShadow: activeTab === 'password' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              cursor: 'pointer',
            }}
          >
            🔐 Password Login
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('otp');
              setError(null);
            }}
            style={{
              flex: 1,
              padding: '8px 12px',
              fontSize: '0.85rem',
              fontWeight: activeTab === 'otp' ? 600 : 500,
              background: activeTab === 'otp' ? '#fff' : 'transparent',
              color: activeTab === 'otp' ? '#0f172a' : '#64748b',
              border: 'none',
              borderRadius: '6px',
              boxShadow: activeTab === 'otp' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              cursor: 'pointer',
            }}
          >
            📱 Phone OTP
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('register');
              setError(null);
            }}
            style={{
              flex: 1,
              padding: '8px 12px',
              fontSize: '0.85rem',
              fontWeight: activeTab === 'register' ? 600 : 500,
              background: activeTab === 'register' ? '#fff' : 'transparent',
              color: activeTab === 'register' ? '#0f172a' : '#64748b',
              border: 'none',
              borderRadius: '6px',
              boxShadow: activeTab === 'register' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              cursor: 'pointer',
            }}
          >
            ✍️ Sign Up
          </button>
        </div>

        {error && (
          <div
            role="alert"
            style={{
              background: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#991b1b',
              padding: '12px 16px',
              borderRadius: '8px',
              marginBottom: '20px',
              fontSize: '0.88rem',
            }}
          >
            {error}
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* Tab 1: Password Login Form                                         */}
        {/* ------------------------------------------------------------------ */}
        {activeTab === 'password' && (
          <form onSubmit={handlePasswordSubmit}>
            {/* Role Switcher */}
            <div style={{ marginBottom: '16px' }}>
              <label
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.88rem',
                }}
              >
                Accessing As
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setLoginRole('doctor')}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: loginRole === 'doctor' ? '2px solid #0284c7' : '1px solid #cbd5e1',
                    background: loginRole === 'doctor' ? '#f0f9ff' : '#fff',
                    color: loginRole === 'doctor' ? '#0369a1' : '#475569',
                    fontWeight: 600,
                    fontSize: '0.88rem',
                    cursor: 'pointer',
                  }}
                >
                  👨‍⚕️ Doctor / Specialist
                </button>
                <button
                  type="button"
                  onClick={() => setLoginRole('triage')}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: loginRole === 'triage' ? '2px solid #0284c7' : '1px solid #cbd5e1',
                    background: loginRole === 'triage' ? '#f0f9ff' : '#fff',
                    color: loginRole === 'triage' ? '#0369a1' : '#475569',
                    fontWeight: 600,
                    fontSize: '0.88rem',
                    cursor: 'pointer',
                  }}
                >
                  🚨 Triage Staff
                </button>
              </div>
            </div>

            {/* Doctor Clinical Affiliations */}
            {loginRole === 'doctor' && (
              <div
                style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  padding: '14px',
                  marginBottom: '16px',
                }}
              >
                <div style={{ marginBottom: '12px' }}>
                  <label
                    htmlFor="login-hospital"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '4px',
                      fontSize: '0.85rem',
                    }}
                  >
                    🏥 Hospital / Facility
                  </label>
                  <select
                    id="login-hospital"
                    value={selectedHospitalId}
                    onChange={(e) => setSelectedHospitalId(e.target.value)}
                    disabled={busy}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      background: '#fff',
                    }}
                  >
                    {hospitals.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.name} ({h.city || 'Facility'})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="login-specialty"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '4px',
                      fontSize: '0.85rem',
                    }}
                  >
                    🩺 Clinical Specialisation
                  </label>
                  <select
                    id="login-specialty"
                    value={selectedSpecialty}
                    onChange={(e) => setSelectedSpecialty(e.target.value)}
                    disabled={busy}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      background: '#fff',
                    }}
                  >
                    {SPECIALTY_OPTIONS.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            <div style={{ marginBottom: '18px' }}>
              <label
                htmlFor="staff-identifier"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Phone Number or Staff ID
              </label>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <span
                  style={{
                    background: '#f1f5f9',
                    border: '1px solid #cbd5e1',
                    borderRight: 'none',
                    borderRadius: '8px 0 0 8px',
                    padding: '10px 12px',
                    fontSize: '0.95rem',
                    color: '#475569',
                    fontWeight: 600,
                  }}
                >
                  🇮🇳 +91
                </span>
                <input
                  id="staff-identifier"
                  type="text"
                  placeholder="e.g. 9876500001 or doctor@medikiosk.invalid"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  disabled={busy}
                  style={{
                    flex: 1,
                    borderRadius: '0 8px 8px 0',
                    border: '1px solid #cbd5e1',
                    padding: '10px 14px',
                    fontSize: '0.95rem',
                  }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '22px' }}>
              <label
                htmlFor="staff-password"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="staff-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your account password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={busy}
                  style={{
                    width: '100%',
                    padding: '10px 48px 10px 14px',
                    fontSize: '0.95rem',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                    color: '#64748b',
                    padding: '4px',
                    minHeight: 'auto',
                  }}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? '🙈' : '👁️'}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '1rem',
                fontWeight: 600,
                borderRadius: '8px',
                background: '#0284c7',
                color: '#fff',
                border: 'none',
                cursor: busy ? 'not-allowed' : 'pointer',
                marginBottom: '16px',
              }}
            >
              {busy ? 'Verifying Credentials…' : 'Sign In to Staff Workspace'}
            </button>

            {/* Quick Demo Chips */}
            <div
              style={{
                marginTop: '16px',
                paddingTop: '16px',
                borderTop: '1px solid #e5e7eb',
                textAlign: 'center',
              }}
            >
              <div
                aria-label="Choose hospital"
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '8px',
                  marginBottom: '14px',
                }}
              >
                {hospitals.map((hospital) => (
                  <button
                    key={hospital.id}
                    type="button"
                    onClick={() => setSelectedHospitalId(hospital.id)}
                    disabled={busy}
                    aria-pressed={selectedHospitalId === hospital.id}
                    style={{
                      padding: '10px',
                      borderRadius: '8px',
                      border:
                        selectedHospitalId === hospital.id
                          ? '2px solid #0284c7'
                          : '1px solid #cbd5e1',
                      background: selectedHospitalId === hospital.id ? '#f0f9ff' : '#fff',
                      color: selectedHospitalId === hospital.id ? '#0369a1' : '#475569',
                      fontWeight: 600,
                      cursor: busy ? 'not-allowed' : 'pointer',
                    }}
                  >
                    🏥 {hospital.name}
                    <span className="muted" style={{ display: 'block', fontSize: '0.72rem' }}>
                      {hospital.address || hospital.city}
                    </span>
                  </button>
                ))}
              </div>
              <p
                className="eyebrow"
                style={{ fontSize: '0.75rem', marginBottom: '4px', color: '#6b7280' }}
              >
                Clinicians at the selected hospital
              </p>
              <p className="muted" style={{ fontSize: '0.75rem', margin: '0 0 10px' }}>
                Choose a clinician to fill their recording credentials. The badge shows waiting
                patients.
              </p>
              <div
                data-testid="demo-doctor-buttons"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                  gap: '8px',
                }}
              >
                {DEMO_DOCTOR_PERSONAS.filter(
                  (doctor) => !selectedHospitalId || doctor.hospitalId === selectedHospitalId,
                ).map((doctor) => (
                  <button
                    key={doctor.phone}
                    type="button"
                    className="secondary"
                    onClick={() =>
                      handleQuickFill(
                        doctor.phone,
                        'Doctor@123',
                        'doctor',
                        doctor.hospitalId,
                        doctor.specialty,
                      )
                    }
                    disabled={busy}
                    aria-label={`Clinician ${doctor.name}, ${waitingCounts?.[doctor.name] ?? 'counting'} waiting patients`}
                    style={{
                      fontSize: '0.82rem',
                      padding: '9px 11px',
                      minHeight: '48px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: '8px',
                      textAlign: 'left',
                    }}
                  >
                    <span>
                      👨‍⚕️ <strong>{doctor.name}</strong>
                    </span>
                    <span className="badge" title="Waiting patients">
                      {waitingCounts === null
                        ? 'Counting…'
                        : `${waitingCounts[doctor.name] ?? 0} waiting`}
                    </span>
                  </button>
                ))}
                <button
                  type="button"
                  className="secondary"
                  onClick={() => handleQuickFill('9876500002', 'Triage@123', 'triage')}
                  disabled={busy}
                  style={{
                    fontSize: '0.85rem',
                    padding: '8px 12px',
                    minHeight: '38px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span>
                    🚨 <strong>Triage:</strong> Sister Priya
                  </span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    9876500002 · Triage@123
                  </span>
                </button>
              </div>
            </div>
          </form>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* Tab 2: Phone OTP Login Form                                        */}
        {/* ------------------------------------------------------------------ */}
        {activeTab === 'otp' && (
          <div>
            {otpStep === 'request' ? (
              <form onSubmit={handleSendOtp}>
                <div style={{ marginBottom: '18px' }}>
                  <label
                    htmlFor="staff-otp-phone"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '6px',
                      fontSize: '0.9rem',
                    }}
                  >
                    Registered Staff Mobile Number
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span
                      style={{
                        background: '#f1f5f9',
                        border: '1px solid #cbd5e1',
                        borderRight: 'none',
                        borderRadius: '8px 0 0 8px',
                        padding: '10px 12px',
                        fontSize: '0.95rem',
                        color: '#475569',
                        fontWeight: 600,
                      }}
                    >
                      🇮🇳 +91
                    </span>
                    <input
                      id="staff-otp-phone"
                      type="tel"
                      placeholder="Enter 10-digit registered number"
                      value={otpPhone}
                      onChange={(e) => setOtpPhone(e.target.value)}
                      disabled={busy}
                      maxLength={10}
                      style={{
                        flex: 1,
                        borderRadius: '0 8px 8px 0',
                        border: '1px solid #cbd5e1',
                        padding: '10px 14px',
                        fontSize: '0.95rem',
                      }}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={busy}
                  style={{
                    width: '100%',
                    padding: '12px',
                    fontSize: '1rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    background: '#0284c7',
                    color: '#fff',
                    border: 'none',
                    cursor: busy ? 'not-allowed' : 'pointer',
                    marginBottom: '16px',
                  }}
                >
                  {busy ? 'Sending OTP…' : 'Send One-Time Password'}
                </button>

                {/* Quick Staff Numbers */}
                <div
                  style={{
                    marginTop: '16px',
                    paddingTop: '16px',
                    borderTop: '1px solid #e5e7eb',
                    textAlign: 'center',
                  }}
                >
                  <p
                    className="eyebrow"
                    style={{ fontSize: '0.75rem', marginBottom: '8px', color: '#6b7280' }}
                  >
                    Fill Registered Staff Number:
                  </p>
                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setOtpPhone('9876500001')}
                      disabled={busy}
                      style={{ fontSize: '0.85rem', padding: '6px 12px', minHeight: '34px' }}
                    >
                      👨‍⚕️ Doctor: 9876500001
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setOtpPhone('9876500002')}
                      disabled={busy}
                      style={{ fontSize: '0.85rem', padding: '6px 12px', minHeight: '34px' }}
                    >
                      🚨 Triage: 9876500002
                    </button>
                  </div>
                </div>
              </form>
            ) : (
              <form onSubmit={handleVerifyOtp}>
                <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                  <p style={{ margin: '0 0 6px', fontWeight: 600 }}>Enter 6-Digit Code</p>
                  <p className="muted" style={{ margin: 0, fontSize: '0.88rem' }}>
                    Sent to {maskedPhone}{' '}
                    <button
                      type="button"
                      onClick={() => setOtpStep('request')}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#0284c7',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: '0.88rem',
                        textDecoration: 'underline',
                      }}
                    >
                      Change
                    </button>
                  </p>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'center',
                    gap: '8px',
                    marginBottom: '20px',
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
                      disabled={busy}
                      aria-label={`Staff OTP Digit ${idx + 1}`}
                      style={{
                        width: '44px',
                        height: '52px',
                        fontSize: '1.4rem',
                        fontWeight: 700,
                        textAlign: 'center',
                        borderRadius: '8px',
                        border: digit ? '2px solid #0284c7' : '1px solid #cbd5e1',
                        background: digit ? '#f0f9ff' : '#fff',
                        outline: 'none',
                      }}
                    />
                  ))}
                </div>

                {demoMode && (
                  <div style={{ textAlign: 'center', marginBottom: '16px' }}>
                    <button
                      type="button"
                      className="secondary"
                      onClick={handleAutoFillDevOtp}
                      disabled={busy}
                      style={{ fontSize: '0.85rem', padding: '6px 14px', minHeight: '34px' }}
                    >
                      Auto-fill access code
                    </button>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={busy}
                  style={{
                    width: '100%',
                    padding: '12px',
                    fontSize: '1rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    background: '#0284c7',
                    color: '#fff',
                    border: 'none',
                    cursor: busy ? 'not-allowed' : 'pointer',
                  }}
                >
                  {busy ? 'Verifying OTP…' : 'Verify & Enter Workspace'}
                </button>
              </form>
            )}
          </div>
        )}

        {/* ------------------------------------------------------------------ */}
        {/* Tab 3: Staff Sign Up / Registration Form                           */}
        {/* ------------------------------------------------------------------ */}
        {activeTab === 'register' && (
          <form onSubmit={handleRegisterSubmit}>
            <div style={{ marginBottom: '16px' }}>
              <label
                htmlFor="staff-reg-name"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Full Name
              </label>
              <input
                id="staff-reg-name"
                type="text"
                placeholder="e.g. Dr. Jane Doe"
                value={regName}
                onChange={(e) => setRegName(e.target.value)}
                disabled={busy}
                style={{
                  width: '100%',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  padding: '10px 14px',
                  fontSize: '0.95rem',
                }}
              />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Staff Role & Department
              </label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setRegRole('doctor')}
                  style={{
                    flex: 1,
                    padding: '10px',
                    borderRadius: '8px',
                    border: regRole === 'doctor' ? '2px solid #0284c7' : '1px solid #cbd5e1',
                    background: regRole === 'doctor' ? '#f0f9ff' : '#fff',
                    color: regRole === 'doctor' ? '#0369a1' : '#334155',
                    fontWeight: 600,
                    fontSize: '0.88rem',
                    cursor: 'pointer',
                  }}
                >
                  👨‍⚕️ Doctor (Clinician)
                </button>
                <button
                  type="button"
                  onClick={() => setRegRole('triage')}
                  style={{
                    flex: 1,
                    padding: '10px',
                    borderRadius: '8px',
                    border: regRole === 'triage' ? '2px solid #0284c7' : '1px solid #cbd5e1',
                    background: regRole === 'triage' ? '#f0f9ff' : '#fff',
                    color: regRole === 'triage' ? '#0369a1' : '#334155',
                    fontWeight: 600,
                    fontSize: '0.88rem',
                    cursor: 'pointer',
                  }}
                >
                  🚨 Triage (Emergency)
                </button>
              </div>
            </div>

            {/* Doctor specific fields during registration */}
            {regRole === 'doctor' && (
              <div
                style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  padding: '14px',
                  marginBottom: '16px',
                }}
              >
                <div style={{ marginBottom: '12px' }}>
                  <label
                    htmlFor="reg-hospital"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '4px',
                      fontSize: '0.85rem',
                    }}
                  >
                    🏥 Primary Hospital Affiliation
                  </label>
                  <select
                    id="reg-hospital"
                    value={selectedHospitalId}
                    onChange={(e) => setSelectedHospitalId(e.target.value)}
                    disabled={busy}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      background: '#fff',
                    }}
                  >
                    {hospitals.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.name} ({h.city || 'Facility'})
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <label
                    htmlFor="reg-specialty"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '4px',
                      fontSize: '0.85rem',
                    }}
                  >
                    🩺 Primary Specialisation
                  </label>
                  <select
                    id="reg-specialty"
                    value={selectedSpecialty}
                    onChange={(e) => setSelectedSpecialty(e.target.value)}
                    disabled={busy}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      background: '#fff',
                    }}
                  >
                    {SPECIALTY_OPTIONS.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="reg-qual"
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      marginBottom: '4px',
                      fontSize: '0.85rem',
                    }}
                  >
                    🎓 Medical Qualification / Degrees
                  </label>
                  <input
                    id="reg-qual"
                    type="text"
                    placeholder="e.g. MBBS, MD (Cardiology)"
                    value={regQualification}
                    onChange={(e) => setRegQualification(e.target.value)}
                    disabled={busy}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      fontSize: '0.9rem',
                      background: '#fff',
                    }}
                  />
                </div>
              </div>
            )}

            <div style={{ marginBottom: '16px' }}>
              <label
                htmlFor="staff-reg-phone"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Mobile Number
              </label>
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <span
                  style={{
                    background: '#f1f5f9',
                    border: '1px solid #cbd5e1',
                    borderRight: 'none',
                    borderRadius: '8px 0 0 8px',
                    padding: '10px 12px',
                    fontSize: '0.95rem',
                    color: '#475569',
                    fontWeight: 600,
                  }}
                >
                  🇮🇳 +91
                </span>
                <input
                  id="staff-reg-phone"
                  type="tel"
                  placeholder="10-digit mobile number"
                  value={regPhone}
                  onChange={(e) => setRegPhone(e.target.value)}
                  disabled={busy}
                  maxLength={10}
                  style={{
                    flex: 1,
                    borderRadius: '0 8px 8px 0',
                    border: '1px solid #cbd5e1',
                    padding: '10px 14px',
                    fontSize: '0.95rem',
                  }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label
                htmlFor="staff-reg-email"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Official Email (Optional)
              </label>
              <input
                id="staff-reg-email"
                type="email"
                placeholder="e.g. doctor@hospital.gov.in"
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                disabled={busy}
                style={{
                  width: '100%',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  padding: '10px 14px',
                  fontSize: '0.95rem',
                }}
              />
            </div>

            <div style={{ marginBottom: '22px' }}>
              <label
                htmlFor="staff-reg-password"
                style={{
                  display: 'block',
                  fontWeight: 600,
                  marginBottom: '6px',
                  fontSize: '0.9rem',
                }}
              >
                Create Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="staff-reg-password"
                  type={showRegPassword ? 'text' : 'password'}
                  placeholder="At least 6 characters"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  disabled={busy}
                  style={{
                    width: '100%',
                    padding: '10px 48px 10px 14px',
                    fontSize: '0.95rem',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowRegPassword(!showRegPassword)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                    color: '#64748b',
                    padding: '4px',
                    minHeight: 'auto',
                  }}
                  aria-label={showRegPassword ? 'Hide password' : 'Show password'}
                >
                  {showRegPassword ? '🙈' : '👁️'}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '1rem',
                fontWeight: 600,
                borderRadius: '8px',
                background: '#059669',
                color: '#fff',
                border: 'none',
                cursor: busy ? 'not-allowed' : 'pointer',
              }}
            >
              {busy ? 'Creating Staff Account…' : 'Create Staff Account & Sign In'}
            </button>
          </form>
        )}

        {/* Return to Patient Kiosk Switcher */}
        <div style={{ marginTop: '24px', textAlign: 'center' }}>
          <Link
            to="/login"
            style={{
              color: '#15803d',
              fontSize: '0.9rem',
              fontWeight: 500,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            ← Switch to Patient Kiosk Intake
          </Link>
        </div>
      </div>
    </div>
  );
}
