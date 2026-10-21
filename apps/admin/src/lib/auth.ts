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

export const ACCESS_KEY = 'slyk_admin_access';
const REFRESH_KEY = 'slyk_admin_refresh';

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
  window.dispatchEvent(new CustomEvent(TOKENS_EVENT, { detail: tokens.access }));
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function apiLogin(username: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${config.apiUrl}/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Login failed');
  }
  const tokens = (await res.json()) as AuthTokens;
  const decoded = decodeToken(tokens.access);
  if (!decoded?.is_staff) {
    throw new Error('Access denied — staff account required');
  }
  return tokens;
}

export async function apiRefresh(refresh: string): Promise<AuthTokens> {
  const res = await fetch(`${config.apiUrl}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    // Only a rejected token ends the session; a rate limit or outage doesn't.
    const err = new Error(res.status === 401 || res.status === 400 ? 'Session expired' : `Refresh failed (${res.status})`);
    (err as Error & { expired?: boolean }).expired = res.status === 401 || res.status === 400;
    throw err;
  }
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

/** Fired on `window` whenever this tab stores new tokens (detail: the access token). */
export const TOKENS_EVENT = 'slyk:tokens';

let inflight: Promise<AuthTokens> | null = null;

/**
 * Swap the stored refresh token for a new pair, one refresh per tab at a time.
 * Refresh tokens are single-use (rotated, then blacklisted), so parallel
 * refreshes with the same token fail for all but one, which used to log people
 * out whenever several requests hit an expired token together. If another tab
 * rotated the token first, this adopts the pair that tab stored.
 */
export function refreshSession(): Promise<AuthTokens> {
  inflight ??= (async () => {
    const stored = getStoredTokens();
    if (!stored) throw Object.assign(new Error('Session expired'), { expired: true });
    try {
      const tokens = await apiRefresh(stored.refresh);
      storeTokens(tokens);
      return tokens;
    } catch (err) {
      for (const wait of [0, 400, 1200]) {  // the other tab's tokens land shortly after
        if (wait) await new Promise((r) => setTimeout(r, wait));
        const now = getStoredTokens();
        if (now && now.refresh !== stored.refresh) return now;
      }
      throw err;
    }
  })().finally(() => { inflight = null; });
  return inflight;
}
