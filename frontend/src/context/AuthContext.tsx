/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, setAuthToken } from '../api/client';
import type { AuthUser, LoginResult, OtpRequestResult } from '../api/client';

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  requestOtp: (phone: string) => Promise<OtpRequestResult>;
  verifyOtp: (phone: string, otp: string) => Promise<LoginResult>;
  demoLogin: (role?: 'patient' | 'doctor') => Promise<LoginResult>;
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

  // In development / demo environment, provide route-matched default identity unless explicitly logged out
  const path = window.location.pathname;
  if (path === '/login' || path.startsWith('/login')) {
    return null;
  }
  if (path.startsWith('/doctor') || path.startsWith('/triage')) {
    return {
      id: '00000000-0000-4000-8000-000000000001',
      name: 'Demo Doctor',
      role: 'doctor',
      phone_number: null,
      phone_verified: false,
    };
  }
  return {
    id: 'demo-patient-0001',
    name: 'Demo Patient',
    role: 'patient',
    phone_number: '+919999999999',
    phone_verified: true,
  };
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

  const demoLogin = async (role: 'patient' | 'doctor' = 'patient'): Promise<LoginResult> => {
    setError(null);
    const result = await api.demoLogin(role);
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
