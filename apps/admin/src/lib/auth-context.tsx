'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  type DecodedToken,
  apiLogin,
  apiLogout,
  apiRefresh,
  clearTokens,
  decodeToken,
  getStoredTokens,
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
    apiRefresh(stored.refresh)
      .then((tokens) => {
        const decoded = decodeToken(tokens.access);
        if (!decoded?.is_staff) { clearTokens(); return; }
        storeTokens(tokens);
        setAccessToken(tokens.access);
        setUser(userFromDecoded(decoded));
      })
      .catch(() => clearTokens())
      .finally(() => setIsLoading(false));
  }, []);

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
