'use client';

import { useState } from 'react';
import { BsXLg } from 'react-icons/bs';
import { Btn, Field, Notice, Select, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

type Decision = 'dismiss' | 'confirm' | 'confirm_delete';

const DECISIONS: { id: Decision; label: string; verb: string; variant: 'success' | 'danger' }[] = [
  { id: 'dismiss', label: 'Dismiss & reinstate', verb: 'dismiss', variant: 'success' },
  { id: 'confirm', label: 'Confirm fraud (keep the accounts, restricted)', verb: 'confirm as fraud', variant: 'danger' },
  { id: 'confirm_delete', label: 'Confirm fraud & delete the players', verb: 'confirm and delete', variant: 'danger' },
];

/** The most cases one permanent deletion may cover. */
export const MAX_PURGE = 100;

export interface CasesResult {
  requested: number; done?: number; dry_run?: boolean; deletable?: number; confirm_phrase?: string;
  balance_forfeited?: string; open_bets_discarded?: number;
  skipped: { case_id: number; username?: string | null; reason: string }[]; skipped_count: number;
  failed: { case_id: number; username: string; error: string }[]; failed_count: number;
}

/** Sticky bar on the fraud list: decide every selected case at once. Deleting reviews first, then needs "DELETE n" typed. */
export function CasesBulkBar({ ids, onClear, onDone }: {
  ids: number[]; onClear: () => void; onDone: (decision: Decision, result: CasesResult) => void;
}) {
  const { accessToken } = useAuth();
  const [decision, setDecision] = useState<Decision>('dismiss');
  const [note, setNote] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [review, setReview] = useState<CasesResult | null>(null);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const current = DECISIONS.find((d) => d.id === decision)!;
  const deleting = decision === 'confirm_delete';
  const n = ids.length;
  const noted = note.trim().length >= 3;

  async function send(extra: Record<string, unknown> = {}) {
    if (!accessToken) return null;
    setBusy(true); setError('');
    const res = await authedPost<CasesResult>('/admin/risk/cases/bulk/', { decision, case_ids: ids, note, ...extra }, accessToken);
    setBusy(false); setConfirming(false);
    if (res.error || !res.data) { setError(res.error ?? 'Something went wrong.'); return null; }
    return res.data;
  }
  const run = async () => { const r = await send(); if (r) onDone(decision, r); };
  const look = async () => { setTyped(''); setReview(await send({ dry_run: true })); };
  const del = async () => { const r = await send({ confirm: typed.trim() }); if (r) onDone(decision, r); };

  return (
    <div className="sticky bottom-3 z-30 rounded-2xl border border-border bg-card p-4 shadow-2xl shadow-black/20">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-[150px]">
          <p className="text-sm font-extrabold">{n.toLocaleString()} case{n === 1 ? '' : 's'} selected</p>
          <button onClick={onClear} className="mt-0.5 inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground">
            <BsXLg size={9} /> Clear selection
          </button>
        </div>
        <Field label="Decision" className="min-w-[260px]">
          <Select value={decision} onChange={(e) => { setDecision(e.target.value as Decision); setConfirming(false); setReview(null); setTyped(''); setError(''); }}>
            {DECISIONS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </Select>
        </Field>
        <Field label="Note for the record" hint="Why — kept with every case." className="min-w-[260px] flex-1">
          <TextInput value={note} onChange={(e) => { setNote(e.target.value); setReview(null); }} maxLength={300} placeholder="Same device and payout numbers across all of them" />
        </Field>
        <div className="ml-auto flex items-end gap-2 self-end">
          {deleting ? (
            <Btn variant="danger" busy={busy} disabled={!noted || n > MAX_PURGE} onClick={look}>Review…</Btn>
          ) : (
            <>
              {confirming && <Btn variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Btn>}
              <Btn variant={current.variant} busy={busy} disabled={!noted} onClick={() => (confirming ? run() : setConfirming(true))}>
                {confirming ? `Confirm: ${current.verb} ${n} case${n === 1 ? '' : 's'}` : 'Apply…'}
              </Btn>
            </>
          )}
        </div>
      </div>
      {deleting && n > MAX_PURGE && (
        <div className="mt-3"><Notice tone="red">Permanent deletion is limited to {MAX_PURGE} cases at a time. Select fewer.</Notice></div>
      )}
      {deleting && review && (
        <div className="mt-3 space-y-3 rounded-xl border border-live/40 bg-live/5 p-4 text-sm">
          <p className="font-bold text-live">
            {review.deletable} of {review.requested} player{review.requested === 1 ? '' : 's'} will be confirmed as fraud and deleted permanently
            {review.skipped_count > 0 && ` · ${review.skipped_count} skipped`}
          </p>
          {review.skipped.slice(0, 5).map((s) => (
            <p key={s.case_id} className="text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Case #{s.case_id}{s.username ? ` (${s.username})` : ''}</span>: {s.reason}
            </p>
          ))}
          <p className="text-xs font-semibold text-live">
            Their money is forfeited: ${Number(review.balance_forfeited ?? 0).toFixed(2)} in balances and {review.open_bets_discarded ?? 0} open bet(s).
          </p>
          <p className="text-xs text-muted-foreground">
            Each account and its login, wallet, bets, KYC files and chats are removed and cannot be recovered. The cases stay on record as confirmed,
            with the fraud signals and identity links, so the same people signing up again are still caught.
          </p>
          {(review.deletable ?? 0) > 0 && (
            <div className="flex flex-wrap items-end gap-3">
              <Field label={`Type ${review.confirm_phrase} to confirm`} className="min-w-[220px]">
                <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" placeholder={review.confirm_phrase} />
              </Field>
              <Btn variant="danger" busy={busy} disabled={typed.trim() !== review.confirm_phrase} onClick={del}>
                Confirm fraud &amp; delete {review.deletable} player{review.deletable === 1 ? '' : 's'}
              </Btn>
            </div>
          )}
        </div>
      )}
      {error && <div className="mt-3"><Notice tone="red" onClose={() => setError('')}>{error}</Notice></div>}
    </div>
  );
}

/** What a bulk decision did. */
export function CasesSummary({ decision, result, onClose }: { decision: Decision; result: CasesResult; onClose: () => void }) {
  const what = decision === 'dismiss' ? 'dismissed' : decision === 'confirm' ? 'confirmed as fraud' : 'confirmed as fraud and deleted';
  return (
    <Notice tone={result.failed_count > 0 ? 'red' : 'green'} onClose={onClose}>
      <p className="font-semibold">
        {(result.done ?? 0).toLocaleString()} of {result.requested.toLocaleString()} case{result.requested === 1 ? '' : 's'} {what}
        {result.skipped_count > 0 && ` · ${result.skipped_count} skipped`}{result.failed_count > 0 && ` · ${result.failed_count} failed`}
      </p>
      {[...result.skipped.map((s) => `Case #${s.case_id}: ${s.reason}`), ...result.failed.map((f) => `Case #${f.case_id} (${f.username}): ${f.error}`)]
        .slice(0, 6).map((line) => <p key={line} className="text-xs opacity-90">{line}</p>)}
    </Notice>
  );
}
