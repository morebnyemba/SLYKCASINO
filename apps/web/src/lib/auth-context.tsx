'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  type DecodedToken,
  apiLogin,
  apiLogout,
  ACCESS_KEY,
  TOKENS_EVENT,
  apiRegister,
  clearTokens,
  decodeToken,
  getStoredTokens,
  refreshSession,
  storeTokens,
} from './auth';

interface AuthUser {
  userId: number;
  username: string;
  isStaff: boolean;
  /** A staff member signed in as this player: who, read-only or not, and until when (ms). */
  staffSession: { by: string; mode: 'view' | 'full'; endsAt: number } | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string, acceptTerms: boolean) => Promise<void>;
  logout: () => Promise<void>;
}

/** Signup succeeded but the automatic sign-in after it did not. */
export class AccountCreatedError extends Error {
  constructor() {
    super('Your account was created, but we could not sign you in automatically. Please log in.');
    this.name = 'AccountCreatedError';
  }
}

const AuthContext = createContext<AuthContextValue | null>(null);

function userFromDecoded(decoded: DecodedToken): AuthUser {
  return {
    userId: decoded.user_id, username: decoded.username, isStaff: decoded.is_staff,
    staffSession: decoded.imp
      ? { by: decoded.imp_by ?? 'staff', mode: decoded.imp_mode ?? 'view', endsAt: (decoded.imp_exp ?? 0) * 1000 }
      : null,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount try to restore session via stored refresh token.
  useEffect(() => {
    // The staff sign-in page replaces the session itself; restoring the old one
    // here could race it and win.
    if (window.location.pathname === '/impersonate') { setIsLoading(false); return; }
    const stored = getStoredTokens();
    if (!stored) { setIsLoading(false); return; }
    refreshSession()
      .then((tokens) => {
        setAccessToken(tokens.access);
        const decoded = decodeToken(tokens.access);
        if (decoded) setUser(userFromDecoded(decoded));
      })
      .catch((err: Error & { expired?: boolean }) => {
        if (err.expired) { clearTokens(); return; }
        // Couldn't refresh right now (rate limit, network): keep the stored session.
        const decoded = decodeToken(stored.access);
        if (decoded) { setAccessToken(stored.access); setUser(userFromDecoded(decoded)); }
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Keep the token here current when this tab refreshes it (TOKENS_EVENT) or
  // another tab does (storage), and refresh a minute before it runs out so
  // requests don't start with an expired token.
  useEffect(() => {
    const adopt = (access: string | null) => {
      const decoded = access ? decodeToken(access) : null;
      if (!access || !decoded) return;
      setAccessToken(access);
      setUser(userFromDecoded(decoded));
    };
    const onTokens = (e: Event) => adopt((e as CustomEvent<string>).detail);
    const onStorage = (e: StorageEvent) => { if (e.key === ACCESS_KEY) adopt(e.newValue); };
    window.addEventListener(TOKENS_EVENT, onTokens);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(TOKENS_EVENT, onTokens);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    const exp = accessToken ? decodeToken(accessToken)?.exp : undefined;
    if (!exp) return;
    const t = window.setTimeout(() => { void refreshSession().catch(() => {}); }, Math.max(5_000, exp * 1000 - Date.now() - 60_000));
    return () => window.clearTimeout(t);
  }, [accessToken]);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiLogin(email, password);
    storeTokens(tokens);
    setAccessToken(tokens.access);
    const decoded = decodeToken(tokens.access);
    if (decoded) setUser(userFromDecoded(decoded));
  }, []);

  const register = useCallback(async (username: string, email: string, password: string, acceptTerms: boolean) => {
    await apiRegister(username, email, password, acceptTerms);
    try {
      await login(email, password);
    } catch {
      // The account exists now; retrying the signup would only say "already taken".
      throw new AccountCreatedError();
    }
  }, [login]);

  const logout = useCallback(async () => {
    const stored = getStoredTokens();
    if (stored) await apiLogout(stored.access, stored.refresh).catch(() => {});
    clearTokens();
    setAccessToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, accessToken, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
