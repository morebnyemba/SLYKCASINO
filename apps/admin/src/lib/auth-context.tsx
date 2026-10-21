'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  type DecodedToken,
  apiLogin,
  apiLogout,
  ACCESS_KEY,
  TOKENS_EVENT,
  clearTokens,
  decodeToken,
  getStoredTokens,
  refreshSession,
  storeTokens,
} from './auth';

interface AdminUser {
  userId: number;
  username: string;
  isStaff: boolean;
  isSuperuser: boolean;
}

interface AuthContextValue {
  user: AdminUser | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function userFromDecoded(decoded: DecodedToken): AdminUser {
  return {
    userId: decoded.user_id,
    username: decoded.username,
    isStaff: decoded.is_staff,
    isSuperuser: decoded.is_superuser,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = getStoredTokens();
    if (!stored) { setIsLoading(false); return; }
    // A page load reuses a still-valid access token instead of refreshing every
    // time: the refresh endpoint is rate-limited, so reloading pages or opening
    // tabs would otherwise log staff out.
    const current = decodeToken(stored.access);
    if (current?.is_staff && current.exp * 1000 > Date.now() + 60_000) {
      setAccessToken(stored.access);
      setUser(userFromDecoded(current));
      setIsLoading(false);
      return;
    }
    refreshSession()
      .then((tokens) => {
        const decoded = decodeToken(tokens.access);
        if (!decoded?.is_staff) { clearTokens(); return; }
        setAccessToken(tokens.access);
        setUser(userFromDecoded(decoded));
      })
      .catch((err: Error & { expired?: boolean }) => {
        if (err.expired) { clearTokens(); return; }
        // Couldn't refresh right now (rate limit, network): keep the session
        // with the stored token; API calls retry the refresh when they need to.
        const decoded = decodeToken(stored.access);
        if (decoded?.is_staff) { setAccessToken(stored.access); setUser(userFromDecoded(decoded)); }
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Keep the token here current when this tab refreshes it (TOKENS_EVENT) or
  // another tab does (storage), and refresh a minute before it runs out so
  // requests don't start with an expired token.
  useEffect(() => {
    const adopt = (access: string | null) => {
      const decoded = access ? decodeToken(access) : null;
      if (!access || !decoded?.is_staff) return;
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

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await apiLogin(username, password);
    storeTokens(tokens);
    setAccessToken(tokens.access);
    const decoded = decodeToken(tokens.access);
    if (decoded) setUser(userFromDecoded(decoded));
  }, []);

  const logout = useCallback(async () => {
    const stored = getStoredTokens();
    if (stored) await apiLogout(stored.access, stored.refresh).catch(() => {});
    clearTokens();
    setAccessToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, accessToken, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
