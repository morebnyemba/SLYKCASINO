'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { BsXLg, BsReceipt, BsTrash3 } from 'react-icons/bs';
import { LoadCodeForm, ShareSlip } from '@/components/booking-code';
import { useAuth } from '@/lib/auth-context';
import { useBetslip, keyOf, type BetLeg, type Selection } from '@/lib/betslip-context';
import { formatOdds, useSettings } from '@/lib/settings-context';
import { withTeamNames } from '@/lib/sports';
import { bonusEligible, meetsMinOdds, useWallets, WALLET_IDS, WALLET_LABEL, type WalletId } from '@/lib/wallets';
import { Spinner } from '@slyk/ui/components/spinner';

const SELECTION_CODE: Record<Selection, string> = { home: '1', draw: 'X', away: '2' };
const QUICK_STAKES = [5, 10, 25, 50, 100];

/** "Arsenal" / "Draw" / "Chelsea" — the pick in plain words, from the "A v B" event name. */
function pickLabel(leg: BetLeg): string {
  if (leg.outcomeId != null) return leg.outcomeLabel ?? 'Selection';
  if (leg.selection === 'draw') return 'Draw';
  const [home, away] = leg.eventName.split(/\s+(?:v|vs\.?)\s+/i);
  if (leg.selection === 'away') return away ?? 'Away';
  return away ? home : leg.eventName;
}

/** The server's same-match note names outcomes as the feed spells them ("Home/Yes"): put the teams in. */
function namedConflict(message: string | null, legs: BetLeg[], events: Set<string>): string | null {
  if (!message) return null;
  const leg = legs.find((l) => events.has(String(l.eventId)));
  const [home, away] = (leg?.eventName ?? '').split(/\s+(?:v|vs\.?)\s+/i);
  return home && away ? withTeamNames(message, home, away) : message;
}

