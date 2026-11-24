'use client';

import Link from 'next/link';
import { useState } from 'react';
import {
  BsCashCoin, BsChevronDown, BsHandThumbsDownFill, BsHandThumbsUpFill, BsUpcScan,
} from 'react-icons/bs';
import { CashoutPanel, type CashoutOffer } from '@/components/cashout';
import { withTeamNames } from '@/lib/sports';

/** The match a bet or leg is on, as the API returns it (null for legacy free-text bets). */
export interface BetMatch {
  id: number;
  name: string;
  sport: string;
  starts_at: string | null;
  status: string;
  elapsed?: number | null;
  score_home: number | null;
  score_away: number | null;
  ht_score_home?: number | null;
  ht_score_away?: number | null;
  home?: string | null;
  away?: string | null;
  /** "Country - League", as printed on a ticket. */
  league?: string | null;
}

export interface ApiBet {
  id: number;
  code?: string | null;
  event: string;
  selection?: string;
  market_name?: string | null;
  outcome_label?: string | null;
  match?: BetMatch | null;
  stake: string;
  odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
  settled_at?: string | null;
  /** Placed while the match was being played. */
  in_play?: boolean;
  wallet?: string;
  cashout?: CashoutOffer | null;
  cashout_paid?: string;
  stake_cashed_out?: string;
}

export interface ApiSlipLeg {
  id: number;
  event: string;
  selection?: string;
  market_name?: string | null;
  outcome_label?: string | null;
  match?: BetMatch | null;
  odds: string;
  result?: string;
  in_play?: boolean;
  /** Short name as it reads on a combined ticket ("Liverpool Win", "BTTS YES"). */
  pick_name?: string;
  /** The one price of all this ticket's picks from this match. */
  match_odds?: string | null;
}

export interface ApiSlip {
  id: number;
  code?: string | null;
  stake: string;
  combined_odds: string;
  status: string;
  payout: string | null;
  bonus_percent?: string;
  bonus?: string;
  placed_at: string;
  settled_at?: string | null;
  in_play?: boolean;
  wallet?: string;
  legs: ApiSlipLeg[];
  cashout?: CashoutOffer | null;
  cashout_paid?: string;
  stake_cashed_out?: string;
}

interface TicketLeg {
  id: number;
  match: string;
  /** "Market - Pick" on one line (summaries); `market` + `outcome` for the full ticket. */
  pick: string;
  market: string;
  outcome: string;
  odds: number;
  result: string;
  info: BetMatch | null;
  /** This selection's match was being played when the ticket was placed. */
  inPlay: boolean;
  /** Several picks from this match, shown as one entry: each pick and its result. */
  parts?: { name: string; result: string; odds: number }[];
}

export interface Ticket {
  key: string;
  kind: 'single' | 'multiple';
  id: number;
  /** Random ticket code: what the barcode carries and the "check a ticket" page looks up. */
  code: string | null;
  stake: number;
  odds: number;
  status: string;
  payout: number | null;
  /** Multiples: multi-bet bonus rate promised, and the amount paid on a win. */
  bonusPercent: number;
  bonus: number;
  placedAt: string;
  settledAt: string | null;
  /** Placed live: at least one selection's match was being played. */
  inPlay: boolean;
  /** The wallet the stake came from (deposit, winnings, bonus). */
  wallet: string;
  legs: TicketLeg[];
  /** The cash-out offer as listed (kept fresh by useCashoutOffers). */
  cashout: CashoutOffer | null;
  /** Paid out early so far, and the part of the original stake it bought. */
  cashoutPaid: number;
  stakeCashedOut: number;
}

const IN_PLAY = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE']);

/** "Home - Away", from the feed's teams, else from the stored "Home v Away". */
function fixture(m: BetMatch | null | undefined, fallbackName: string) {
  const [a, b] = (m?.name ?? fallbackName).split(/\s+(?:v|vs\.?)\s+/i);
  const home = m?.home || a;
  const away = m?.away || b;
  return home && away ? `${home} - ${away}` : (m?.name ?? fallbackName);
}

