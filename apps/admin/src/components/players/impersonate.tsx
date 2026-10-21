'use client';

import { useState } from 'react';
import { BsBoxArrowUpRight, BsEye, BsShieldExclamation } from 'react-icons/bs';
import { Btn, Drawer, Field, Notice, TextInput, cx } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { authedPost } from '@/lib/use-api';

interface Session { refresh: string; mode: 'view' | 'full'; expires_at: number; username: string }

const REASONS = ['Checking a ticket complaint', 'Reproducing a bug the player reported', 'Walking the player through the site'];

/**
 * "View as player": opens the player site in a new tab, signed in as this
 * player for an hour. View-only by default (any staff); full access can bet
 * and move money and is for superusers. Every start is in the audit log.
 */
export function ImpersonateButton({ playerId, username, size = 'md', className }: {
  playerId: number; username: string; size?: 'sm' | 'md'; className?: string;
}) {
  const { accessToken, user } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'view' | 'full'>('view');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState<string | null>(null);

  async function start() {
    if (!accessToken) return;
    // Open the tab inside the click so popup blockers allow it, then point it at the site.
    const tab = window.open('about:blank', '_blank');
    setBusy(true);
    setError('');
    const res = await authedPost<Session>(`/players/${playerId}/impersonate/`, { mode, reason }, accessToken);
    setBusy(false);
    if (!res.data) {
      tab?.close();
      setError(res.error ?? 'Could not start the session.');
      return;
    }
    // The token rides in the fragment (never sent to a server or logged) and
    // is single-use: the player site swaps it for its own pair on arrival.
    const url = `${config.playerUrl}/impersonate#token=${encodeURIComponent(res.data.refresh)}`;
    if (!tab) { setBlocked(url); return; }  // popup blocked: offer a link instead
    tab.opener = null;
    tab.location.href = url;
    setOpen(false);
    setReason('');
  }

  const option = (value: 'view' | 'full', title: string, body: string, disabled = false) => (
    <label className={cx(
      'flex cursor-pointer gap-3 rounded-xl border p-3.5 transition-colors',
      mode === value ? 'border-secondary bg-secondary/10' : 'border-border hover:bg-muted/50',
      disabled && 'pointer-events-none opacity-50',
    )}>
      <input type="radio" name="imp-mode" className="mt-1" checked={mode === value} disabled={disabled} onChange={() => setMode(value)} />
      <span><span className="block text-sm font-bold">{title}</span><span className="text-xs text-muted-foreground">{body}</span></span>
    </label>
  );

  return (
    <>
      <Btn size={size} icon={BsEye} className={className} onClick={() => { setError(''); setBlocked(null); setMode('view'); setOpen(true); }}>
        View as player
      </Btn>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={`Sign in as ${username}`}
        description="Opens the player site in a new tab, signed in as this player for one hour."
        footer={(
          <>
            <Btn variant="ghost" onClick={() => setOpen(false)}>Cancel</Btn>
            <Btn variant={mode === 'full' ? 'danger' : 'primary'} icon={BsBoxArrowUpRight} busy={busy}
              disabled={reason.trim().length < 3} onClick={start}>
              {mode === 'full' ? 'Act as player' : 'Open read-only view'}
            </Btn>
          </>
        )}
      >
        <div className="space-y-5">
          <div className="space-y-2">
            {option('view', 'View only', 'See exactly what the player sees: balance, tickets, bonuses, messages. Nothing can be changed.')}
            {option('full', 'Full access', user?.isSuperuser
              ? 'Place bets, cash out and move money as the player. Every change is logged against your name.'
              : 'Superusers only.', !user?.isSuperuser)}
          </div>
          {mode === 'full' && (
            <Notice tone="red"><BsShieldExclamation className="mr-1.5 inline" />Real money: anything you do is done to {username}’s account.</Notice>
          )}
          <Field label="Reason" hint="Saved in the audit log with your name.">
            <TextInput autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why do you need to sign in as this player?"
              onKeyDown={(e) => { if (e.key === 'Enter' && reason.trim().length >= 3) void start(); }} />
          </Field>
          <div className="flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button key={r} type="button" onClick={() => setReason(r)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:border-secondary/60 hover:text-foreground">
                {r}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            The new tab replaces any player session open in this browser. End it from the banner at the top of the player site.
          </p>
          {error && <Notice tone="red">{error}</Notice>}
          {blocked && (
            <Notice tone="indigo">
              Your browser blocked the new tab.{' '}
              <a href={blocked} target="_blank" rel="noopener noreferrer" className="font-bold underline" onClick={() => setOpen(false)}>Open the player site</a>
            </Notice>
          )}
        </div>
      </Drawer>
    </>
  );
}
