'use client';

import { config } from '@/lib/config';

/** Affiliate link tracking: `?ref=CODE` (optional `campaign`/`utm_campaign`) is
 * remembered for 30 days so a visitor who signs up later is still attributed. */

const KEY = 'slyk_ref';
const TTL_MS = 30 * 24 * 3600 * 1000;

interface StoredRef { code: string; campaign: string; at: number }

function read(): StoredRef | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const ref = JSON.parse(raw) as StoredRef;
    if (!ref.code || Date.now() - ref.at > TTL_MS) {
      localStorage.removeItem(KEY);
      return null;
    }
    return ref;
  } catch {
    return null;
  }
}

/** Store the ref from the current URL (last click wins) and log one click per session. */
export function captureReferral(): void {
  let params: URLSearchParams;
  try { params = new URLSearchParams(window.location.search); } catch { return; }
  const code = (params.get('ref') ?? '').replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 24);
  if (!code) return;
  const campaign = (params.get('campaign') ?? params.get('utm_campaign') ?? '').slice(0, 50);
  try { localStorage.setItem(KEY, JSON.stringify({ code, campaign, at: Date.now() })); } catch { /* storage off */ }
  const seen = `slyk_ref_click:${code}`;
  try {
    if (sessionStorage.getItem(seen)) return;
    sessionStorage.setItem(seen, '1');
  } catch { /* still log */ }
  void fetch(`${config.apiUrl}/affiliates/click/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, campaign, landing: window.location.pathname }),
  }).catch(() => {});
}

export function getReferral(): { ref: string; ref_campaign: string } | null {
  const ref = read();
  return ref ? { ref: ref.code, ref_campaign: ref.campaign } : null;
}

/** A code typed in at sign-up (overrides any stored link). */
export function setReferral(code: string): void {
  const clean = code.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 24);
  if (!clean) return;
  const campaign = read()?.code === clean ? read()!.campaign : '';
  try { localStorage.setItem(KEY, JSON.stringify({ code: clean, campaign, at: Date.now() })); } catch { /* ignore */ }
}

export function clearReferral(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