/** What was backed, as market + pick ("Double Chance" / "Home or draw", "1X2" / "1 · Chelsea"). */
function pickParts(l: ApiSlipLeg): { market: string; outcome: string } {
  if (l.outcome_label) {
    // Feed labels say "Home/Yes", "Draw or away": name the teams on the ticket.
    const [a, b] = (l.match?.name ?? l.event.split(' — ')[0]).split(/\s+(?:v|vs\.?)\s+/i);
    const home = l.match?.home || a;
    const away = l.match?.away || b || null;
    const named = (t: string) => (home ? withTeamNames(t, home, away) : t);
    return { market: named(l.market_name ?? ''), outcome: named(l.outcome_label) };
  }
  const code = { home: '1', draw: 'X', away: '2' }[l.selection ?? ''];
  if (code) {
    const [a, b] = (l.match?.name ?? l.event.split(' — ')[0]).split(/\s+(?:v|vs\.?)\s+/i);
    const team = code === '1' ? l.match?.home || a : code === '2' ? l.match?.away || b : 'Draw';
    return { market: '1X2', outcome: team ? `${code} · ${team}` : code };
  }
  // Old free-text bets are stored as "Arsenal v Chelsea — Match Result: Home".
  const [, ...rest] = l.event.split(' — ');
  if (!rest.length) return { market: '', outcome: '—' };
  const [market, ...pick] = rest.join(' — ').split(': ');
  return pick.length ? { market, outcome: pick.join(': ') } : { market: '', outcome: market };
}

function toLeg(l: ApiSlipLeg, result: string): TicketLeg {
  const match = fixture(l.match, l.event.split(' — ')[0]);
  const { market, outcome } = pickParts(l);
  return {
    id: l.id, match, market, outcome, pick: market ? `${market} - ${outcome}` : outcome,
    odds: Number(l.odds), result, info: l.match ?? null, inPlay: !!l.in_play,
  };
}

/** The matches on a ticket, each once (same-match picks share a fixture). */
function matchList(legs: TicketLeg[]) {
  return [...new Set(legs.map((l) => l.match))].join(' | ');
}

/** A single's result is its own status; a leg carries its own result. */
function singleResult(status: string) {
  return status === 'won' || status === 'lost' || status === 'void' ? status : 'pending';
}

export function ticketFromBet(b: ApiBet): Ticket {
  return {
    key: `b${b.id}`, kind: 'single', id: b.id, code: b.code ?? null, stake: Number(b.stake), odds: Number(b.odds),
    status: b.status, payout: b.payout == null ? null : Number(b.payout), placedAt: b.placed_at, settledAt: b.settled_at ?? null,
    bonusPercent: 0, bonus: 0, inPlay: !!b.in_play, wallet: b.wallet ?? '',
    legs: [toLeg(b, singleResult(b.status))],
    cashout: b.cashout ?? null, cashoutPaid: Number(b.cashout_paid ?? 0), stakeCashedOut: Number(b.stake_cashed_out ?? 0),
  };
}

/** A combined result for picks from one match: lost if any lost, won once every pick won (or was voided). */
function groupResult(results: string[]): string {
  if (results.includes('lost')) return 'lost';
  if (results.includes('pending')) return 'pending';
  return results.every((r) => r === 'void') ? 'void' : 'won';
}

/** One entry per match: picks from the same match join into one ("Liverpool Win & BTTS YES") at one price. */
function byMatch(legs: ApiSlipLeg[]): TicketLeg[] {
  const groups = new Map<string, ApiSlipLeg[]>();
  legs.forEach((l, i) => {
    const key = l.match?.id != null ? `m${l.match.id}` : `x${i}`;
    groups.set(key, [...(groups.get(key) ?? []), l]);
  });
  return [...groups.values()].map((group) => {
    const legsOut = group.map((l) => toLeg(l, l.result ?? 'pending'));
    if (group.length === 1) return legsOut[0];
    const names = group.map((l, i) => l.pick_name || legsOut[i].pick);
    const odds = Number(group[0].match_odds ?? 0) || legsOut.reduce((acc, l) => acc * l.odds, 1);
    const result = groupResult(legsOut.map((l) => l.result));
    return {
      ...legsOut[0], market: `${group.length} picks · one price`, outcome: names.join(' & '), pick: names.join(' & '),
      odds, result, inPlay: legsOut.some((l) => l.inPlay),
      parts: legsOut.map((l, i) => ({ name: names[i], result: l.result, odds: l.odds })),
    };
  });
}

