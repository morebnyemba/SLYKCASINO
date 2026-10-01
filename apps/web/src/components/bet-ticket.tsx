'use client';

import { useState } from 'react';
import { BsCheckCircleFill, BsChevronDown, BsCircle, BsDashCircle, BsXCircleFill } from 'react-icons/bs';

/** The match a bet or leg is on, as the API returns it (null for legacy free-text bets). */
export interface BetMatch {
  id: number;
  name: string;
  sport: string;
  starts_at: string | null;
  status: string;
  score_home: number | null;
  score_away: number | null;
}

export interface ApiBet {
  id: number;
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
}

export interface ApiSlip {
  id: number;
  stake: string;
  combined_odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
  legs: ApiSlipLeg[];
}

interface TicketLeg {
  id: number;
  match: string;
  pick: string;
  odds: number;
  result: string;
  info: BetMatch | null;
}

export interface Ticket {
  key: string;
  kind: 'single' | 'multiple';
  id: number;
  stake: number;
  odds: number;
  status: string;
  payout: number | null;
  placedAt: string;
  legs: TicketLeg[];
}

const SELECTION_LABEL: Record<string, string> = { home: 'Home', draw: 'Draw', away: 'Away' };

/** Bet labels are stored as "Arsenal v Chelsea — Match Result: Home". */
function toLeg(l: ApiSlipLeg, result: string): TicketLeg {
  const [label, ...rest] = l.event.split(' — ');
  const pick = l.outcome_label
    ? `${l.market_name ? `${l.market_name}: ` : ''}${l.outcome_label}`
    : rest.join(' — ') || SELECTION_LABEL[l.selection ?? ''] || '—';
  return { id: l.id, match: l.match?.name ?? label, pick, odds: Number(l.odds), result, info: l.match ?? null };
}

/** A single's result is its own status; a leg carries its own result. */
function singleResult(status: string) {
  return status === 'won' || status === 'lost' || status === 'void' ? status : 'pending';
}

export function ticketFromBet(b: ApiBet): Ticket {
  return {
    key: `b${b.id}`, kind: 'single', id: b.id, stake: Number(b.stake), odds: Number(b.odds),
    status: b.status, payout: b.payout == null ? null : Number(b.payout), placedAt: b.placed_at,
    legs: [toLeg(b, singleResult(b.status))],
  };
}

export function ticketFromSlip(s: ApiSlip): Ticket {
  return {
    key: `s${s.id}`, kind: 'multiple', id: s.id, stake: Number(s.stake), odds: Number(s.combined_odds),
    status: s.status, payout: s.payout == null ? null : Number(s.payout), placedAt: s.placed_at,
    legs: s.legs.map((l) => toLeg(l, l.result ?? 'pending')),
  };
}

/** Open (and in-flight) tickets first, then newest first. */
export function sortTickets(tickets: Ticket[]) {
  const live = (t: Ticket) => (isSettled(t.status) ? 1 : 0);
  return [...tickets].sort((a, b) => live(a) - live(b) || Date.parse(b.placedAt) - Date.parse(a.placedAt));
}

export function isSettled(status: string) {
  return status === 'won' || status === 'lost' || status === 'void' || status === 'rejected';
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
};

function ResultIcon({ result }: { result: string }) {
  if (result === 'won') return <BsCheckCircleFill className="text-win" size={13} aria-label="Won" />;
  if (result === 'lost') return <BsXCircleFill className="text-destructive" size={13} aria-label="Lost" />;
  if (result === 'void') return <BsDashCircle className="text-muted-foreground" size={13} aria-label="Void" />;
  return <BsCircle className="text-muted-foreground/60" size={13} aria-label="Pending" />;
}

function matchLine(m: BetMatch | null) {
  if (!m) return null;
  const hasScore = m.score_home != null && m.score_away != null;
  const live = !!m.status && !['NS', 'FT', 'AET', 'PEN', ''].includes(m.status);
  if (hasScore) {
    return (
      <span className="flex items-center gap-1.5">
        {live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-live" />}
        <b className="font-mono text-foreground">{m.score_home}–{m.score_away}</b>
        {m.status && <span className={live ? 'font-bold text-live' : ''}>{m.status}</span>}
      </span>
    );
  }
  if (!m.starts_at) return null;
  return (
    <span>
      {new Date(m.starts_at).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
    </span>
  );
}

/**
 * A placed bet rendered as a betting ticket: header with type, reference and
 * status; every selection with its match, pick, odds and result; then a
 * perforated footer with stake, odds and the (potential) return.
 */
export function BetTicket({ ticket, compact = false }: { ticket: Ticket; compact?: boolean }) {
  const t = ticket;
  const s = STATUS[t.status] ?? STATUS.pending;
  // In the narrow rail a long multiple starts folded to its first legs.
  const foldAt = compact ? 2 : Infinity;
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? t.legs : t.legs.slice(0, foldAt);
  const hidden = t.legs.length - shown.length;
  const potential = t.stake * t.odds;
  const settledLegs = t.legs.filter((l) => l.result !== 'pending').length;

  let returnLabel = 'Potential return';
  let returnValue = money(potential);
  let returnClass = 'text-win';
  if (t.status === 'won') { returnLabel = 'Paid out'; returnValue = money(t.payout ?? potential); }
  else if (t.status === 'lost') { returnLabel = 'Return'; returnValue = money(0); returnClass = 'text-muted-foreground'; }
  else if (t.status === 'void' || t.status === 'rejected') { returnLabel = 'Refunded'; returnValue = money(t.payout ?? t.stake); returnClass = 'text-foreground'; }

  const pad = compact ? 'px-3' : 'px-4';

  return (
    <article className="relative overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <span className={`absolute inset-y-0 left-0 w-1 ${s.bar}`} aria-hidden />

      <header className={`flex items-start justify-between gap-2 ${pad} pb-2 pt-3`}>
        <div className="min-w-0">
          <p className="text-[13px] font-extrabold">
            {t.kind === 'single' ? 'Single' : `Multiple · ${t.legs.length} legs`}
          </p>
          <p className="text-[11px] text-muted-foreground">
            #{t.kind === 'single' ? 'S' : 'M'}{t.id} · {new Date(t.placedAt).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            {t.kind === 'multiple' && !isSettled(t.status) && ` · ${settledLegs}/${t.legs.length} settled`}
          </p>
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-extrabold uppercase tracking-wide ${s.className}`}>
          {s.label}
        </span>
      </header>

      <ul className={`divide-y divide-border/70 ${pad}`}>
        {shown.map((l) => (
          <li key={l.id} className="flex gap-2.5 py-2">
            <span className="pt-0.5"><ResultIcon result={l.result} /></span>
            <div className="min-w-0 flex-1">
              <p className={`truncate text-[13px] font-bold ${l.result === 'lost' ? 'text-muted-foreground line-through' : ''}`}>{l.pick}</p>
              <p className="truncate text-[11.5px] text-muted-foreground">{l.match}</p>
              {matchLine(l.info) && <p className="mt-0.5 text-[11px] text-muted-foreground">{matchLine(l.info)}</p>}
            </div>
            <span className="shrink-0 self-start rounded-md bg-chip px-1.5 py-0.5 font-mono text-[12px] font-bold text-chip-foreground">
              {l.odds.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>
      {(hidden > 0 || (expanded && t.legs.length > foldAt)) && (
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
          <p className="text-[13px] font-bold">{money(t.stake)}</p>
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
    </article>
  );
}
