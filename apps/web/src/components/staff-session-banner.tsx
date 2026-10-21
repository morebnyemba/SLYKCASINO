'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';

const left = (ms: number) => {
  const m = Math.max(0, Math.ceil(ms / 60_000));
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m} min`;
};

/**
 * Shown on every page while a staff member is signed in as this player (from
 * the admin portal), so it's never mistaken for the player's own session.
 */
export function StaffSessionBanner() {
  const { user, logout } = useAuth();
  const session = user?.staffSession;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!session) return;
    const t = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(t);
  }, [session]);

  useEffect(() => {
    if (session && now >= session.endsAt) void logout();
  }, [session, now, logout]);

  if (!session) return null;

  async function end() {
    await logout();
    window.close();  // works when the admin portal opened this tab
    window.location.replace('/');
  }

  const readOnly = session.mode !== 'full';
  return (
    // Floats above the content (clear of the sticky header and the mobile tab bar) so it's always in view.
    <div role="status" className={`fixed bottom-[84px] left-1/2 z-[60] flex w-[calc(100%-24px)] max-w-max -translate-x-1/2 flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-2xl px-4 py-2 text-center text-[13px] font-semibold shadow-2xl ring-1 ring-black/20 lg:bottom-4 ${readOnly ? 'bg-amber-400 text-black' : 'bg-red-600 text-white'}`}>
      <span>
        Staff view: {session.by} is signed in as <b>{user?.username}</b>
        {readOnly ? ' · read-only' : ' · full access, changes are real'} · ends in {left(session.endsAt - now)}
      </span>
      <button onClick={() => void end()} className="rounded-md bg-black/80 px-2.5 py-0.5 text-xs font-bold text-white hover:bg-black">
        End session
      </button>
    </div>
  );
}
