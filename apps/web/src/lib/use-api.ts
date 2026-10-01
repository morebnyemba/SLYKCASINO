'use client';

import { useCallback, useEffect, useState } from 'react';
import { config } from './config';
import { useAuth } from './auth-context';
import { apiRefresh, getStoredTokens, storeTokens } from './auth';

/**
 * Fetches `path` with the player's token. Pass `{ public: true }` for endpoints that
 * also work logged out (e.g. the game catalogue) so they load for visitors too.
 */
export function useApi<T>(path: string | null, opts: { public?: boolean; allPages?: boolean } = {}) {
  const isPublic = !!opts.public;
  const allPages = !!opts.allPages;
  const { accessToken, logout } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch_ = useCallback(async (p: string, token: string | null) => {
    setLoading(true);
    setError(null);
    try {
      let res = await fetch(`${config.apiUrl}${p}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        cache: 'no-store',
      });

      if (res.status === 401 && token) {
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
      const first = (await res.json()) as T & { next?: string | null; results?: unknown[] };
      if (allPages && Array.isArray(first.results)) {
        // Paginated list: keep requesting ?page=N until the API says there is no next page.
        const results = [...first.results];
        const headers = { Authorization: `Bearer ${getStoredTokens()?.access ?? token ?? ''}` };
        let next = first.next;
        for (let page = 2; next && page <= 200; page++) {
          const more = await fetch(`${config.apiUrl}${p}${p.includes('?') ? '&' : '?'}page=${page}`, { headers, cache: 'no-store' });
          if (!more.ok) throw new Error(`API ${more.status}`);
          const body = (await more.json()) as { next?: string | null; results?: unknown[] };
          results.push(...(body.results ?? []));
          next = body.next;
        }
        setData({ ...first, next: null, results } as T);
      } else {
        setData(first);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [logout, allPages]);

  useEffect(() => {
    if (path && (accessToken || isPublic)) {
      void fetch_(path, accessToken);
    } else if (!accessToken) {
      setLoading(false);
    }
  }, [path, accessToken, isPublic, fetch_]);

  const refetch = useCallback(() => {
    if (path && (accessToken || isPublic)) void fetch_(path, accessToken);
  }, [path, accessToken, isPublic, fetch_]);

  return { data, error, loading, refetch };
}

export async function authedPost<T>(
  path: string,
  body: unknown,
  token: string,
): Promise<{ data?: T; error?: string; status: number; body?: Record<string, unknown> }> {
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
      return { error: msg, status: res.status, body: json as Record<string, unknown> };
    }
    return { data: json as T, status: res.status };
  } catch (e) {
    return { error: String(e), status: 0 };
  }
}