export function ticketFromSlip(s: ApiSlip): Ticket {
  return {
    key: `s${s.id}`, kind: 'multiple', id: s.id, code: s.code ?? null, stake: Number(s.stake), odds: Number(s.combined_odds),
    status: s.status, payout: s.payout == null ? null : Number(s.payout), placedAt: s.placed_at, settledAt: s.settled_at ?? null,
    bonusPercent: Number(s.bonus_percent ?? 0), bonus: Number(s.bonus ?? 0), inPlay: !!s.in_play, wallet: s.wallet ?? '',
    legs: byMatch(s.legs),
    cashout: s.cashout ?? null, cashoutPaid: Number(s.cashout_paid ?? 0), stakeCashedOut: Number(s.stake_cashed_out ?? 0),
  };
}

/** A row from /my-tickets/ or /tickets/<code>/ (singles and multiples together). */
export function ticketFromRow(row: (ApiBet | ApiSlip) & { kind: 'single' | 'multiple' }): Ticket {
  return row.kind === 'multiple' ? ticketFromSlip(row as ApiSlip) : ticketFromBet(row as ApiBet);
}

/** Open (and in-flight) tickets first, then newest first. */
export function sortTickets(tickets: Ticket[]) {
  const live = (t: Ticket) => (isSettled(t.status) ? 1 : 0);
  return [...tickets].sort((a, b) => live(a) - live(b) || Date.parse(b.placedAt) - Date.parse(a.placedAt));
}

export function isSettled(status: string) {
  return status === 'won' || status === 'lost' || status === 'void' || status === 'rejected' || status === 'cashed_out';
}

export function money(v: number) {
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const STATUS: Record<string, { label: string; className: string; bar: string }> = {
  pending: { label: 'Pending', className: 'bg-muted text-muted-foreground', bar: 'bg-muted-foreground/40' },
  accepting: { label: 'Confirming', className: 'bg-live/10 text-live', bar: 'bg-live' },
  open: { label: 'Open', className: 'bg-secondary/15 text-secondary', bar: 'bg-secondary' },
  won: { label: 'Won', className: 'bg-win/15 text-win', bar: 'bg-win' },
  lost: { label: 'Lost', className: 'bg-destructive/10 text-destructive', bar: 'bg-destructive' },
  void: { label: 'Void', className: 'bg-muted text-muted-foreground', bar: 'bg-muted-foreground/40' },
  rejected: { label: 'Rejected', className: 'bg-muted text-muted-foreground', bar: 'bg-muted-foreground/40' },
  cashed_out: { label: 'Cashed out', className: 'bg-gold/15 text-gold', bar: 'bg-gold' },
};

const when = (iso: string, withDay = true) => new Date(iso).toLocaleString(undefined, {
  ...(withDay ? { weekday: 'short' as const } : {}), day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
});

function isLiveMatch(m: BetMatch | null) {
  return !!m && IN_PLAY.has(m.status);
}

/** The thumb beside a settled ticket's Won / Lost label. */
function StatusThumb({ status, size = 13 }: { status: string; size?: number }) {
  if (status === 'won') return <BsHandThumbsUpFill size={size} aria-hidden />;
  if (status === 'lost') return <BsHandThumbsDownFill size={size} aria-hidden />;
  return null;
}


/** Ticket-style date: 20/10/2026 18:45. */
const ticketDate = (iso: string) => new Date(iso).toLocaleString('en-GB', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
}).replace(',', '');

