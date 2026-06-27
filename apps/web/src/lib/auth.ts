'use client';

import { config } from './config';

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface DecodedToken {
  user_id: number;
  username: string;
  is_staff: boolean;
  is_superuser: boolean;
  exp: number;
}

const ACCESS_KEY = 'slyk_access';
const REFRESH_KEY = 'slyk_refresh';

export function decodeToken(token: string): DecodedToken | null {
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload)) as DecodedToken;
  } catch {
    return null;
  }
}

export function getStoredTokens(): AuthTokens | null {
  if (typeof window === 'undefined') return null;
  const access = localStorage.getItem(ACCESS_KEY);
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!access || !refresh) return null;
  return { access, refresh };
}

export function storeTokens(tokens: AuthTokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  localStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function apiLogin(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${config.apiUrl}/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as Record<string, unknown>).detail
      ?? Object.values(err as Record<string, string[]>).flat().join(' ');
    throw new Error(String(detail) || 'Login failed');
  }
  return res.json() as Promise<AuthTokens>;
}

export async function apiRegister(
  username: string,
  email: string,
  password: string,
  currency = 'USD',
): Promise<void> {
  const res = await fetch(`${config.apiUrl}/auth/register/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password, currency }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as Record<string, unknown>).detail
      ?? Object.values(err as Record<string, string[]>).flat().join(' ');
    throw new Error(String(detail) || 'Registration failed');
  }
}

export async function apiRefresh(refresh: string): Promise<AuthTokens> {
  const res = await fetch(`${config.apiUrl}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) throw new Error('Session expired');
  return res.json() as Promise<AuthTokens>;
}

export async function apiLogout(access: string, refresh: string): Promise<void> {
  await fetch(`${config.apiUrl}/auth/logout/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
    body: JSON.stringify({ refresh }),
  });
}

export function authedHeaders(access: string): Record<string, string> {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` };
}
