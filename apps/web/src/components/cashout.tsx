'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { BsCashCoin, BsLockFill } from 'react-icons/bs';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { authedPost } from '@/lib/use-api';

/** The live cash-out offer on an open ticket, as the API returns it. */
export interface CashoutOffer {
  available: boolean;
  value: string | null;
  reason: string;
  partial: boolean;
  min_amount: string;
}

/** Other parts of the page (the header balance) listen for this. */
export const WALLET_CHANGED = 'slyk:wallet-changed';

const POLL_MS = 8000;

function money(v: number) {
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Keeps the cash-out offers of the given open tickets fresh: starts from what
 * the ticket list returned, then polls /cashout/offers/ while the tab is
 * visible. Keyed by ticket key ("b12" single, "s7" multiple).
 */
export function useCashoutOffers(tickets: { key: string; kind: 'single' | 'multiple'; id: number; status: string; cashout?: CashoutOffer | null }[]) {
  const { accessToken } = useAuth();
  const open = useMemo(() => tickets.filter((t) => t.status === 'open'), [tickets]);
  const initial = useMemo(
    () => Object.fromEntries(open.map((t) => [t.key, t.cashout ?? null])) as Record<string, CashoutOffer | null>,
    [open],
  );
  const [offers, setOffers] = useState<Record<string, CashoutOffer | null>>(initial);
  useEffect(() => { setOffers(initial); }, [initial]);

  const bets = open.filter((t) => t.kind === 'single').map((t) => t.id).join(',');
  const slips = open.filter((t) => t.kind === 'multiple').map((t) => t.id).join(',');

  const poll = useCallback(async () => {
    if (!accessToken || (!bets && !slips) || document.visibilityState !== 'visible') return;
    try {
      const res = await fetch(`${config.apiUrl}/cashout/offers/?bets=${bets}&slips=${slips}`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
      });
      if (!res.ok) return;
      const data = (await res.json()) as { bets: Record<string, CashoutOffer>; slips: Record<string, CashoutOffer> };
      setOffers((prev) => ({
        ...prev,
        ...Object.fromEntries(Object.entries(data.bets ?? {}).map(([id, o]) => [`b${id}`, o])),
        ...Object.fromEntries(Object.entries(data.slips ?? {}).map(([id, o]) => [`s${id}`, o])),
      }));
    } catch { /* keep the last offer; the next poll retries */ }
  }, [accessToken, bets, slips]);

  useEffect(() => {
    if (!bets && !slips) return;
    const timer = window.setInterval(poll, POLL_MS);
    return () => window.clearInterval(timer);
  }, [poll, bets, slips]);

  return offers;
}

/**
 * The cash-out strip at the bottom of an open ticket: the live value, then a
 * confirm step where the player can take all of it or (when allowed) only
 * part, leaving the rest of the stake riding.
 */
export function CashoutPanel({ kind, id, stake, odds, offer, onDone, compact = false }: {
  kind: 'single' | 'multiple';
  id: number;
  stake: number;
  odds: number;
  offer: CashoutOffer | null | undefined;
  onDone: () => void;
  compact?: boolean;
}) {
  const { accessToken } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [share, setShare] = useState(100);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [override, setOverride] = useState<string | null>(null);

  const valueText = override ?? offer?.value ?? null;
  const value = valueText ? Number(valueText) : 0;
  const min = Number(offer?.min_amount ?? 0);
  const partial = !!offer?.partial && value >= 2 * min;
  // Partial: between the minimum and leaving at least the minimum riding.
  const amount = share >= 100 || !partial
    ? value
    : Math.min(value - min, Math.max(min, Math.floor(value * share) / 100));
  const full = amount >= value;
  const riding = stake * (1 - amount / (value || 1));

  useEffect(() => { setOverride(null); }, [offer?.value]);

  if (!offer) return null;
  const pad = compact ? 'px-3' : 'px-4';

  if (!offer.available || !valueText) {
    return (
      <div className={`flex items-center gap-2 border-t border-border/70 ${pad} py-2 text-[11.5px] text-muted-foreground`}>
        <BsLockFill size={10} className="shrink-0" />
        <span className="truncate">{offer.reason || 'Cash-out isn’t available right now.'}</span>
      </div>
    );
  }

  async function confirm() {
    if (!accessToken) return;
    setBusy(true); setMessage(null);
    const path = `/${kind === 'single' ? 'bets' : 'betslips'}/${id}/cashout/`;
    const res = await authedPost<{ paid: string; full: boolean }>(
      path, { expected: valueText, ...(full ? {} : { amount: amount.toFixed(2) }) }, accessToken,
    );
    setBusy(false);
    if (res.data) {
      setConfirming(false);
      setMessage({ tone: 'ok', text: `${money(Number(res.data.paid))} is in your wallet.` });
      window.dispatchEvent(new Event(WALLET_CHANGED));
      onDone();
      return;
    }
    const body = res.body as { code?: string; value?: string } | undefined;
    if (body?.code === 'cashout_changed' && body.value) {
      setOverride(body.value);
      setShare(100);
      setMessage({ tone: 'warn', text: `The value changed to ${money(Number(body.value))}. Confirm again to take it.` });
      return;
    }
    setConfirming(false);
    setMessage({ tone: 'error', text: res.error ?? 'Cash-out failed. Please try again.' });
    onDone();
  }

  return (
    <div className={`border-t border-border/70 ${pad} py-2.5`}>
      {!confirming ? (
        <button
          onClick={() => { setConfirming(true); setShare(100); setMessage(null); }}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-gold to-[#f0b54a] text-[13px] font-extrabold text-black shadow-sm transition-transform active:scale-[0.99]"
        >
          <BsCashCoin size={15} /> Cash out {money(value)}
        </button>
      ) : (
        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[12px] font-bold text-muted-foreground">{full ? 'Cash out everything' : 'Cash out part'}</span>
            <span className="text-lg font-extrabold text-gold">{money(amount)}</span>
          </div>
          {partial && (
            <div>
              <input
                type="range" min={10} max={100} step={5} value={share}
                onChange={(e) => setShare(Number(e.target.value))}
                aria-label="How much to cash out"
                className="w-full accent-[var(--gold)]"
              />
              <p className="text-[11px] text-muted-foreground">
                {full
                  ? `Ticket closes. Potential return was ${money(stake * odds)}.`
                  : `${money(riding)} stake keeps riding — potential return ${money(riding * odds)}.`}
              </p>
            </div>
          )}
          {!partial && <p className="text-[11px] text-muted-foreground">The ticket closes. Potential return was {money(stake * odds)}.</p>}
          <div className="flex gap-2">
            <button
              onClick={() => setConfirming(false)}
              className="h-10 flex-1 rounded-lg border border-border text-[13px] font-bold text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            <button
              onClick={confirm}
              disabled={busy}
              className="flex h-10 flex-[2] items-center justify-center gap-2 rounded-lg bg-gold text-[13px] font-extrabold text-black disabled:opacity-60"
            >
              {busy ? <Spinner size={14} /> : <BsCashCoin size={14} />} Confirm {money(amount)}
            </button>
          </div>
        </div>
      )}
      {message && (
        <p className={`mt-2 text-[11.5px] font-semibold ${message.tone === 'ok' ? 'text-win' : message.tone === 'warn' ? 'text-gold' : 'text-live'}`} role="status">
          {message.text}
        </p>
      )}
    </div>
  );
}
