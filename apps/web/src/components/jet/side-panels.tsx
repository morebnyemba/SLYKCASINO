'use client';

import { useEffect, useState } from 'react';
import { BsCheckCircleFill, BsShieldCheck, BsXCircleFill, BsXLg } from 'react-icons/bs';
import { config } from '@/lib/config';
import { useApi } from '@/lib/use-api';
import { crashTone, fmtX, verifyRound, type JetBet, type JetSettings } from '@/lib/jet';

const money = (v: number | string) => `$${Number(v).toFixed(2)}`;

/** The round's bets (real players only) or the player's own history. */
export function BetsList({ bets, loggedIn }: { bets: JetBet[]; loggedIn: boolean }) {
  const [tab, setTab] = useState<'all' | 'mine'>('all');
  const { data: mine } = useApi<{ results: (JetBet & { created_at: string; crash_point: string | null })[] }>(
    tab === 'mine' && loggedIn ? '/jet/my-bets/' : null,
  );
  const total = bets.reduce((s, b) => s + Number(b.stake), 0);
  return (
    <section className="flex min-h-0 flex-col rounded-2xl border border-[#2c2d30] bg-[#1b1c1d] text-white">
      <div className="m-2 flex rounded-full border border-[#2c2d30] bg-[#141516] p-0.5 text-xs font-bold">
        {([['all', 'All bets'], ['mine', 'My bets']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex-1 rounded-full py-1.5 ${tab === id ? 'bg-[#2c2d30]' : 'text-white/60'}`}>{label}</button>
        ))}
      </div>
      {tab === 'all' ? (
        <>
          <div className="flex justify-between px-4 pb-2 text-[11px] font-semibold text-white/50">
            <span>{bets.length} bet{bets.length === 1 ? '' : 's'} this round</span>
            <span>{money(total)} staked</span>
          </div>
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 px-4 pb-1 text-[10.5px] font-bold uppercase text-white/40">
            <span>Player</span><span className="text-right">Bet</span><span className="text-right">X</span><span className="text-right">Win</span>
          </div>
          <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-2">
            {bets.length === 0 && <li className="px-2 py-6 text-center text-xs text-white/40">No bets yet this round.</li>}
            {bets.map((b) => (
              <li key={b.id} className={`grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-3 rounded-lg px-2 py-1.5 text-xs ${
                b.status === 'cashed' ? 'bg-[#123405] ring-1 ring-[#427f00]' : 'bg-[#101011]'
              }`}>
                <span className="truncate font-semibold">{b.player}</span>
                <span className="text-right tabular-nums">{money(b.stake)}</span>
                <span className={`text-right font-bold tabular-nums ${b.cashout_multiplier ? 'text-[#913ef8]' : 'text-white/30'}`}>
                  {b.cashout_multiplier ? fmtX(b.cashout_multiplier) : '—'}
                </span>
                <span className="text-right font-bold tabular-nums">{b.status === 'cashed' ? money(b.payout) : '—'}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-2">
          {!loggedIn && <li className="px-2 py-6 text-center text-xs text-white/40">Log in to see your bets.</li>}
          {loggedIn && (mine?.results ?? []).length === 0 && <li className="px-2 py-6 text-center text-xs text-white/40">No Jet bets yet.</li>}
          {(mine?.results ?? []).map((b) => (
            <li key={b.id} className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 rounded-lg bg-[#101011] px-2 py-1.5 text-xs">
              <span className="text-white/50">{new Date(b.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</span>
              <span>{money(b.stake)}{b.cashout_multiplier ? ` · ${fmtX(b.cashout_multiplier)}` : ''}</span>
              <span className={`font-bold ${b.status === 'cashed' ? 'text-[#22c55e]' : b.status === 'lost' ? 'text-white/40' : 'text-white/70'}`}>
                {b.status === 'cashed' ? money(b.payout) : b.status === 'lost' ? `Lost${b.crash_point ? ` @ ${fmtX(b.crash_point)}` : ''}` : b.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface RoundDetail {
  id: number; seed_hash: string; server_seed: string; crash_point: string; house_edge_percent: string;
  crashed_at: string; bet_count: number;
}

/** Recent crash points; tapping one opens its fairness check. */
export function HistoryStrip({ history, settings }: { history: { id: number; crash_point: string }[]; settings: JetSettings }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto">
        {history.map((h) => (
          <button key={h.id} onClick={() => setOpen(h.id)}
            className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-extrabold tabular-nums ${crashTone(Number(h.crash_point))}`}>
            {fmtX(h.crash_point)}
          </button>
        ))}
      </div>
      {open !== null && <FairnessModal roundId={open} settings={settings} onClose={() => setOpen(null)} />}
    </>
  );
}

function FairnessModal({ roundId, settings, onClose }: { roundId: number; settings: JetSettings; onClose: () => void }) {
  const [round, setRound] = useState<RoundDetail | null>(null);
  const [check, setCheck] = useState<{ hash: boolean; crash: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await fetch(`${config.apiUrl}/jet/rounds/${roundId}/`, { cache: 'no-store' });
      if (!res.ok) return;
      const r = (await res.json()) as RoundDetail;
      if (cancelled) return;
      setRound(r);
      const v = await verifyRound(r.server_seed, r.id, Number(r.house_edge_percent), Number(settings.max_multiplier));
      const hash = await v.hashOk(r.seed_hash);
      if (!cancelled) setCheck({ hash, crash: v.crash });
    })();
    return () => { cancelled = true; };
  }, [roundId, settings.max_multiplier]);

  const matches = check && round && check.hash && Math.abs(check.crash - Number(round.crash_point)) < 0.005;
  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-t-2xl border border-[#2c2d30] bg-[#1b1c1d] p-5 text-white sm:rounded-2xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Fairness check">
        <div className="mb-4 flex items-center gap-2">
          <BsShieldCheck className="text-[#22c55e]" size={18} />
          <h2 className="flex-1 font-extrabold">Round {roundId} — fairness check</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-2 text-white/60 hover:bg-white/10"><BsXLg size={13} /></button>
        </div>
        {!round ? <p className="text-sm text-white/60">Loading…</p> : (
          <div className="space-y-3 text-sm">
            <Row label="Crash point" value={fmtX(round.crash_point)} />
            <Row label="Seed hash (published before betting)" value={round.seed_hash} mono />
            <Row label="Server seed (revealed after the crash)" value={round.server_seed} mono />
            <Row label="House edge" value={`${Number(round.house_edge_percent).toFixed(2)}% (RTP ${(100 - Number(round.house_edge_percent)).toFixed(2)}%)`} />
            <div className={`flex items-center gap-2 rounded-xl px-3 py-2.5 font-bold ${matches ? 'bg-[#22c55e]/15 text-[#22c55e]' : 'bg-white/5 text-white/70'}`}>
              {check ? (matches ? <BsCheckCircleFill /> : <BsXCircleFill />) : null}
              {!check ? 'Checking in your browser…'
                : matches ? 'Verified: the seed matches its hash and gives this exact crash point.'
                : 'This round doesn’t verify — please contact support.'}
            </div>
            <p className="text-xs leading-relaxed text-white/50">
              How it works: crash = floor(100 × (1 − edge) ÷ (1 − r)) ÷ 100, where r is the first 52 bits of
              HMAC-SHA256(server seed, “jet:{roundId}”) ÷ 2⁵². The seed’s hash is shown before any bet, so the
              result can’t be changed after bets come in.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] font-bold uppercase tracking-wide text-white/40">{label}</p>
      <p className={`break-all ${mono ? 'font-mono text-xs' : 'font-bold'}`}>{value}</p>
    </div>
  );
}
