import { config } from './config';
import { getStoredTokens, refreshSession } from './auth';

/** POST multipart form data with the staff token (refreshing it once on 401). */
export async function authedUpload<T>(path: string, form: FormData, token: string): Promise<{ data?: T; error?: string; status: number }> {
  const send = (t: string) => fetch(`${config.apiUrl}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${t}` }, body: form });
  try {
    let res = await send(token);
    if (res.status === 401 && getStoredTokens()?.refresh) res = await send((await refreshSession()).access);
    const json = await res.json().catch(() => ({}));
    if (!res.ok) return { error: (json as { detail?: string }).detail ?? `Upload failed (${res.status}).`, status: res.status };
    return { data: json as T, status: res.status };
  } catch {
    return { error: 'Upload failed: check your connection and try again.', status: 0 };
  }
}

/** The API's absolute URL for a path the API itself returned (e.g. /api/support/attachments/3/). */
export function apiFileUrl(path: string): string {
  return `${config.apiUrl.replace(/\/api\/?$/, '')}${path}`;
}
