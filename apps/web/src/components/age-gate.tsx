'use client';

import { useEffect, useState } from 'react';

const STORAGE_KEY = 'slyk:age-verified';

/**
 * 18+ confirmation gate shown once per browser (persisted in localStorage).
 * Regulatory/trust requirement for a real-money gambling site.
 */
export function AgeGate() {
  const [state, setState] = useState<'checking' | 'ask' | 'ok' | 'denied'>('checking');

  useEffect(() => {
    try {
      setState(window.localStorage.getItem(STORAGE_KEY) === '1' ? 'ok' : 'ask');
    } catch {
      setState('ask');
    }
  }, []);

  function confirm() {
    try { window.localStorage.setItem(STORAGE_KEY, '1'); } catch { /* ignore */ }
    setState('ok');
  }

  if (state === 'checking' || state === 'ok') return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-card p-6 text-center shadow-xl">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border-4 border-secondary text-lg font-extrabold text-secondary">
          18+
        </div>
        {state === 'denied' ? (
          <>
            <h2 className="mb-2 text-lg font-bold">Sorry, you can&apos;t enter</h2>
            <p className="text-sm text-muted-foreground">
              You must be at least 18 years old to access SLÝKBETS.
            </p>
          </>
        ) : (
          <>
            <h2 className="mb-2 text-lg font-bold">Are you 18 or older?</h2>
            <p className="mb-5 text-sm text-muted-foreground">
              SLÝKBETS is a real-money gambling site licensed in Zimbabwe. You must confirm you are of legal
              age to continue. Please play responsibly.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setState('denied')}
                className="flex-1 rounded-md border border-border px-4 py-2.5 text-sm font-medium hover:bg-accent"
              >
                No, I&apos;m under 18
              </button>
              <button
                onClick={confirm}
                className="flex-1 rounded-md bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90"
              >
                Yes, I&apos;m 18+
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
