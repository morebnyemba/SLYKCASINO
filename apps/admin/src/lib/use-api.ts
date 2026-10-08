'use client';

import { useCallback, useEffect, useState } from 'react';
import { config } from './config';
import { useAuth } from './auth-context';
import { apiRefresh, getStoredTokens, storeTokens } from './auth';

export function useApi<T>(path: string | null) {
  const { accessToken, logout } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch_ = useCallback(async (p: string, token: string) => {
    setLoading(true);
    setError(null);
    try {
      let res = await fetch(`${config.apiUrl}${p}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
      });

      if (res.status === 401) {
        const stored = getStoredTokens();
        if (stored?.refresh) {
          try {
            const refreshed = await apiRefresh(stored.refresh);
            storeTokens(refreshed);
            res = await fetch(`${config.apiUrl}${p}`, {
              headers: { Authorization: `Bearer ${refreshed.access}` },
              cache: 'no-store',
            });
          } catch (err) {
            // Log out only when the server rejected the session, not on a rate limit.
            if ((err as { expired?: boolean }).expired) logout();
            setError((err as { expired?: boolean }).expired ? 'Session expired' : 'Could not refresh your session — try again in a moment.');
            return;
          }
        } else {
          logout();
          setError('Session expired');
          return;
        }
      }

      if (!res.ok) throw new Error(`API ${res.status}`);
      setData((await res.json()) as T);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [logout]);

  useEffect(() => {
    if (path && accessToken) {
      void fetch_(path, accessToken);
    } else if (!accessToken) {
      setLoading(false);
    }
  }, [path, accessToken, fetch_]);

  const refetch = useCallback(() => {
    if (path && accessToken) void fetch_(path, accessToken);
  }, [path, accessToken, fetch_]);

  return { data, error, loading, refetch };
}

export async function authedPost<T>(
  path: string,
  body: unknown,
  token: string,
): Promise<{ data?: T; error?: string; status: number }> {
  try {
    let res = await fetch(`${config.apiUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });

    if (res.status === 401) {
      const stored = getStoredTokens();
      if (stored?.refresh) {
        const refreshed = await apiRefresh(stored.refresh);
        storeTokens(refreshed);
        res = await fetch(`${config.apiUrl}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${refreshed.access}` },
          body: JSON.stringify(body),
        });
      }
    }

    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = (json as { detail?: string }).detail ?? `API ${res.status}`;
      return { error: msg, status: res.status };
    }
    return { data: json as T, status: res.status };
  } catch (e) {
    return { error: String(e), status: 0 };
  }
}

/** PUT / PATCH / DELETE (and POST) with the same token refresh as authedPost. */
export async function authedRequest<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  token: string,
  body?: unknown,
): Promise<{ data?: T; error?: string; status: number; fields?: Record<string, string[]> }> {
  const send = (t: string) => fetch(`${config.apiUrl}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  try {
    let res = await send(token);
    if (res.status === 401) {
      const stored = getStoredTokens();
      if (stored?.refresh) {
        const refreshed = await apiRefresh(stored.refresh);
        storeTokens(refreshed);
        res = await send(refreshed.access);
      }
    }
    if (res.status === 204) return { status: 204 };
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const obj = json as Record<string, unknown>;
      const detail = typeof obj.detail === 'string' ? obj.detail : null;
      // DRF field errors: { field: ["message"] } -> "field: message".
      const fields = detail ? undefined : (obj as Record<string, string[]>);
      const msg = detail ?? Object.entries(fields ?? {})
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(' ') : String(v)}`).join(' · ');
      return { error: msg || `API ${res.status}`, status: res.status, fields };
    }
    return { data: json as T, status: res.status };
  } catch (e) {
    return { error: String(e), status: 0 };
  }
}