function money(n: number) {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Which wallet pays for the slip. Each shows its balance and minimum odds;
 *  one the slip's odds don't reach can't be picked. The server enforces the
 *  same rules — this only shows them before the player confirms. */
function walletProblems(data: ReturnType<typeof useWallets>['data'], odds: number, legOdds: number[], isMultiple: boolean,
  fmtOdds: (o: number) => string, stake = 0) {
  const out: Partial<Record<WalletId, string | null>> = {};
  if (!data?.wallets) return out;
  const bonusProblem = bonusEligible(data.bonus_rules, legOdds, isMultiple);
  for (const id of WALLET_IDS) {
    const info = data.wallets[id];
    if (id === 'bonus' && Number(info.balance) <= 0) out[id] = 'Your Bonus wallet is empty';
    else if (id === 'bonus' && bonusProblem) out[id] = bonusProblem;
    else if (!meetsMinOdds(info, odds)) out[id] = `Needs odds of ${fmtOdds(Number(info.min_odds))} or more`;
    // A bonus bet stakes the whole Bonus wallet, so only the other two can run short.
    else if (id !== 'bonus' && stake > 0 && Number(info.balance) + 1e-9 < stake) out[id] = 'Not enough for this stake';
    else out[id] = null;
  }
  return out;
}

function WalletPicker({ odds, legOdds, isMultiple, stake = 0 }: { odds: number; legOdds: number[]; isMultiple: boolean; stake?: number }) {
  const { wallet, setWallet, setAccaStake } = useBetslip();
  const { data } = useWallets();
  const { oddsFormat } = useSettings();
  const bonusBalance = data?.wallets?.bonus.balance;
  // A bonus bet always stakes the whole Bonus wallet.
  useEffect(() => {
    if (wallet === 'bonus' && bonusBalance != null) setAccaStake(Number(bonusBalance).toFixed(2));
  }, [wallet, bonusBalance, setAccaStake]);
  if (!data?.wallets) return null;
  const rules = data.bonus_rules;
  const problems = walletProblems(data, odds, legOdds, isMultiple, (o) => formatOdds(o, oddsFormat), stake);
  return (
    <fieldset className="mb-3">
      <legend className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Pay from</legend>
      <div className="grid grid-cols-3 gap-1.5">
        {WALLET_IDS.map((id: WalletId) => {
          const info = data.wallets[id];
          const why = problems[id] ?? null;
          const ok = !why;
          const chosen = wallet === id && ok;
          return (
            <button
              key={id}
              type="button"
              disabled={!ok}
              onClick={() => setWallet(id)}
              aria-pressed={chosen}
              title={why ?? undefined}
              className={`relative rounded-xl border-2 px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                chosen ? 'border-secondary bg-secondary/10' : 'border-border hover:bg-muted'
              }`}
            >
              {chosen && <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-secondary text-[10px] font-black text-secondary-foreground">✓</span>}
              <span className="block text-[11.5px] font-bold">{WALLET_LABEL[id]}</span>
              <span className="block text-[14px] font-extrabold tabular-nums">{money(Number(info.balance))}</span>
              <span className="block text-[10px] leading-tight text-muted-foreground">
                {why ?? (id === 'bonus' && rules ? `${rules.min_legs}+ picks @ ${rules.min_leg_odds}+` : `Min odds ${formatOdds(Number(info.min_odds), oddsFormat)}`)}
              </span>
            </button>
          );
        })}
      </div>
      {wallet === 'bonus' && rules && (
        <p className="mt-2 rounded-lg bg-gold/10 px-3 py-2 text-[11.5px] font-semibold leading-snug text-gold">
          Bonus bet: stakes your whole Bonus wallet on one multiple of {rules.min_legs}+ selections at {rules.min_leg_odds}+ each.
          Winnings go back into Bonus; win {rules.wins_needed} in a row to move up to ${Number(rules.max_conversion).toFixed(0)} into
          Winnings ({rules.wins} of {rules.wins_needed} so far). No cash-out.
        </p>
      )}
    </fieldset>
  );
}

/** The last step before a bet is placed: what's staked and could come back, and
 * which wallet pays (the last one used is ticked when it can still pay). */
function ConfirmBet({ odds, legOdds, isMultiple, stake, payout, combined, bets, onCancel, onConfirm }: {
  odds: number; legOdds: number[]; isMultiple: boolean; stake: number; payout: number;
  combined: number | null; bets: number; onCancel: () => void; onConfirm: () => Promise<void>;
}) {
  const { wallet, busy } = useBetslip();
  const { data } = useWallets();
  const { oddsFormat } = useSettings();
  const problems = walletProblems(data, odds, legOdds, isMultiple, (o) => formatOdds(o, oddsFormat), stake);
  const canPay = !!wallet && problems[wallet] === null;
  return (
    <div className="absolute inset-0 z-20 flex flex-col justify-end bg-black/40" onClick={onCancel}>
      <div
        role="dialog" aria-modal="true" aria-label="Confirm your bet"
        className="animate-slyk-sheet max-h-full overflow-y-auto rounded-t-2xl border-t border-border bg-card px-4 pb-4 pt-3 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[15px] font-extrabold">Confirm your bet</p>
          <button onClick={onCancel} aria-label="Back to the slip" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"><BsXLg size={13} /></button>
        </div>
        <dl className="mb-3 grid grid-cols-3 gap-2 rounded-xl bg-muted/50 px-3 py-2.5 text-[11px]">
          <div><dt className="text-muted-foreground">{bets > 1 ? `Stake (${bets} bets)` : 'Stake'}</dt><dd className="text-[14px] font-extrabold tabular-nums">{money(stake)}</dd></div>
          <div><dt className="text-muted-foreground">{combined != null ? 'Total odds' : 'Bets'}</dt><dd className="text-[14px] font-extrabold tabular-nums">{combined != null ? formatOdds(combined, oddsFormat) : bets}</dd></div>
          <div className="text-right"><dt className="text-muted-foreground">Potential win</dt><dd className="text-[14px] font-extrabold tabular-nums text-win">{money(payout)}</dd></div>
        </dl>
        <WalletPicker odds={odds} legOdds={legOdds} isMultiple={isMultiple} stake={stake} />
        <div className="flex gap-2">
          <button onClick={onCancel} className="rounded-xl border border-border px-4 py-3 text-sm font-bold">Back</button>
          <button
            onClick={() => void onConfirm()}
            disabled={!canPay || busy}
            className="flex-1 rounded-xl bg-win px-4 py-3 text-sm font-extrabold text-win-foreground shadow-lg transition-opacity hover:opacity-90 disabled:opacity-45"
          >
            {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Placing…</span>
              : canPay ? `Confirm · ${money(stake)}` : 'Choose a wallet'}
          </button>
        </div>
      </div>
    </div>
  );
}

/** The slip body, shared by the desktop rail card and the mobile sheet. */
export function SlipBody({ onClose, variant = 'card' }: {
  onClose?: () => void;
  /** `rail` renders flat and full-height for the desktop right column (which has its own header). */
  variant?: 'card' | 'rail';
}) {
  const { user } = useAuth();
  const { oddsFormat } = useSettings();
  const {
    legs, limits, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, bonus, status, busy,
    removeLeg, clear, place, conflictingEvents, conflictMessage, sameMatchPercent, hasPriceChanges, hasSuspended, acceptPriceChanges, wallet,
    oddsPolicy, setOddsPolicy,
    matchGroups, fixtures,
  } = useBetslip();

  const hasLegs = legs.length > 0;
  const isSingles = mode === 'singles';
  const fmt = (o: number) => formatOdds(o, oddsFormat);

  /** One pick (singles, or the only pick from its match on a multiple). */
  const renderLeg = (l: BetLeg) => {
              const key = keyOf(l);
              const conflict = !isSingles && conflictingEvents.has(String(l.eventId));
              const stake = legStakes[key] || '';
              const stakeNum = parseFloat(stake) || 0;
              return (
                <div key={key} className={`rounded-xl border bg-background/50 p-3 ${conflict ? 'border-gold' : 'border-border'}`}>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-[13px] font-extrabold leading-tight">{pickLabel(l)}</p>
                      <p className="mt-0.5 text-[11px] font-semibold text-muted-foreground">
                        {l.outcomeId != null ? l.marketName : `Match result · ${SELECTION_CODE[l.selection]}`}
                      </p>
                      <p className="mt-0.5 break-words text-[11px] text-muted-foreground">{l.eventName.replace(/\s+vs?\.?\s+/i, ' – ')}</p>
                      {conflict && (
                        <p className="mt-1 text-[11px] font-bold text-gold">Can’t go on the same multiple — see the note above</p>
                      )}
                    </div>
                    {l.suspended ? (
                      <span className="flex flex-col items-end" title="Can’t be played right now">
                        <span className="rounded-md bg-muted px-2 py-1 text-sm font-extrabold tabular-nums text-muted-foreground/60">{fmt(l.odds)}</span>
                        <span className="mt-0.5 text-[10px] font-bold text-muted-foreground">Not available now</span>
                      </span>
                    ) : (
                      <span className="flex flex-col items-end">
                        {l.changedFrom != null && (
                          <span className="text-[10.5px] font-semibold tabular-nums text-muted-foreground line-through">{fmt(l.changedFrom)}</span>
                        )}
                        <span className={`rounded-md px-2 py-1 text-sm font-extrabold tabular-nums ${
                          l.changedFrom == null ? 'bg-odds'
                            : l.odds > l.changedFrom ? 'bg-win/15 text-win' : 'bg-destructive/10 text-destructive'
                        }`}>
                          {l.changedFrom != null && (l.odds > l.changedFrom ? '▲ ' : '▼ ')}{fmt(l.odds)}
                        </span>
                      </span>
                    )}
                    <button
                      onClick={() => removeLeg(key)}
                      aria-label="Remove selection"
                      className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                    >
                      <BsXLg size={12} />
                    </button>
                  </div>
                  {isSingles && (
                    <div className="mt-2.5 flex items-center gap-2">
                      <div className="relative flex-1">
                        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs font-bold text-muted-foreground">$</span>
                        <input
                          value={stake}
                          onChange={(e) => setLegStake(key, e.target.value)}
                          inputMode="decimal"
                          placeholder="Stake"
                          aria-label={`Stake for ${pickLabel(l)}`}
                          className="w-full rounded-lg border border-border bg-input py-2 pl-6 pr-2 text-sm font-bold outline-none focus:ring-2 focus:ring-ring"
                        />
                      </div>
                      <div className="min-w-[80px] text-right">
                        <p className="text-[10px] font-semibold text-muted-foreground">Returns</p>
                        <p className="text-[13px] font-extrabold tabular-nums text-win">{money(stakeNum * l.odds)}</p>
                      </div>
                    </div>
                  )}
                </div>
              );
  };

  const slipTabs: { id: 'acca' | 'singles'; label: string }[] = [
    { id: 'acca', label: legs.length > 1 ? (fixtures > 1 ? `Multiple (${fixtures})` : 'Same match') : 'Single' },
    { id: 'singles', label: 'Singles' },
  ];

  const totalStake = isSingles
    ? legs.reduce((a, l) => a + (parseFloat(legStakes[keyOf(l)] || '0') || 0), 0)
    : parseFloat(accaStake || '0') || 0;
  const placeLabel = isSingles
    ? `Place ${legs.length} bet${legs.length === 1 ? '' : 's'} · ${money(totalStake)}`
    : `Place bet · ${money(totalStake)}`;
  const rejected = !!status && /^(Rejected|Enter|Please|Choose|Odds changed|Multiples|Placed \d)/.test(status);
  // Place bet opens a short confirm step: the stake, the return, and which wallet pays.
  const [confirming, setConfirming] = useState(false);
  useEffect(() => { if (!hasLegs || hasPriceChanges || hasSuspended) setConfirming(false); }, [hasLegs, hasPriceChanges, hasSuspended]);

  return (
    <div className={variant === 'rail'
      ? 'relative flex h-full min-h-0 flex-col'
      : 'relative flex max-h-full flex-col overflow-hidden rounded-2xl border border-border bg-card'}
    >
      {confirming && user && hasLegs && (
        <ConfirmBet
          odds={isSingles ? Math.min(...legs.map((l) => l.odds)) : combinedOdds}
          legOdds={legs.map((l) => l.odds)}
          isMultiple={!isSingles && legs.length > 1}
          stake={totalStake}
          payout={potentialPayout}
          combined={isSingles ? null : combinedOdds}
          bets={isSingles ? legs.filter((l) => (parseFloat(legStakes[keyOf(l)] || '0') || 0) > 0).length : 1}
          onCancel={() => setConfirming(false)}
          onConfirm={async () => { await place(); setConfirming(false); }}
        />
      )}
      <div className={`flex items-center gap-2.5 px-4 py-3 ${variant === 'rail' && !hasLegs ? 'hidden' : ''}`}>
        <BsReceipt size={16} className={variant === 'rail' ? 'hidden' : 'text-secondary'} />
        <span className={`font-extrabold ${variant === 'rail' ? 'text-sm text-muted-foreground' : ''}`}>
          {variant === 'rail' ? `${legs.length} selection${legs.length === 1 ? '' : 's'}` : 'Bet slip'}
        </span>
        {hasLegs && variant !== 'rail' && (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-secondary px-1.5 text-[11px] font-extrabold text-secondary-foreground">
            {legs.length}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {hasLegs && (
            <button
              onClick={clear}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <BsTrash3 size={11} /> Clear
            </button>
          )}
          {onClose && (
            <button onClick={onClose} aria-label="Close bet slip" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <BsXLg size={15} />
            </button>
          )}
        </div>
      </div>

      {hasLegs && (
        <div className="mx-3 mb-2 grid grid-cols-2 gap-1 rounded-xl bg-muted/60 p-1">
          {slipTabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setMode(t.id)}
              className={`rounded-lg py-1.5 text-xs font-bold transition-colors ${
                mode === t.id ? 'bg-card text-foreground shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {!hasLegs && (
        <div className={`px-6 pb-8 pt-4 text-center ${variant === 'rail' ? 'my-auto' : ''}`}>
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
            <BsReceipt size={22} className="text-muted-foreground" />
          </div>
          <p className="mb-1 text-sm font-bold">Your bet slip is empty</p>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            Tap any price to add a selection. Add two or more for a multiple.
          </p>
          <LoadCodeForm className="mb-4" />
          {user && (
            <Link href="/account/bets" onClick={onClose} className="text-xs font-bold text-secondary hover:underline">
              View my bets →
            </Link>
          )}
        </div>
      )}

      {hasLegs && (
        <>
          {/* Picks, stake, wallet and totals scroll together (a fixed footer left room
              for barely one pick on phones); only the place button stays pinned. */}
          <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-2 px-3 pb-3">
            {/* Why some picks can't share this multiple: said once, with the teams named. */}
            {!isSingles && conflictingEvents.size > 0 && (
              <p className="rounded-xl border border-gold/50 bg-gold/10 px-3 py-2 text-[11.5px] font-semibold text-gold">
                {namedConflict(conflictMessage, legs, conflictingEvents)
                  ?? 'Two picks from the same match can’t share a multiple.'} Remove one, or switch to Singles.
              </p>
            )}
            {(isSingles ? legs.map((l) => renderLeg(l)) : matchGroups.map((g) => (g.legs.length === 1 ? renderLeg(g.legs[0]) : (
              <div key={`m${g.eventId}`} className={`rounded-xl border bg-background/50 p-3 ${!isSingles && conflictingEvents.has(g.eventId) ? 'border-gold' : 'border-secondary/50'}`}>
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-[10.5px] font-bold uppercase tracking-wide text-secondary">Same match · {g.legs.length} picks</p>
                    <p className="mt-0.5 break-words text-[11px] text-muted-foreground">{g.eventName.replace(/\s+vs?\.?\s+/i, ' – ')}</p>
                    <p className="mt-1 break-words text-[13px] font-extrabold leading-tight">{g.names.join(' & ')}</p>
                  </div>
                  <span className="rounded-md bg-odds px-2 py-1 text-sm font-extrabold tabular-nums">{fmt(g.odds)}</span>
                </div>
                <ul className="mt-2 space-y-1 border-t border-border/60 pt-2">
                  {g.legs.map((l, i) => (
                    <li key={keyOf(l)} className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
                      <span className="min-w-0 flex-1 truncate">{g.names[i]}{l.suspended ? ' · not available now' : ''}</span>
                      <button onClick={() => removeLeg(keyOf(l))} aria-label={`Remove ${g.names[i]}`}
                        className="rounded p-0.5 hover:bg-muted hover:text-destructive"><BsXLg size={10} /></button>
                    </li>
                  ))}
                </ul>
                {conflictingEvents.has(g.eventId) && (
                  <p className="mt-1 text-[11px] font-bold text-gold">Can’t go on the same multiple — see the note above</p>
                )}
              </div>
            ))))}
          </div>

          <div className="border-t border-border bg-muted/30 px-4 pt-3.5">
            {!isSingles && (
              <div className="mb-3">
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold text-muted-foreground">Stake $</span>
                  <input
                    value={accaStake}
                    readOnly={wallet === 'bonus'}
                    onChange={(e) => setAccaStake(e.target.value.replace(/[^0-9.]/g, ''))}
                    inputMode="decimal"
                    placeholder="0.00"
                    aria-label="Stake"
                    className="w-full rounded-xl border border-border bg-input py-2.5 pl-[4.5rem] pr-3 text-right text-base font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                {wallet !== 'bonus' && limits && (
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Stake ${limits.minStake.toFixed(2)}–${limits.maxStake.toFixed(2)} · up to {limits.maxSelections} matches
                  </p>
                )}
                {wallet !== 'bonus' && (
                <div className="mt-2 grid grid-cols-5 gap-1.5">
                  {QUICK_STAKES.map((v) => (
                    <button
                      key={v}
                      onClick={() => setAccaStake(String(v))}
                      className={`rounded-lg border py-1.5 text-xs font-bold transition-colors ${
                        accaStake === String(v)
                          ? 'border-secondary bg-secondary/15 text-foreground'
                          : 'border-border bg-card text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {v}
                    </button>
                  ))}
                </div>
                )}
              </div>
            )}



            <dl className="mb-3 space-y-1 text-[12.5px]">
              {!isSingles && (
                <>
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">{legs.length > 1 ? 'Total odds' : 'Odds'}</dt>
                    <dd className="font-bold tabular-nums">{fmt(combinedOdds)}</dd>
                  </div>
                  {sameMatchPercent != null && sameMatchPercent < 100 && conflictingEvents.size === 0 && (
                    <p className="text-[11px] text-muted-foreground">Picks from the same match are priced together: the more they tend to win together, the lower their combined price.</p>
                  )}
                </>
              )}
              {bonus.percent > 0 && (
                <div className="flex justify-between">
                  <dt className="font-semibold text-gold">Multi-bet bonus +{bonus.percent}%</dt>
                  <dd className="font-bold tabular-nums text-gold">+{money(bonus.amount)}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Total stake</dt>
                <dd className="font-bold tabular-nums">{money(totalStake)}</dd>
              </div>
              <div className="flex items-baseline justify-between pt-1">
                <dt className="text-sm font-bold">Potential win</dt>
                <dd className="text-lg font-extrabold tabular-nums text-win">{money(potentialPayout)}</dd>
              </div>
            </dl>

            {!isSingles && bonus.next && (
              <p className="mb-3 rounded-lg bg-gold/10 px-3 py-2 text-[11.5px] font-semibold text-gold">
                Add {bonus.next.minLegs - bonus.qualifying} more selection{bonus.next.minLegs - bonus.qualifying === 1 ? '' : 's'}
                {' '}at {fmt(bonus.minOdds)}+ for a {bonus.next.percent}% multi-bet bonus.
              </p>
            )}

            <label className="mb-1 flex items-center justify-between gap-2 text-[11.5px] font-semibold text-muted-foreground">
              Odds changes
              <select value={oddsPolicy} onChange={(e) => setOddsPolicy(e.target.value as typeof oddsPolicy)}
                aria-label="When odds change"
                className="rounded-lg border border-border bg-background px-2 py-1 text-[11.5px] font-bold text-foreground outline-none">
                <option value="higher">Accept higher odds</option>
                <option value="any">Accept any odds</option>
                <option value="ask">Always ask me</option>
              </select>
            </label>
          </div>
          <div className="sticky bottom-0 z-10 border-t border-border bg-card px-4 pb-3.5 pt-3">
            {user ? (
              hasSuspended ? (
                <button
                  disabled
                  className="w-full rounded-xl bg-muted px-4 py-3 text-sm font-extrabold text-muted-foreground"
                >
                  Remove suspended selections
                </button>
              ) : hasPriceChanges ? (
                <button
                  onClick={acceptPriceChanges}
                  className="w-full rounded-xl bg-gold px-4 py-3 text-sm font-extrabold text-gold-foreground shadow-lg transition-opacity hover:opacity-90"
                >
                  Accept odds changes
                </button>
              ) : (
                <button
                  onClick={() => setConfirming(true)}
                  disabled={busy}
                  className="w-full rounded-xl bg-win px-4 py-3 text-sm font-extrabold text-win-foreground shadow-lg transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Placing…</span> : placeLabel}
                </button>
              )
            ) : (
              <Link
                href="/login"
                onClick={onClose}
                className="block w-full rounded-xl bg-win px-4 py-3 text-center text-sm font-extrabold text-win-foreground shadow-lg hover:opacity-90"
              >
                Log in to place bet
              </Link>
            )}
            <div className="mt-2.5">
              <ShareSlip />
            </div>
            {status && (
              <p className={`mt-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                rejected ? 'bg-destructive/10 text-destructive' : 'bg-win/10 text-win'
              }`}>
                {status}
              </p>
            )}
          </div>
          </div>
        </>
      )}
      {!hasLegs && status && (
        <p className="mx-4 mb-4 rounded-lg bg-win/10 px-3 py-2 text-center text-xs font-semibold text-win">{status}</p>
      )}
    </div>
  );
}

/**
 * Mobile: a slide-up sheet opened from the bottom nav, plus a floating summary bar
 * on sportsbook pages whenever the slip has selections. Mounted once in the root layout.
 */
export function BetslipDrawer() {
  const { legs, combinedOdds, slipOpen, setSlipOpen } = useBetslip();
  const { oddsFormat } = useSettings();
  const pathname = usePathname();

  // Close the sheet on navigation so it never lingers over a new page.
  useEffect(() => { setSlipOpen(false); }, [pathname, setSlipOpen]);

  return (
    <div className="xl:hidden">
      {!slipOpen && legs.length > 0 && pathname.startsWith('/sportsbook') && (
        <button
          onClick={() => setSlipOpen(true)}
          className="fixed bottom-[118px] left-3 right-3 z-30 flex lg:bottom-5 lg:left-auto lg:right-5 lg:w-80 items-center gap-3 rounded-2xl bg-win px-4 py-3 text-win-foreground shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
        >
          <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-win-foreground px-1.5 text-xs font-extrabold text-win">
            {legs.length}
          </span>
          <span className="text-sm font-extrabold">Bet slip</span>
          <span className="ml-auto text-[13px] font-bold tabular-nums">Odds {formatOdds(combinedOdds, oddsFormat)}</span>
        </button>
      )}
      {slipOpen && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60 lg:items-stretch lg:justify-end" onClick={() => setSlipOpen(false)}>
          <div
            className="animate-slyk-sheet flex max-h-[85vh] w-full flex-col rounded-t-3xl lg:max-h-none lg:w-[380px] lg:rounded-none lg:pt-4 bg-background p-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-[0_-10px_40px_rgba(0,0,0,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-center pb-2 pt-1 lg:hidden">
              <span className="h-[5px] w-10 rounded-full bg-border" />
            </div>
            <SlipBody onClose={() => setSlipOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
