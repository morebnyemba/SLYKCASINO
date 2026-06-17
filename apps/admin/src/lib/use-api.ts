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
          } catch {
            logout();
            setError('Session expired');
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
