'use client';

import { useEffect, useState } from 'react';
import { BsActivity, BsAirplane, BsCashCoin, BsGraphUpArrow, BsPauseFill, BsPeople, BsPlayFill, BsShieldCheck } from 'react-icons/bs';
import {
  Badge, Btn, Field, Notice, PageHeader, Panel, StatTile, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Settings {
  enabled: boolean; display_name: string; house_edge_percent: string; rtp_percent: string; min_bet: string; max_bet: string;
  max_win: string; max_multiplier: string; round_stake_limit: string; betting_seconds: number;
}
interface Totals { rounds: number; bets: number; stake: string; payout: string; ggr: string; rtp_percent: string | null }
interface Stats {
  today: Totals; week: Totals; all_time: Totals; players_today: number;
  live: { round: number | null; status: string | null; bets: number; stake: string; riding: number; max_exposure: string };
  rounds: { id: number; crash_point: string; bet_count: number; total_stake: string; total_payout: string; ggr: string;
    seed_hash: string; server_seed: string; crashed_at: string }[];
}

const FIELDS: { key: keyof Settings; label: string; hint: string; suffix?: string }[] = [
  { key: 'house_edge_percent', label: 'House edge (%)', hint: 'Return to player is 100% minus this. 3% is typical.' },
  { key: 'min_bet', label: 'Minimum bet ($)', hint: 'Smallest stake per bet.' },
  { key: 'max_bet', label: 'Maximum bet ($)', hint: 'Largest stake per bet.' },
  { key: 'max_win', label: 'Max win per bet ($)', hint: 'A bet that reaches it is cashed out automatically.' },
  { key: 'max_multiplier', label: 'Highest multiplier (x)', hint: 'The plane never goes past this.' },
  { key: 'round_stake_limit', label: 'Stake limit per round ($)', hint: 'Total stakes a round accepts; later bets wait for the next round.' },
  { key: 'betting_seconds', label: 'Countdown (seconds)', hint: 'Betting window before each take-off (3–30).' },
];

/** The crash game — takings, the live round, limits and the round log. No crash-point controls exist by design. */
export default function CrashGameAdminPage() {
  const { accessToken } = useAuth();
  const { data: settings, refetch: refetchSettings } = useApi<Settings>('/admin/jet/settings/');
  const { data: stats, refetch: refetchStats } = useApi<Stats>('/admin/jet/stats/');
  const [form, setForm] = useState<Record<string, string>>({});
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<'save' | 'toggle' | null>(null);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  useEffect(() => {
    if (settings) {
      setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(settings[f.key])])));
      setName(settings.display_name);
    }
  }, [settings]);

  // Live round and takings refresh every few seconds.
  useEffect(() => {
    const t = window.setInterval(refetchStats, 4000);
    return () => window.clearInterval(t);
  }, [refetchStats]);

  async function put(body: Record<string, unknown>, ok: string, kind: 'save' | 'toggle') {
    if (!accessToken) return;
    setBusy(kind); setNotice(null);
    const res = await authedRequest('PUT', '/admin/jet/settings/', accessToken, body);
    setBusy(null);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok });
    if (!res.error) { refetchSettings(); refetchStats(); }
  }

  const dirty = settings && (name.trim() !== settings.display_name || FIELDS.some((f) => Number(form[f.key]) !== Number(settings[f.key])));
  const live = stats?.live;
  const t = stats?.today;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BsAirplane}
        eyebrow="Games"
        title={settings?.display_name ?? 'Aviator'}
        description="The multiplayer crash game: takings, the round in the air, limits and every round’s fairness proof."
        actions={settings && (settings.enabled
          ? <Btn variant="danger" icon={BsPauseFill} busy={busy === 'toggle'}
              onClick={() => confirm('Pause the game? The round in the air finishes; no new rounds start.') && put({ enabled: false }, 'Paused — the current round finishes, then no new rounds start.', 'toggle')}>
              Pause game
            </Btn>
          : <Btn variant="success" icon={BsPlayFill} busy={busy === 'toggle'} onClick={() => put({ enabled: true }, 'The game is live again.', 'toggle')}>Resume game</Btn>)}
      />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatTile loading={!stats} icon={BsCashCoin} tone="indigo" label="Staked today" value={money(t?.stake)}
          hint={t ? `${t.bets} bets · ${t.rounds} rounds` : undefined} />
        <StatTile loading={!stats} icon={BsGraphUpArrow} tone={Number(t?.ggr ?? 0) < 0 ? 'red' : 'green'} label="GGR today" value={money(t?.ggr)}
          hint={t ? `Paid out ${money(t.payout)}` : undefined} />
        <StatTile loading={!stats} icon={BsActivity} tone="gold" label="RTP today" value={t?.rtp_percent ? `${t.rtp_percent}%` : '—'}
          hint={settings ? `Target ${settings.rtp_percent}% — settles toward it over many rounds` : undefined} />
        <StatTile loading={!stats} icon={BsPeople} tone="slate" label="Players today" value={stats?.players_today ?? 0}
          hint={stats ? `7 days: ${money(stats.week.ggr)} GGR · all time ${money(stats.all_time.ggr)}` : undefined} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.3fr]">
        <Panel title="In the air now" description="The live round. Its crash point stays secret until it crashes — for staff too."
          actions={settings?.enabled ? <Badge tone="green" dot>Running</Badge> : <Badge tone="gold">Paused</Badge>}>
          {live?.round ? (
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div><dt className="text-xs text-muted-foreground">Round</dt><dd className="text-lg font-extrabold">#{live.round} <Badge tone={live.status === 'flying' ? 'red' : 'indigo'} dot>{live.status}</Badge></dd></div>
              <div><dt className="text-xs text-muted-foreground">Bets</dt><dd className="text-lg font-extrabold">{live.bets} <span className="text-sm font-semibold text-muted-foreground">({live.riding} riding)</span></dd></div>
              <div><dt className="text-xs text-muted-foreground">Staked</dt><dd className="text-lg font-extrabold">{money(live.stake)}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Most it could pay</dt><dd className="text-lg font-extrabold">{money(live.max_exposure)}</dd></div>
            </dl>
          ) : <p className="text-sm text-muted-foreground">Between rounds.</p>}
          <p className="mt-4 flex items-start gap-2 rounded-xl bg-muted/40 p-3 text-xs text-muted-foreground">
            <BsShieldCheck className="mt-0.5 shrink-0 text-win" />
            Outcomes are provably fair: each round’s seed hash is shown to players before betting and the seed after the crash.
            There are no automated players and no way to set a crash point — risk is managed only with the limits below.
          </p>
        </Panel>

        <Panel title="Name, limits & house edge" description="Shown to players in the game’s rules. Changes apply from the next round.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Game name" hint="Shown in the game header and page title, e.g. “BetBlits Aviator”." className="sm:col-span-2">
              <TextInput value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
            </Field>
            {FIELDS.map((f) => (
              <Field key={f.key} label={f.label} hint={f.hint}>
                <TextInput inputMode="decimal" value={form[f.key] ?? ''} onChange={(e) => setForm((v) => ({ ...v, [f.key]: e.target.value.replace(/[^0-9.]/g, '') }))} />
              </Field>
            ))}
          </div>
          <div className="mt-4 flex justify-end">
            <Btn variant="primary" busy={busy === 'save'} disabled={!dirty}
              onClick={() => put({ display_name: name.trim(), ...Object.fromEntries(FIELDS.map((f) => [f.key, f.key === 'betting_seconds' ? Number(form[f.key]) : form[f.key]])) }, 'Saved — limits apply from the next round.', 'save')}>
              Save limits
            </Btn>
          </div>
        </Panel>
      </div>

      <Panel title="Recent rounds" description="Every finished round with its seed, so any result can be re-checked." padded={false}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead><tr>
              <th className={thClass}>Round</th><th className={thClass}>Crash</th><th className={thClass}>Bets</th>
              <th className={thClass}>Staked</th><th className={thClass}>Paid</th><th className={thClass}>GGR</th>
              <th className={thClass}>Seed hash / seed</th><th className={thClass}>Time</th>
            </tr></thead>
            <tbody>
              {(stats?.rounds ?? []).map((r) => (
                <tr key={r.id} className={trClass}>
                  <td className={cx(tdClass, 'font-semibold')}>#{r.id}</td>
                  <td className={cx(tdClass, 'font-mono font-bold', Number(r.crash_point) >= 10 ? 'text-gold' : Number(r.crash_point) >= 2 ? 'text-secondary' : 'text-muted-foreground')}>{Number(r.crash_point).toFixed(2)}x</td>
                  <td className={tdClass}>{r.bet_count}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(r.total_stake)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(r.total_payout)}</td>
                  <td className={cx(tdClass, 'font-semibold tabular-nums', Number(r.ggr) < 0 ? 'text-live' : 'text-win')}>{money(r.ggr)}</td>
                  <td className={cx(tdClass, 'max-w-[220px]')}>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground" title={r.seed_hash}>{r.seed_hash}</span>
                    <span className="block truncate font-mono text-[11px]" title={r.server_seed}>{r.server_seed}</span>
                  </td>
                  <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(r.crashed_at).toLocaleTimeString()}</td>
                </tr>
              ))}
              {stats && stats.rounds.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">No rounds yet — start the Jet service on the server.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
