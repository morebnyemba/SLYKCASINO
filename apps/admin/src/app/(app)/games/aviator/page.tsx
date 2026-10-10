'use client';

import { useEffect, useState } from 'react';
import {
  BsActivity, BsAirplane, BsChatDots, BsCloudRainHeavy, BsEyeSlash, BsMicMute, BsRobot, BsBoxArrowUpRight, BsCashCoin, BsGraphUpArrow, BsPauseFill, BsPeople, BsPlayFill, BsShieldCheck,
} from 'react-icons/bs';
import {
  Badge, Btn, Field, Notice, PageHeader, Panel, StatTile, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { authedRequest, useApi } from '@/lib/use-api';

interface Settings {
  enabled: boolean; display_name: string; house_edge_percent: string; rtp_percent: string; min_bet: string; max_bet: string;
  max_win: string; max_multiplier: string; round_stake_limit: string; betting_seconds: number;
  bots_enabled: boolean; bot_count: number;
  chat_enabled: boolean; rain_enabled: boolean; rain_amount: string; rain_players: number; rain_every_minutes: number;
  rain_daily_budget: string; rain_given_today: string; last_rain_at: string | null;
}
interface ChatRow { id: number; kind: string; name: string; body: string; at: string; player_id: number | null; hidden: boolean }

const RAIN_FIELDS: { key: 'rain_amount' | 'rain_players' | 'rain_every_minutes' | 'rain_daily_budget'; label: string; hint: string }[] = [
  { key: 'rain_amount', label: 'Free bet per player ($)', hint: '$0.10–$100.' },
  { key: 'rain_players', label: 'Players per rain', hint: 'Picked at random from active depositors (1–100).' },
  { key: 'rain_every_minutes', label: 'Rain every (minutes)', hint: '0 = only when you press the button; at least 5.' },
  { key: 'rain_daily_budget', label: 'Daily budget ($)', hint: 'Most all rains together may give away per day.' },
];
interface Totals { rounds: number; bets: number; stake: string; payout: string; ggr: string; rtp_percent: string | null }
interface Stats {
  today: Totals; week: Totals; all_time: Totals; players_today: number;
  bots: { enabled: boolean; per_round: number; live_round: number };
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
  const [busy, setBusy] = useState<'save' | 'toggle' | 'bots' | null>(null);
  const [botCount, setBotCount] = useState('');
  const [rainForm, setRainForm] = useState<Record<string, string>>({});
  const { data: chatLog, refetch: refetchChat } = useApi<{ results: ChatRow[] }>('/admin/jet/chat/');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  useEffect(() => {
    if (settings) {
      setForm(Object.fromEntries(FIELDS.map((f) => [f.key, String(settings[f.key])])));
      setName(settings.display_name);
      setBotCount(String(settings.bot_count));
      setRainForm(Object.fromEntries(RAIN_FIELDS.map((f) => [f.key, String(settings[f.key])])));
    }
  }, [settings]);

  // Live round and takings refresh every few seconds.
  useEffect(() => {
    const t = window.setInterval(refetchStats, 4000);
    return () => window.clearInterval(t);
  }, [refetchStats]);

  async function post(path: string, body: Record<string, unknown>, ok: (data: Record<string, unknown>) => string) {
    if (!accessToken) return;
    setNotice(null);
    const res = await authedRequest<Record<string, unknown>>('POST', path, accessToken, body);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok(res.data ?? {}) });
    refetchChat(); refetchSettings();
  }

  async function put(body: Record<string, unknown>, ok: string, kind: 'save' | 'toggle' | 'bots') {
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
        actions={settings && (<div className="flex flex-wrap gap-2">
          <a href={`${config.playerUrl}/aviator`} target="_blank" rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-border bg-card px-4 text-sm font-semibold hover:border-secondary/60 hover:bg-muted/60">
            <BsBoxArrowUpRight size={13} /> Open game
          </a>
          {settings.enabled
          ? <Btn variant="danger" icon={BsPauseFill} busy={busy === 'toggle'}
              onClick={() => confirm('Pause the game? The round in the air finishes; no new rounds start.') && put({ enabled: false }, 'Paused — the current round finishes, then no new rounds start.', 'toggle')}>
              Pause game
            </Btn>
          : <Btn variant="success" icon={BsPlayFill} busy={busy === 'toggle'} onClick={() => put({ enabled: true }, 'The game is live again.', 'toggle')}>Resume game</Btn>}
        </div>)}
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

      <Panel
        title="Live game"
        description="The game exactly as players see it, live (you watch as a guest — staff can’t bet from here)."
        padded={false}
      >
        <iframe
          src={`${config.playerUrl}/play/aviator`}
          title="Live game"
          loading="lazy"
          className="block h-[560px] w-full rounded-b-2xl border-0 bg-[#0e0e0e]"
        />
      </Panel>

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
            There is no way to set a crash point — risk is managed only with the limits below.
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

      <Panel
        title="Simulated players"
        description="Fill the live bets list so the game feels busy. Display only: they never stake money and aren’t stored, so every figure on this page, the analytics, GGR and affiliate reports count real players only."
        actions={settings?.bots_enabled ? <Badge tone="green" dot>On</Badge> : <Badge tone="slate">Off</Badge>}
      >
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Players per round (0–1000)" hint="Each round gets 70–100% of this, joining through the countdown." className="w-64">
            <TextInput inputMode="numeric" value={botCount} onChange={(e) => setBotCount(e.target.value.replace(/[^0-9]/g, ''))} />
          </Field>
          <Btn variant="primary" icon={BsRobot} busy={busy === 'bots'}
            disabled={!settings || Number(botCount) === settings.bot_count || botCount === ''}
            onClick={() => put({ bot_count: Number(botCount) }, 'Saved — applies from the next round.', 'bots')}>
            Save count
          </Btn>
          {settings && (settings.bots_enabled
            ? <Btn variant="danger" busy={busy === 'bots'} onClick={() => put({ bots_enabled: false }, 'Simulated players are off from the next round.', 'bots')}>Turn off</Btn>
            : <Btn variant="success" busy={busy === 'bots'} onClick={() => put({ bots_enabled: true, bot_count: Number(botCount) || settings.bot_count }, 'Simulated players are on from the next round.', 'bots')}>Turn on</Btn>)}
        </div>
        {stats?.bots.enabled && (
          <p className="mt-3 text-xs text-muted-foreground">Round in play: {stats.bots.live_round} simulated players alongside {stats.live.bets} real bet{stats.live.bets === 1 ? '' : 's'}.</p>
        )}
        <p className="mt-3 flex items-start gap-2 rounded-xl bg-muted/40 p-3 text-xs text-muted-foreground">
          <BsShieldCheck className="mt-0.5 shrink-0 text-win" />
          While on, the game’s “How to play” tells players the bets list and the chat’s win shout-outs include simulated players. They can’t change a round — its crash point is fixed before betting opens.
        </p>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
        <Panel
          title="Chat & rain"
          description="Rain drops free bets on real players who deposited and played or chatted in the last 30 minutes. Free-bet winnings are paid as bonus credit, so they count as a promotion cost (NGR), never as GGR."
          actions={settings && <div className="flex gap-2">
            <Badge tone={settings.chat_enabled ? 'green' : 'slate'} dot>Chat {settings.chat_enabled ? 'on' : 'off'}</Badge>
            <Badge tone={settings.rain_enabled ? 'green' : 'slate'} dot>Auto rain {settings.rain_enabled ? 'on' : 'off'}</Badge>
          </div>}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {RAIN_FIELDS.map((f) => (
              <Field key={f.key} label={f.label} hint={f.hint}>
                <TextInput inputMode="decimal" value={rainForm[f.key] ?? ''} onChange={(e) => setRainForm((v) => ({ ...v, [f.key]: e.target.value.replace(/[^0-9.]/g, '') }))} />
              </Field>
            ))}
          </div>
          {settings && (
            <p className="mt-3 text-xs text-muted-foreground">
              Given today: <b className="text-foreground">{money(settings.rain_given_today)}</b> of {money(settings.rain_daily_budget)}
              {settings.last_rain_at && <> · last rain {new Date(settings.last_rain_at).toLocaleTimeString()}</>}
            </p>
          )}
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            {settings && <>
              <Btn variant="ghost" busy={busy === 'bots'} onClick={() => put({ chat_enabled: !settings.chat_enabled }, settings.chat_enabled ? 'Chat is off.' : 'Chat is on.', 'bots')}>
                {settings.chat_enabled ? 'Turn chat off' : 'Turn chat on'}
              </Btn>
              <Btn variant="ghost" busy={busy === 'bots'} onClick={() => put({ rain_enabled: !settings.rain_enabled }, settings.rain_enabled ? 'Automatic rain is off.' : 'Automatic rain is on.', 'bots')}>
                {settings.rain_enabled ? 'Stop auto rain' : 'Start auto rain'}
              </Btn>
            </>}
            <Btn variant="primary" busy={busy === 'save'}
              onClick={() => put({
                rain_amount: rainForm.rain_amount, rain_daily_budget: rainForm.rain_daily_budget,
                rain_players: Number(rainForm.rain_players), rain_every_minutes: Number(rainForm.rain_every_minutes),
              }, 'Rain settings saved.', 'save')}>
              Save rain settings
            </Btn>
            <Btn variant="success" icon={BsCloudRainHeavy}
              onClick={() => confirm(`Rain ${money(rainForm.rain_amount)} free bets on up to ${rainForm.rain_players} active players now?`)
                && post('/admin/jet/rain/', { players: Number(rainForm.rain_players), amount: rainForm.rain_amount },
                  (d) => `It rained: ${d.given} player(s) got a ${money(String(d.amount))} free bet.`)}>
              Make it rain now
            </Btn>
          </div>
        </Panel>

        <Panel title="Chat moderation" description="The latest messages. Hide anything abusive; mute a player for 24 hours." padded={false}
          actions={<BsChatDots className="text-muted-foreground" />}>
          <ul className="max-h-[420px] divide-y divide-border overflow-y-auto">
            {(chatLog?.results ?? []).map((m) => (
              <li key={m.id} className={cx('flex items-start gap-3 px-4 py-2.5 text-sm', m.hidden && 'opacity-50')}>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted-foreground">
                    <b className="text-foreground">{m.name}</b> {m.kind !== 'chat' && <Badge tone={m.kind === 'rain' ? 'indigo' : 'gold'}>{m.kind}</Badge>}
                    {m.player_id && <> · player #{m.player_id}</>} · {new Date(m.at).toLocaleTimeString()} {m.hidden && '· hidden'}
                  </p>
                  <p className="break-words">{m.body}</p>
                </div>
                {!m.hidden && (
                  <button title="Hide message" aria-label="Hide message" onClick={() => post(`/admin/jet/chat/${m.id}/hide/`, {}, () => 'Message hidden.')}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"><BsEyeSlash /></button>
                )}
                {m.player_id && (
                  <button title="Mute for 24 hours" aria-label="Mute player" onClick={() => confirm(`Mute ${m.name} in chat for 24 hours?`) && post('/admin/jet/chat/mute/', { player_id: m.player_id, hours: 24 }, () => `${m.name} is muted for 24 hours.`)}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-live"><BsMicMute /></button>
                )}
              </li>
            ))}
            {chatLog && chatLog.results.length === 0 && <li className="px-4 py-10 text-center text-sm text-muted-foreground">No messages yet.</li>}
          </ul>
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
