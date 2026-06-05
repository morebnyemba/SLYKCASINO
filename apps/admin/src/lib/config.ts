// Centralized config for the Admin UI (operator command center).
export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost/api',
  wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost/ws',
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost/admin-portal',
};

export interface ApiResult<T = unknown> {
  results?: T[];
  error?: string;
  [key: string]: unknown;
}

export async function apiGet<T = unknown>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${config.apiUrl}${path}`, { cache: 'no-store', ...init });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return (await res.json()) as ApiResult<T>;
  } catch (err) {
    return { error: String(err), results: [] };
  }
}
