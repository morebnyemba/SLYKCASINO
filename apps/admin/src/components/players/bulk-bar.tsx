'use client';

import { useState } from 'react';
import { BsXLg } from 'react-icons/bs';
import { Btn, Field, Notice, Select, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export type BulkAction =
  | 'suspend' | 'unsuspend' | 'freeze_withdrawals' | 'unfreeze_withdrawals' | 'block_bonus' | 'unblock_bonus' | 'notify'
  | 'delete';

const ACTIONS: { id: BulkAction; label: string; verb: string; danger?: boolean; superuser?: boolean }[] = [
  { id: 'suspend', label: 'Suspend accounts', verb: 'suspend', danger: true },
  { id: 'unsuspend', label: 'Unsuspend accounts', verb: 'unsuspend' },
  { id: 'freeze_withdrawals', label: 'Freeze withdrawals', verb: 'freeze withdrawals for', danger: true },
  { id: 'unfreeze_withdrawals', label: 'Unfreeze withdrawals (superuser)', verb: 'unfreeze withdrawals for', superuser: true },
  { id: 'block_bonus', label: 'Block bonuses', verb: 'block bonuses for', danger: true },
  { id: 'unblock_bonus', label: 'Unblock bonuses (superuser)', verb: 'unblock bonuses for', superuser: true },
  { id: 'notify', label: 'Send a message', verb: 'message' },
  { id: 'delete', label: 'Delete permanently (superuser)', verb: 'delete', danger: true, superuser: true },
];

/** The most players one permanent deletion may cover. */
export const MAX_DELETE = 100;

export interface BulkResult {
  action: BulkAction; requested: number; done: number;
  skipped: { id: number; username: string; reason: string }[]; skipped_count: number;
  failed: { id: number; username: string; error: string }[]; failed_count: number;
  // Permanent deletion: the dry run says what would go, then the typed phrase is required.
  dry_run?: boolean; deletable?: number; balance_discarded?: string; open_bets_discarded?: number; confirm_phrase?: string;
}

/** The selection: chosen ids, or everyone matching the list's filters. */
export interface Selection {
  ids: number[];
  allMatching: boolean;
  count: number;
  filters: { q?: string; kyc?: string; status?: string };
}

/** Sticky bar under the player list: pick one action and apply it to the whole selection. */
export function BulkBar({ selection, onClear, onDone }: {
  selection: Selection; onClear: () => void; onDone: (result: BulkResult) => void;
}) {
  const { accessToken, user } = useAuth();
  const actions = ACTIONS.filter((a) => !a.superuser || user?.isSuperuser);
  const [force, setForce] = useState(false);
  const [review, setReview] = useState<BulkResult | null>(null);
  const [typed, setTyped] = useState('');
  const [action, setAction] = useState<BulkAction>('suspend');
  const [reason, setReason] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = ACTIONS.find((a) => a.id === action)!;
  const n = selection.count;
  const ready = action === 'suspend' ? reason.trim().length >= 3 : action === 'notify' ? title.trim().length >= 3 : true;
  const deleting = action === 'delete';
  const tooMany = deleting && n > MAX_DELETE;
  const which = selection.allMatching ? { all_matching: true, filters: selection.filters } : { ids: selection.ids };

  async function apply(extra: Record<string, unknown> = {}) {
    if (!accessToken) return null;
    setBusy(true); setError('');
    const res = await authedPost<BulkResult>('/players/bulk/', { action, reason, title, body, ...which, ...extra }, accessToken);
    setBusy(false); setConfirming(false);
    if (res.error || !res.data) { setError(res.error ?? 'Something went wrong.'); return null; }
    return res.data;
  }
  const run = async () => { const r = await apply(); if (r) onDone(r); };
  // Permanent deletion: look first (nothing changes), then type the number to confirm.
  const look = async () => { setTyped(''); setReview(await apply({ dry_run: true, force })); };
  const del = async () => {
    const r = await apply({ force, confirm: typed.trim() });
    if (r) onDone(r);
  };

  return (
    <div className="sticky bottom-3 z-30 rounded-2xl border border-border bg-card p-4 shadow-2xl shadow-black/20">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-[150px]">
          <p className="text-sm font-extrabold">{n.toLocaleString()} selected</p>
          <button onClick={onClear} className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground">
            <BsXLg size={9} /> Clear selection
          </button>
        </div>
        <Field label="Action" className="min-w-[220px]">
          <Select value={action} onChange={(e) => { setAction(e.target.value as BulkAction); setConfirming(false); setReview(null); setTyped(''); setError(''); }}>
            {actions.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </Select>
        </Field>
        {action === 'suspend' && (
          <Field label="Reason" hint="Saved on each account." className="min-w-[240px] flex-1">
            <TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={255} placeholder="Linked accounts, same device" />
          </Field>
        )}
        {action === 'notify' && (
          <>
            <Field label="Title" className="min-w-[200px] flex-1">
              <TextInput value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="Maintenance tonight" />
            </Field>
            <Field label="Message" className="min-w-[240px] flex-[2]">
              <TextInput value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} placeholder="Back by 9pm." />
            </Field>
          </>
        )}
        {deleting ? (
          <div className="ml-auto flex items-end gap-3 self-end">
            <label className="flex max-w-[260px] items-start gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={force} onChange={(e) => { setForce(e.target.checked); setReview(null); setTyped(''); }}
                className="mt-0.5 h-4 w-4 accent-[var(--color-live)]" />
              Also delete players who still hold money or have open bets (it is discarded)
            </label>
            <Btn variant="danger" busy={busy} disabled={tooMany} onClick={look}>Review…</Btn>
          </div>
        ) : (
          <div className="ml-auto flex items-end gap-2 self-end">
            {confirming && <Btn variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Btn>}
            <Btn variant={current.danger ? 'danger' : 'primary'} busy={busy} disabled={!ready}
              onClick={() => (confirming ? run() : setConfirming(true))}>
              {confirming ? `Confirm: ${current.verb} ${n.toLocaleString()} player${n === 1 ? '' : 's'}` : 'Apply…'}
            </Btn>
          </div>
        )}
      </div>
      {tooMany && (
        <div className="mt-3"><Notice tone="red">Permanent deletion is limited to {MAX_DELETE} players at a time. Select fewer.</Notice></div>
      )}
      {deleting && review && (
        <div className="mt-3 space-y-3 rounded-xl border border-live/40 bg-live/5 p-4 text-sm">
          <p className="font-bold text-live">
            {review.deletable} of {review.requested} player{review.requested === 1 ? '' : 's'} can be deleted permanently
            {review.skipped_count > 0 && ` · ${review.skipped_count} blocked`}
          </p>
          {review.skipped.slice(0, 5).map((s) => (
            <p key={s.id} className="text-xs text-muted-foreground"><span className="font-semibold text-foreground">{s.username}</span>: {s.reason}</p>
          ))}
          {Number(review.balance_discarded) > 0 || (review.open_bets_discarded ?? 0) > 0 ? (
            <p className="text-xs font-semibold text-live">
              Discards ${Number(review.balance_discarded).toFixed(2)} in balances and {review.open_bets_discarded} open bet(s).
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            This removes each player&rsquo;s login, profile, KYC files, wallet and ledger, bets, bonuses, chats and history. It cannot be undone.
          </p>
          {(review.deletable ?? 0) > 0 && (
            <div className="flex flex-wrap items-end gap-3">
              <Field label={`Type ${review.confirm_phrase} to confirm`} className="min-w-[220px]">
                <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" placeholder={review.confirm_phrase} />
              </Field>
              <Btn variant="danger" busy={busy} disabled={typed.trim() !== review.confirm_phrase} onClick={del}>
                Delete {review.deletable} player{review.deletable === 1 ? '' : 's'} permanently
              </Btn>
            </div>
          )}
        </div>
      )}
      {selection.allMatching && (
        <p className="mt-2 text-xs text-muted-foreground">Applies to everyone matching the current search and filters, not only this page. Staff accounts are never suspended, frozen or blocked here.</p>
      )}
      {error && <div className="mt-3"><Notice tone="red" onClose={() => setError('')}>{error}</Notice></div>}
    </div>
  );
}

/** What a bulk action did: counts, and why some players were skipped or failed. */
export function BulkSummary({ result, onClose }: { result: BulkResult; onClose: () => void }) {
  const label = ACTIONS.find((a) => a.id === result.action)?.label.replace(' (superuser)', '') ?? result.action;
  const problems = result.failed_count > 0;
  return (
    <Notice tone={problems ? 'red' : 'green'} onClose={onClose}>
      <p className="font-semibold">
        {label}: {result.done.toLocaleString()} of {result.requested.toLocaleString()} done
        {result.skipped_count > 0 && ` · ${result.skipped_count} skipped`}{problems && ` · ${result.failed_count} failed`}
      </p>
      {[...result.skipped.map((s) => `${s.username}: ${s.reason}`), ...result.failed.map((f) => `${f.username}: ${f.error}`)].slice(0, 6).map((line) => (
        <p key={line} className="text-xs opacity-90">{line}</p>
      ))}
    </Notice>
  );
}