/** "HT: 2-1 FT: 2-2"; in play "Live 67': 1-0"; "Ended: 1-0" when the feed never sent full time. */
function scoreLine(m: BetMatch | null): { text: string; live: boolean } | null {
  if (!m || m.score_home == null || m.score_away == null) return m?.status === 'NR' ? { text: 'Ended', live: false } : null;
  const score = `${m.score_home}-${m.score_away}`;
  if (isLiveMatch(m)) {
    const clock = m.status === 'HT' ? 'HT' : m.elapsed != null ? `${m.elapsed}'` : m.status;
    return { text: `Live ${clock}: ${score}`, live: true };
  }
  if (m.status === 'NR') return { text: `Ended: ${score}`, live: false };
  const ht = m.ht_score_home != null && m.ht_score_away != null ? `HT: ${m.ht_score_home}-${m.ht_score_away} ` : '';
  return { text: `${ht}FT: ${score}`, live: false };
}

/** The tab in a selection's top-right corner: WON / LOST / VOID, or LIVE while it's being played. */
function ResultTab({ result, live }: { result: string; live: boolean }) {
  const tab = result === 'won' ? { label: 'Won', cls: 'bg-win text-white', icon: <BsHandThumbsUpFill size={13} aria-hidden /> }
    : result === 'lost' ? { label: 'Lost', cls: 'bg-destructive text-white', icon: <BsHandThumbsDownFill size={13} aria-hidden /> }
      : result === 'void' ? { label: 'Void', cls: 'bg-muted-foreground/70 text-white', icon: null }
        : live ? { label: 'Live', cls: 'bg-live text-white', icon: <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> }
          : null;
  if (!tab) return null;
  return (
    <span className={`absolute right-0 top-0 flex items-center gap-1 rounded-bl-lg rounded-tr-lg px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-wide ${tab.cls}`}>
      {tab.icon}{tab.label}
    </span>
  );
}

/** What a settled ticket did for the player, for the one-line summary. */
function outcome(t: Ticket): { text: string; className: string } {
  if (t.status === 'won') return { text: `+${money((t.payout ?? 0) + t.bonus + t.cashoutPaid)}`, className: 'text-win' };
  if (t.status === 'cashed_out') return { text: money(t.payout ?? t.cashoutPaid), className: 'text-gold' };
  if (t.status === 'void' || t.status === 'rejected') return { text: 'Refunded', className: 'text-muted-foreground' };
  return { text: `−${money(t.stake + t.stakeCashedOut)}`, className: 'text-muted-foreground' };
}

/** How a multiple is going: a bar per leg and a line in words. */
function Progress({ t }: { t: Ticket }) {
  const won = t.legs.filter((l) => l.result === 'won').length;
  const lostLeg = t.legs.find((l) => l.result === 'lost');
  const live = t.legs.filter((l) => l.result === 'pending' && isLiveMatch(l.info));
  const toCome = t.legs.filter((l) => l.result === 'pending' && !isLiveMatch(l.info));
  const next = toCome.map((l) => l.info?.starts_at).filter(Boolean).sort()[0];
  const parts = [
    won && `${won} won`,
    live.length && `${live.length} playing now`,
    toCome.length && `${toCome.length} to come${next && Date.parse(next) > Date.now() ? ` · next ${when(next)}` : ''}`,
  ].filter(Boolean);
  return (
    <div className="space-y-1.5">
      <div className="flex gap-1" aria-hidden>
        {t.legs.map((l) => (
          <span key={l.id} className={`h-1.5 flex-1 rounded-full ${
            l.result === 'won' ? 'bg-win' : l.result === 'lost' ? 'bg-destructive' : l.result === 'void' ? 'bg-muted-foreground/40'
              : isLiveMatch(l.info) ? 'animate-pulse bg-gold' : 'bg-muted'}`} />
        ))}
      </div>
      <p className="text-[11.5px] text-muted-foreground">
        {lostLeg && !isSettled(t.status) ? `Lost on ${lostLeg.match}` : parts.join(' · ')}
      </p>
    </div>
  );
}

