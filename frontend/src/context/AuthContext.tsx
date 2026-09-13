/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, setAuthToken } from '../api/client';
import type { AuthUser, LoginResult, OtpRequestResult, StaffRegisterPayload } from '../api/client';

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  requestOtp: (phone: string) => Promise<OtpRequestResult>;
  verifyOtp: (phone: string, otp: string) => Promise<LoginResult>;
  demoLogin: (
    role?: 'patient' | 'doctor' | 'triage',
    hospitalId?: string,
    specialty?: string,
  ) => Promise<LoginResult>;
  staffLogin: (
    identifier: string,
    password: string,
    hospitalId?: string,
    specialty?: string,
  ) => Promise<LoginResult>;
  staffRegister: (payload: StaffRegisterPayload) => Promise<LoginResult>;
  staffOtpRequest: (phone: string) => Promise<OtpRequestResult>;
  staffOtpVerify: (phone: string, otp: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function getInitialUser(): AuthUser | null {
  if (typeof window === 'undefined' || typeof sessionStorage === 'undefined') return null;
  const isLoggedOut = sessionStorage.getItem('medikiosk.logged_out') === 'true';
  if (isLoggedOut) return null;

  const stored = sessionStorage.getItem('medikiosk.auth_user');
  if (stored) {
    try {
      return JSON.parse(stored) as AuthUser;
    } catch {
      // ignore JSON parse error
    }
  }

  return null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(getInitialUser);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = async () => {
    try {
      if (typeof api.getMe === 'function') {
        const me = await api.getMe();
        if (me) {
          setUser(me);
          setError(null);
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(me));
          }
          return;
        }
      }
    } catch {
      const isLoggedOut =
        typeof sessionStorage !== 'undefined' &&
        sessionStorage.getItem('medikiosk.logged_out') === 'true';
      if (isLoggedOut) {
        setUser(null);
        if (typeof sessionStorage !== 'undefined') {
          sessionStorage.removeItem('medikiosk.auth_user');
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    if (typeof api.getMe === 'function') {
      try {
        const res = api.getMe();
        if (res && typeof res.then === 'function') {
          res
            .then((me) => {
              if (active && me) {
                setUser(me);
                setError(null);
                if (typeof sessionStorage !== 'undefined') {
                  sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(me));
                }
              }
            })
            .catch(() => {
              if (active) {
                const isLoggedOut =
                  typeof sessionStorage !== 'undefined' &&
                  sessionStorage.getItem('medikiosk.logged_out') === 'true';
                if (isLoggedOut) {
                  setUser(null);
                  if (typeof sessionStorage !== 'undefined') {
                    sessionStorage.removeItem('medikiosk.auth_user');
                  }
                }
              }
            })
            .finally(() => {
              if (active) setLoading(false);
            });
        }
      } catch {
        // Safe fallback in mock test environments
      }
    }
    return () => {
      active = false;
    };
  }, []);

  const requestOtp = async (phone: string): Promise<OtpRequestResult> => {
    setError(null);
    return await api.requestOtp(phone);
  };

  const verifyOtp = async (phone: string, otp: string): Promise<LoginResult> => {
    setError(null);
    const result = await api.verifyOtp(phone, otp);
    if (result.success && result.user) {
      setUser(result.user);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('medikiosk.logged_out');
        sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(result.user));
      }
      if (result.token) {
        setAuthToken(result.token);
      }
    }
    return result;
  };

  const demoLogin = async (
    role: 'patient' | 'doctor' | 'triage' = 'patient',
    hospitalId?: string,
    specialty?: string,
  ): Promise<LoginResult> => {
    setError(null);
    const result = await api.demoLogin(role, hospitalId, specialty);
    if (result.success && result.user) {
      setUser(result.user);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('medikiosk.logged_out');
        sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(result.user));
      }
      if (result.token) {
        setAuthToken(result.token);
      }
    }
    return result;
  };

  const staffLogin = async (
    identifier: string,
    password: string,
    hospitalId?: string,
    specialty?: string,
  ): Promise<LoginResult> => {
    setError(null);
    const result = await api.staffLogin(identifier, password, hospitalId, specialty);
    if (result.success && result.user) {
      setUser(result.user);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('medikiosk.logged_out');
        sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(result.user));
      }
      if (result.token) {
        setAuthToken(result.token);
      }
    }
    return result;
  };

  const staffRegister = async (payload: StaffRegisterPayload): Promise<LoginResult> => {
    setError(null);
    const result = await api.staffRegister(payload);
    if (result.success && result.user) {
      setUser(result.user);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('medikiosk.logged_out');
        sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(result.user));
      }
      if (result.token) {
        setAuthToken(result.token);
      }
    }
    return result;
  };

  const staffOtpRequest = async (phone: string): Promise<OtpRequestResult> => {
    setError(null);
    return await api.staffOtpRequest(phone);
  };

  const staffOtpVerify = async (phone: string, otp: string): Promise<LoginResult> => {
    setError(null);
    const result = await api.staffOtpVerify(phone, otp);
    if (result.success && result.user) {
      setUser(result.user);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('medikiosk.logged_out');
        sessionStorage.setItem('medikiosk.auth_user', JSON.stringify(result.user));
      }
      if (result.token) {
        setAuthToken(result.token);
      }
    }
    return result;
  };

  const logout = async (): Promise<void> => {
    try {
      await api.logout();
    } catch {
      // Clean up locally even if network fails
    } finally {
      setAuthToken(null);
      setUser(null);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem('medikiosk.logged_out', 'true');
        sessionStorage.removeItem('medikiosk.auth_user');
      }
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        requestOtp,
        verifyOtp,
        demoLogin,
        staffLogin,
        staffRegister,
        staffOtpRequest,
        staffOtpVerify,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function useOptionalAuth(): AuthContextType | undefined {
  return useContext(AuthContext);
}
