'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  type DecodedToken,
  apiLogin,
  apiLogout,
  apiRefresh,
  apiRegister,
  clearTokens,
  decodeToken,
  getStoredTokens,
  storeTokens,
} from './auth';

interface AuthUser {
  userId: number;
  username: string;
  isStaff: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function userFromDecoded(decoded: DecodedToken): AuthUser {
  return { userId: decoded.user_id, username: decoded.username, isStaff: decoded.is_staff };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount try to restore session via stored refresh token.
  useEffect(() => {
    const stored = getStoredTokens();
    if (!stored) { setIsLoading(false); return; }
    apiRefresh(stored.refresh)
      .then((tokens) => {
        storeTokens(tokens);
        setAccessToken(tokens.access);
        const decoded = decodeToken(tokens.access);
        if (decoded) setUser(userFromDecoded(decoded));
      })
      .catch(() => clearTokens())
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await apiLogin(email, password);
    storeTokens(tokens);
    setAccessToken(tokens.access);
    const decoded = decodeToken(tokens.access);
    if (decoded) setUser(userFromDecoded(decoded));
  }, []);

  const register = useCallback(async (username: string, email: string, password: string) => {
    await apiRegister(username, email, password);
    await login(email, password);
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
