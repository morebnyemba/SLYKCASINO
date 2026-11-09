'use client';

import { useState } from 'react';
import { BsXLg } from 'react-icons/bs';
import { Btn, Field, Notice, Select, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export type BulkAction =
  | 'suspend' | 'unsuspend' | 'freeze_withdrawals' | 'unfreeze_withdrawals' | 'block_bonus' | 'unblock_bonus' | 'notify';

const ACTIONS: { id: BulkAction; label: string; verb: string; danger?: boolean }[] = [
  { id: 'suspend', label: 'Suspend accounts', verb: 'suspend', danger: true },
  { id: 'unsuspend', label: 'Unsuspend accounts', verb: 'unsuspend' },
  { id: 'freeze_withdrawals', label: 'Freeze withdrawals', verb: 'freeze withdrawals for', danger: true },
  { id: 'unfreeze_withdrawals', label: 'Unfreeze withdrawals (superuser)', verb: 'unfreeze withdrawals for' },
  { id: 'block_bonus', label: 'Block bonuses', verb: 'block bonuses for', danger: true },
  { id: 'unblock_bonus', label: 'Unblock bonuses (superuser)', verb: 'unblock bonuses for' },
  { id: 'notify', label: 'Send a message', verb: 'message' },
];

export interface BulkResult {
  action: BulkAction; requested: number; done: number;
  skipped: { id: number; username: string; reason: string }[]; skipped_count: number;
  failed: { id: number; username: string; error: string }[]; failed_count: number;
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
  const { accessToken } = useAuth();
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

  async function apply() {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost<BulkResult>('/players/bulk/', {
      action, reason, title, body,
      ...(selection.allMatching ? { all_matching: true, filters: selection.filters } : { ids: selection.ids }),
    }, accessToken);
    setBusy(false); setConfirming(false);
    if (res.error || !res.data) { setError(res.error ?? 'Something went wrong.'); return; }
    onDone(res.data);
  }

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
          <Select value={action} onChange={(e) => { setAction(e.target.value as BulkAction); setConfirming(false); setError(''); }}>
            {ACTIONS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
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
        <div className="ml-auto flex items-end gap-2 self-end">
          {confirming && <Btn variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Btn>}
          <Btn variant={current.danger ? 'danger' : 'primary'} busy={busy} disabled={!ready}
            onClick={() => (confirming ? apply() : setConfirming(true))}>
            {confirming ? `Confirm: ${current.verb} ${n.toLocaleString()} player${n === 1 ? '' : 's'}` : 'Apply…'}
          </Btn>
        </div>
      </div>
      {selection.allMatching && (
        <p className="mt-2 text-xs text-muted-foreground">Applies to everyone matching the current search and filters, not only this page. Staff accounts are never suspended, frozen or blocked here.</p>
      )}
      {error && <div className="mt-3"><Notice tone="red" onClose={() => setError('')}>{error}</Notice></div>}
    </div>
  );
}

/** What a bulk action did: counts, and why some players were skipped or failed. */
export function BulkSummary({ result, onClose }: { result: BulkResult; onClose: () => void }) {
  const label = ACTIONS.find((a) => a.id === result.action)?.label ?? result.action;
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
