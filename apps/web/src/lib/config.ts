// Centralized config for the Player UI.
// NEXT_PUBLIC_* are baked at build time in prod and read live in dev.
export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost/api',
  wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost/ws',
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost',
};

export interface ApiResult<T = unknown> {
  results?: T[];
  error?: string;
  [key: string]: unknown;
}

// Fetch helper for server components hitting the Django REST API. Fails soft so
// the UI still renders while the backend is unseeded during scaffolding.
export async function apiGet<T = unknown>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${config.apiUrl}${path}`, { next: { revalidate: 10 }, ...init });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return (await res.json()) as ApiResult<T>;
  } catch (err) {
    return { error: String(err), results: [] };
  }
}

/**
 * Like apiGet, but follows DRF pagination (`next`) so listings get every row,
 * not just the first page. `complete` is false if a page failed or `maxPages`
 * ran out before the last page; `failed` is true only when a request failed
 * (the API is restarting or unreachable), so callers can retry.
 */
export async function apiGetAll<T = unknown>(
  path: string, maxPages = 10,
): Promise<{ rows: T[]; complete: boolean; failed: boolean }> {
  const rows: T[] = [];
  const sep = path.includes('?') ? '&' : '?';
  for (let page = 1; page <= maxPages; page++) {
    const data = await apiGet<T>(`${path}${sep}page=${page}`);
    if (data.error) return { rows, complete: false, failed: true };
    rows.push(...((data.results ?? []) as T[]));
    if (!data.next) return { rows, complete: true, failed: false };
  }
  return { rows, complete: false, failed: false };
}
