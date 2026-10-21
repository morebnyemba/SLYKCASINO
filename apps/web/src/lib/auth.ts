'use client';

import { config } from './config';
import { clearReferral, getReferral } from './referral';

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
  /** Set when staff are signed in as this player (see apps.accounts.impersonation). */
  imp?: number;
  imp_by?: string;
  imp_mode?: 'view' | 'full';
  imp_exp?: number;
}

export const ACCESS_KEY = 'slyk_access';
const REFRESH_KEY = 'slyk_refresh';

export function decodeToken(token: string): DecodedToken | null {
  try {
    // JWTs are base64url; atob wants plain base64 (and UTF-8 names need decoding).
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as DecodedToken;
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
  acceptTerms: boolean,
  currency = 'USD',
): Promise<void> {
  const res = await fetch(`${config.apiUrl}/auth/register/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // Attribute the signup to the affiliate link the visitor came through, if any.
    body: JSON.stringify({ username, email, password, currency, accept_terms: acceptTerms, ...(getReferral() ?? {}) }),
  });
  if (res.ok) { clearReferral(); return; }
  const err = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  // DRF field errors ({"email": ["…"]}) go under their inputs; "detail" is form-wide.
  const fields: Record<string, string> = {};
  for (const [key, value] of Object.entries(err)) {
    if (key !== 'detail') fields[key] = Array.isArray(value) ? value.join(' ') : String(value);
  }
  const detail = typeof err.detail === 'string' ? err.detail : '';
  const fallback = res.status === 429
    ? 'Too many attempts. Please wait a minute and try again.'
    : res.status >= 500 ? 'Our server had a problem creating your account. Please try again shortly.' : 'Registration failed';
  throw new RegisterError(detail || (Object.keys(fields).length ? '' : fallback), fields);
}

/** A failed signup: a form-wide message and/or per-field messages. */
export class RegisterError extends Error {
  constructor(message: string, readonly fields: Record<string, string> = {}) {
    super(message);
    this.name = 'RegisterError';
  }
}

export async function apiRefresh(refresh: string): Promise<AuthTokens> {
  const res = await fetch(`${config.apiUrl}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    // Only a rejected token ends the session; a rate limit or outage doesn't.
    const expired = res.status === 401 || res.status === 400;
    throw Object.assign(new Error(expired ? 'Session expired' : `Refresh failed (${res.status})`), { expired });
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