/**
 * A placed bet rendered as a betting ticket: header with type, reference and
 * status; every selection with its match, pick, odds and result; then a
 * perforated footer with stake, odds and the (potential) return.
 *
 * `collapsible`: a settled ticket starts as a one-line summary and opens on tap.
 * `isPublic`: shown on the "check a ticket" page to someone who may not own it.
 */
/** "Placed live": the ticket was bet while its match was being played. */
function LiveBadge({ small = false }: { small?: boolean }) {
  return (
    <span title="Placed while the match was being played"
      className={`inline-flex shrink-0 items-center gap-1 rounded bg-live font-extrabold uppercase tracking-wide text-white ${small ? 'px-1 py-px text-[9px]' : 'px-1.5 py-0.5 text-[10px]'}`}>
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" aria-hidden />{small ? 'Live' : 'Placed live'}
    </span>
  );
}

export function BetTicket({ ticket, compact = false, offer, onChanged, collapsible = false, isPublic = false, agentView = false }: {
  /** An agent looking at a customer's ticket: say when it earns them nothing (Bonus wallet). */
  agentView?: boolean;
  ticket: Ticket; compact?: boolean;
  /** Live cash-out offer (from useCashoutOffers); falls back to the listed one. */
  offer?: CashoutOffer | null;
  /** Called after a cash-out so the list reloads. */
  onChanged?: () => void;
  collapsible?: boolean;
  isPublic?: boolean;
}) {
  const t = ticket;
  const s = STATUS[t.status] ?? STATUS.pending;
  const settled = isSettled(t.status);
  const [open, setOpen] = useState(!(collapsible && settled));
  // In the narrow rail a long multiple starts folded to its first legs.
  const foldAt = compact ? 2 : Infinity;
  const [expanded, setExpanded] = useState(false);
  // The header chevron folds the selections away (a long combo is a long list).
  const [legsOpen, setLegsOpen] = useState(true);
  const shown = expanded ? t.legs : t.legs.slice(0, foldAt);
  const hidden = t.legs.length - shown.length;
  // Estimate: assumes every leg wins (a void leg can lower the bonus tier).
  const potential = t.stake * t.odds + Math.max(0, t.stake * t.odds - t.stake) * t.bonusPercent / 100;
  const number = `#${t.kind === 'single' ? 'S' : 'M'}${t.id}`;

  let returnLabel = 'Potential return';
  let returnValue = money(potential);
  let returnClass = 'text-win';
  if (t.status === 'won') { returnLabel = 'Paid out'; returnValue = money(t.payout != null ? t.payout + t.bonus : potential); }
  else if (t.status === 'lost') { returnLabel = 'Return'; returnValue = money(0); returnClass = 'text-muted-foreground'; }
  else if (t.status === 'void' || t.status === 'rejected') { returnLabel = 'Refunded'; returnValue = money(t.payout ?? t.stake); returnClass = 'text-foreground'; }
  else if (t.status === 'cashed_out') { returnLabel = 'Cashed out'; returnValue = money(t.payout ?? t.cashoutPaid); returnClass = 'text-gold'; }
  // After a partial cash-out a win pays the remaining stake plus what was taken early.
  if (t.status === 'won' && t.cashoutPaid > 0) returnValue = money((t.payout ?? 0) + t.bonus + t.cashoutPaid);
  // The stake the player put down: what's riding plus what was cashed out.
  const originalStake = t.status === 'cashed_out' ? t.stakeCashedOut : t.stake + t.stakeCashedOut;

  const pad = compact ? 'px-3' : 'px-4';

  if (!open) {
    const o = outcome(t);
    const title = t.kind === 'single' ? t.legs[0]?.pick : `Combo (${t.legs.length})`;
    const sub = t.kind === 'single' ? t.legs[0]?.match : matchList(t.legs);
    return (
      <button onClick={() => setOpen(true)} aria-expanded={false}
        className="relative flex w-full items-center gap-3 overflow-hidden rounded-xl border border-border bg-card py-2.5 pl-4 pr-3 text-left shadow-sm transition-colors hover:bg-muted/40">
        <span className={`absolute inset-y-0 left-0 w-1 ${s.bar}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 truncate text-[13px] font-bold">
            {t.inPlay && <LiveBadge small />}<span className="truncate">{title}</span>
          </p>
          <p className="truncate text-[11px] text-muted-foreground">{number} · {sub}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className={`text-[13px] font-extrabold tabular-nums ${o.className}`}>{o.text}</p>
          <p className={`flex items-center justify-end gap-1 text-[10px] font-extrabold uppercase ${s.className.split(' ').find((c) => c.startsWith('text-'))}`}>
            <StatusThumb status={t.status} />{s.label}
          </p>
        </div>
        <BsChevronDown size={12} className="shrink-0 text-muted-foreground" />
      </button>
    );
  }

  return (
    <article className="relative overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <span className={`absolute inset-y-0 left-0 w-1 ${s.bar}`} aria-hidden />

      <header className={`${pad} pb-2 pt-3`}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[14px] font-extrabold">
              {t.kind === 'single' ? 'Single' : `Combo (${t.legs.length})`}
              {t.inPlay && <LiveBadge />}
            </p>
            {agentView && t.wallet === 'bonus' && (
              <p className="mt-0.5 text-[11px] font-bold text-gold">🎁 Bonus wallet: no commission on this ticket</p>
            )}
            <p className="text-[11px] text-muted-foreground">{number} · {when(t.placedAt, false)}</p>
          </div>
          <span className="flex shrink-0 items-center gap-1.5">
            <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide ${s.className}`}>
              <StatusThumb status={t.status} />{s.label}
            </span>
            <button
              onClick={() => (collapsible && settled ? setOpen(false) : setLegsOpen((v) => !v))}
              aria-label={legsOpen ? 'Hide selections' : 'Show selections'} aria-expanded={legsOpen}
              className="rounded p-0.5 text-muted-foreground hover:bg-muted"
            >
              <BsChevronDown size={13} className={legsOpen ? 'rotate-180' : ''} />
            </button>
          </span>
        </div>
        <p className="mt-1 truncate border-b border-border/70 pb-2 text-[12px] text-muted-foreground" title={matchList(t.legs)}>
          {matchList(t.legs)}
        </p>
        {t.bonusPercent > 0 && t.status !== 'lost' && (
          <p className="pt-1.5 text-[11px] font-bold text-gold">
            +{t.bonusPercent}% multi-bet bonus{t.bonus > 0 ? ` · ${money(t.bonus)} paid` : ''}
          </p>
        )}
      </header>

      {legsOpen && t.kind === 'multiple' && !settled && <div className={`${pad} pb-2`}><Progress t={t} /></div>}

      {legsOpen && (
        <ol className={`space-y-2 ${pad} pb-2`}>
          {shown.map((l, i) => {
            const live = l.result === 'pending' && isLiveMatch(l.info);
            const score = scoreLine(l.info);
            const sameMatch = !!l.parts;
            return (
              <li key={l.id} className="relative overflow-hidden rounded-lg bg-muted/60 px-3 pb-2.5 pt-2 text-[12.5px]">
                <ResultTab result={l.result} live={live} />
                <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pr-20 text-[11.5px] text-muted-foreground">
                  <span><b className="text-foreground">{i + 1}.</b> {l.info?.starts_at ? ticketDate(l.info.starts_at) : ''}</span>
                  {sameMatch && (
                    <span className="rounded bg-secondary/15 px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-secondary">Same match</span>
                  )}
                  {l.inPlay && t.kind === 'multiple' && (
                    <span className="rounded bg-live/15 px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-live">Live bet</span>
                  )}
                </p>
                {l.info?.league && <p className="mt-1 break-words text-muted-foreground">{l.info.league}</p>}
                {l.info ? (
                  <Link href={`/sportsbook/${l.info.id}`} className="block break-words text-muted-foreground hover:text-foreground hover:underline">{l.match}</Link>
                ) : (
                  <p className="break-words text-muted-foreground">{l.match}</p>
                )}
                {/* Market and pick each get their own line and wrap: a long market
                    ("Results/Both Teams Score") must never hide what was backed. */}
                <div className="mt-1 flex items-end justify-between gap-3">
                  <div className={`min-w-0 ${l.result === 'lost' ? 'text-muted-foreground' : ''}`}>
                    {l.market && (
                      <p className="break-words text-[11px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">{l.market}</p>
                    )}
                    <p className="break-words text-[13.5px] font-extrabold leading-snug">{l.outcome}</p>
                    {l.parts && (
                      <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
                        {l.parts.map((p, j) => (
                          <li key={j} className="flex items-center gap-1.5">
                            <span aria-hidden className={p.result === 'won' ? 'text-win' : p.result === 'lost' ? 'text-destructive' : ''}>
                              {p.result === 'won' ? '✓' : p.result === 'lost' ? '✗' : p.result === 'void' ? '↩' : '•'}
                            </span>
                            <span className="min-w-0 truncate">{p.name}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <span className="shrink-0 font-mono text-[13.5px] font-extrabold leading-snug">{l.odds.toFixed(2)}</span>
                </div>
                {score && <p className={`mt-0.5 text-[11.5px] ${score.live ? 'font-bold text-live' : 'text-muted-foreground'}`}>{score.text}</p>}
              </li>
            );
          })}
        </ol>
      )}
      {legsOpen && (hidden > 0 || (expanded && t.legs.length > foldAt)) && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`flex w-full items-center justify-center gap-1 ${pad} pb-2 text-[11px] font-bold text-secondary hover:underline`}
        >
          {expanded ? 'Show less' : `Show ${hidden} more`}
          <BsChevronDown size={10} className={expanded ? 'rotate-180' : ''} />
        </button>
      )}

      {/* Perforation: a dashed tear line with notches cut into both edges. */}
      <div className="relative h-3" aria-hidden>
        <span className="absolute -left-1.5 top-0 h-3 w-3 rounded-full border border-border bg-background" />
        <span className="absolute -right-1.5 top-0 h-3 w-3 rounded-full border border-border bg-background" />
        <span className="absolute inset-x-3 top-1/2 border-t border-dashed border-border" />
      </div>

      <footer className={`grid grid-cols-3 gap-2 ${pad} pb-3 pt-1 text-[11px]`}>
        <div>
          <p className="text-muted-foreground">Stake</p>
          <p className="text-[13px] font-bold">{money(originalStake || t.stake)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">{t.kind === 'single' ? 'Odds' : 'Total odds'}</p>
          <p className="font-mono text-[13px] font-bold">{t.odds.toFixed(2)}</p>
        </div>
        <div className="text-right">
          <p className="text-muted-foreground">{returnLabel}</p>
          <p className={`text-[13px] font-extrabold ${returnClass}`}>{returnValue}</p>
        </div>
      </footer>
      {t.cashoutPaid > 0 && t.status !== 'cashed_out' && (
        <p className={`flex items-center gap-1.5 ${pad} pb-2.5 text-[11.5px] font-semibold text-gold`}>
          <BsCashCoin size={12} /> {money(t.cashoutPaid)} cashed out · {money(t.stake)} still riding
        </p>
      )}
      {(t.settledAt || (t.code && !isPublic)) && (
        <div className={`flex items-center justify-between gap-2 border-t border-border/70 ${pad} py-2 text-[11px] text-muted-foreground`}>
          <span>{t.settledAt ? `Settled ${when(t.settledAt, false)}` : ''}</span>
          {t.code && !isPublic && (
            <Link href={`/ticket/${t.code}`} className="flex items-center gap-1 font-bold text-secondary hover:underline">
              <BsUpcScan size={12} /> Ticket &amp; barcode
            </Link>
          )}
        </div>
      )}
      {t.status === 'open' && !isPublic && (
        <CashoutPanel
          kind={t.kind} id={t.id} stake={t.stake} odds={t.odds}
          offer={offer !== undefined ? offer : t.cashout}
          onDone={() => onChanged?.()}
          compact={compact}
        />
      )}
    </article>
  );
}
