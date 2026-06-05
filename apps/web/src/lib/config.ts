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
