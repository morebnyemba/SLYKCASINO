'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { BsExclamationOctagon, BsTrash3 } from 'react-icons/bs';
import { Btn, Drawer, Notice, Panel, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Check { username: string; balance: string; open_bets: number; affiliate_owed: string; is_staff: boolean; can_delete: boolean }

const WIPED = [
  'Login, profile and KYC documents (files included)',
  'Wallet, every transaction and payment record',
  'Bets, multiples, cash-outs and Aviator bets',
  'Bonuses, affiliate account, commissions and payouts',
  'Notifications, chat messages and audit history',
];

/** "Danger zone": permanently delete a player and all their data (superusers only). */
export function DeletePlayer({ playerId }: { playerId: number | string }) {
  const router = useRouter();
  const { accessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const { data: check, refetch } = useApi<Check>(open ? `/players/${playerId}/deletion-check/` : null);
  const [typed, setTyped] = useState('');
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const blockers = check ? [
    Number(check.balance) !== 0 && `a balance of $${check.balance}`,
    check.open_bets > 0 && `${check.open_bets} open bet${check.open_bets === 1 ? '' : 's'}`,
    Number(check.affiliate_owed) > 0 && `$${check.affiliate_owed} of affiliate earnings`,
  ].filter(Boolean) as string[] : [];
  const ready = !!check && check.can_delete && typed === check.username && (blockers.length === 0 || force);

  async function remove() {
    if (!accessToken || !check) return;
    setBusy(true); setError('');
    const res = await authedRequest<{ username: string }>('POST', `/players/${playerId}/delete/`, accessToken,
      { confirm: typed, force: blockers.length > 0 && force });
    setBusy(false);
    if (res.error) { setError(res.error); refetch(); return; }
    router.push(`/users?deleted=${encodeURIComponent(check.username)}`);
  }

  return (
    <>
      <Panel title="Danger zone" description="Permanently delete this player and everything linked to them. This can’t be undone."
        actions={<BsExclamationOctagon className="text-live" />}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-sm text-muted-foreground">
            Prefer <b className="text-foreground">Suspend</b> if you may need the records later — deleting removes the player’s
            transactions from every report too.
          </p>
          <Btn variant="danger" icon={BsTrash3} onClick={() => { setOpen(true); setTyped(''); setForce(false); setError(''); }}>
            Delete player permanently
          </Btn>
        </div>
      </Panel>

      <Drawer open={open} onClose={() => setOpen(false)} title="Delete player permanently"
        description="Everything below is erased for good — there is no undo."
        footer={<>
          <Btn onClick={() => setOpen(false)}>Cancel</Btn>
          <Btn variant="danger" icon={BsTrash3} busy={busy} disabled={!ready} onClick={remove}>Delete forever</Btn>
        </>}>
        {!check ? <div className="h-40 animate-pulse rounded-xl bg-muted/50" /> : (
          <div className="space-y-5 text-sm">
            {!check.can_delete && (
              <Notice tone="red">
                {check.is_staff ? 'This is a staff account and can’t be deleted here.' : 'Only a superuser can permanently delete players.'}
              </Notice>
            )}
            <div>
              <p className="mb-2 font-semibold">What gets deleted</p>
              <ul className="list-disc space-y-1 pl-5 text-muted-foreground">{WIPED.map((w) => <li key={w}>{w}</li>)}</ul>
              <p className="mt-2 text-xs text-muted-foreground">
                An affiliate who referred this player keeps the commission they already earned. One audit entry records the deletion.
              </p>
            </div>
            {blockers.length > 0 && (
              <div className="rounded-xl border border-live/40 bg-live/10 p-3">
                <p className="font-semibold text-live">This player still has {blockers.join(', ')}.</p>
                <p className="mt-1 text-muted-foreground">Settle or pay it out first — or tick below to delete anyway and discard it.</p>
                <label className="mt-2 flex items-center gap-2 font-semibold">
                  <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="h-4 w-4 accent-[hsl(0_80%_55%)]" />
                  Delete anyway and discard {blockers.length === 1 ? 'it' : 'them'}
                </label>
              </div>
            )}
            <label className="block space-y-1.5">
              <span className="font-semibold">Type <code className="rounded bg-muted px-1.5 py-0.5">{check.username}</code> to confirm</span>
              <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" disabled={!check.can_delete} />
            </label>
            {error && <Notice tone="red">{error}</Notice>}
          </div>
        )}
      </Drawer>
    </>
  );
}
