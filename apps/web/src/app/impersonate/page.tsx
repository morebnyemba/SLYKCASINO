'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { Spinner } from '@slyk/ui/components/spinner';
import { apiLogout, apiRefresh, clearTokens, decodeToken, getStoredTokens, storeTokens } from '@/lib/auth';

/**
 * Landing page for staff "view as player" (opened from the admin portal).
 * The single-use token arrives in the URL fragment, which never reaches a
 * server; it's swapped for a session straight away and wiped from the URL.
 */
export default function ImpersonatePage() {
  const [error, setError] = useState('');
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;  // once, even when dev mode runs effects twice
    started.current = true;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get('token');
    // Where to land (e.g. an agent's dashboard): a path on this site only.
    const next = params.get('next') ?? '';
    const landing = /^\/(?!\/)[\w\-/]*$/.test(next) ? next : '/';
    window.history.replaceState(null, '', window.location.pathname);
    if (!token) { setError('This link has no session in it. Start again from the admin portal.'); return; }
    // Drop whoever was signed in here first (the auth provider skips restoring
    // sessions on this page, so it can't put theirs back over this one).
    const previous = getStoredTokens();
    clearTokens();
    if (previous) void apiLogout(previous.access, previous.refresh).catch(() => {});
    apiRefresh(token)
      .then((tokens) => {
        if (!decodeToken(tokens.access)?.imp) throw new Error('not a staff session');
        storeTokens(tokens);
        // A full load, so every part of the site starts fresh as the player.
        window.location.replace(landing);
      })
      .catch(() => setError('This link has expired or was already used. Start again from the admin portal.'));
  }, []);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center">
      {error ? (
        <>
          <p className="font-bold">Couldn’t open the player’s view</p>
          <p className="max-w-sm text-sm text-muted-foreground">{error}</p>
          <Link href="/" className="text-sm font-semibold text-secondary hover:underline">Go to the home page</Link>
        </>
      ) : (
        <>
          <Spinner size={22} />
          <p className="text-sm text-muted-foreground">Signing in as the player…</p>
        </>
      )}
    </div>
  );
}
