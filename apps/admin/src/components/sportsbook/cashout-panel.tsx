'use client';

import { useEffect, useState } from 'react';
import { BsCashCoin, BsShieldCheck } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, Switch, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Form {
  enabled: boolean; allow_partial: boolean; in_play: boolean; allow_singles: boolean; allow_multiples: boolean;
  suspend_on_feed_pause: boolean; block_flagged_players: boolean;
  margin_percent: string; live_margin_percent: string; min_amount: string; max_amount: string;
  max_percent_of_win: number | string; min_seconds_after_bet: number | string; live_until_minute: number | string;
  live_delay_seconds: number | string;
}
interface CashoutSettings extends Form {
  stats: { today: { count: number; total: string }; all_time: { count: number; total: string } };
  recent: { id: number; ticket: string; player_id: number; amount: string; stake: string; potential: string; full: boolean; created_at: string }[];
}
const FORM_KEYS: (keyof Form)[] = [
  'enabled', 'allow_partial', 'in_play', 'allow_singles', 'allow_multiples', 'suspend_on_feed_pause', 'block_flagged_players',
  'margin_percent', 'live_margin_percent', 'min_amount', 'max_amount', 'max_percent_of_win', 'min_seconds_after_bet',
  'live_until_minute', 'live_delay_seconds',
];
const pick = (d: CashoutSettings): Form => Object.fromEntries(FORM_KEYS.map((k) => [k, d[k]])) as unknown as Form;

/** Cash-out: switches, the house-protection rules, and what has been cashed out. */
export function CashoutSettingsPanel() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<CashoutSettings>('/admin/sportsbook/cashout/');
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(pick(data)); }, [data]);

  if (!data || !form) return <Panel title="Cash-out"><div className="h-32 animate-pulse rounded-xl bg-muted/50" /></Panel>;
  const dirty = FORM_KEYS.some((k) => String(form[k]) !== String(data[k]));
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => f && ({ ...f, [k]: v }));
  const num = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value.replace(/[^0-9.]/g, '') as never);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true); setNotice(null);
    const res = await authedRequest('PUT', '/admin/sportsbook/cashout/', accessToken, form);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Cash-out settings saved.' });
    if (!res.error) refetch();
  }

  // Worked example: $10 at 2.00, the pick now priced 1.25, in play.
  const fair = 10 * 2 / 1.25;
  const capPct = Number(form.max_percent_of_win) || 0;
  let example = fair * (1 - (Number(form.live_margin_percent) || 0) / 100);
  if (capPct) example = Math.min(example, 20 * capPct / 100);
  if (Number(form.max_amount) > 0) example = Math.min(example, Number(form.max_amount));

  const switches: [keyof Form, string, string][] = [
    ['enabled', 'Offer cash-out', 'Show the cash-out button on open tickets.'],
    ['in_play', 'Cash-out on live tickets', 'Keep offering it while matches are being played (live prices only).'],
    ['allow_partial', 'Partial cash-out', 'Take part of the value and leave the rest riding.'],
    ['allow_singles', 'On single bets', 'Offer it on singles.'],
    ['allow_multiples', 'On multiples', 'Offer it on multiples (never on same-match combos).'],
    ['suspend_on_feed_pause', 'Stop while the feed pauses a match', 'A dangerous attack, a VAR check: no cash-out until the feed resumes.'],
    ['block_flagged_players', 'Not for accounts under review', 'Players the fraud engine flagged can’t cash out.'],
  ];

  return (
    <Panel title="Cash-out" description="Let players settle open tickets early at what they are worth now, always with the house protected."
      actions={data.enabled ? <Badge tone="green" dot>On</Badge> : <Badge tone="slate">Off</Badge>}>
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <div className="space-y-3 rounded-xl border border-border/70 p-4">
            {switches.map(([key, label, hint]) => (
              <label key={key} className="flex items-center justify-between gap-4">
                <span>
                  <span className="block text-sm font-semibold">{label}</span>
                  <span className="block text-xs text-muted-foreground">{hint}</span>
                </span>
                <Switch checked={!!form[key]} onChange={(v) => set(key, v as never)} label={label} disabled={key !== 'enabled' && !form.enabled} />
              </label>
            ))}
          </div>
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><BsShieldCheck /> House protection</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Margin before kick-off (%)" hint="Taken off the fair value.">
              <TextInput inputMode="decimal" value={String(form.margin_percent)} onChange={num('margin_percent')} />
            </Field>
            <Field label="Margin in play (%)" hint={`Prices move fastest live. E.g. $10 at 2.00, now 1.25 → offer ${money(example)}.`}>
              <TextInput inputMode="decimal" value={String(form.live_margin_percent)} onChange={num('live_margin_percent')} />
            </Field>
            <Field label="Offer at most (% of the possible win)" hint="An offer never goes above this share of what the ticket could still win. 0 = no cap.">
              <TextInput inputMode="numeric" value={String(form.max_percent_of_win)} onChange={num('max_percent_of_win')} />
            </Field>
            <Field label="Most one cash-out pays ($)" hint="0 = no cap.">
              <TextInput inputMode="decimal" value={String(form.max_amount)} onChange={num('max_amount')} />
            </Field>
            <Field label="Minimum offer ($)" hint="Smaller offers aren’t shown.">
              <TextInput inputMode="decimal" value={String(form.min_amount)} onChange={num('min_amount')} />
            </Field>
            <Field label="Wait after placing (seconds)" hint="No cash-out on a ticket younger than this. Stops bet-and-cash-out tricks.">
              <TextInput inputMode="numeric" value={String(form.min_seconds_after_bet)} onChange={num('min_seconds_after_bet')} />
            </Field>
            <Field label="No live cash-out from minute" hint="Late in a match prices are least reliable. 0 = all match.">
              <TextInput inputMode="numeric" value={String(form.live_until_minute)} onChange={num('live_until_minute')} />
            </Field>
            <Field label="Live cash-out check (seconds)" hint="In play the cash-out waits this long and is priced again; a goal meanwhile cancels it. 0–10.">
              <TextInput inputMode="numeric" value={String(form.live_delay_seconds)} onChange={num('live_delay_seconds')} />
            </Field>
          </div>
          <p className="text-xs text-muted-foreground">
            Always on: no offer during the bet stop after a goal, on a held or locked match, on a price the live feed isn’t quoting
            now, on bonus tickets, or once any pick has lost.
          </p>
          {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
          <div className="flex justify-end">
            <Btn variant="primary" onClick={save} busy={busy} disabled={!dirty}>Save cash-out settings</Btn>
          </div>
        </div>
        <div className="grid content-start gap-3">
          {([['Cashed out today', data.stats.today], ['All time', data.stats.all_time]] as const).map(([label, s]) => (
            <div key={label} className="flex items-center gap-3 rounded-xl border border-border/70 bg-background/40 p-4">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gold/15 text-gold"><BsCashCoin size={17} /></span>
              <span>
                <span className="block text-xs font-semibold text-muted-foreground">{label}</span>
                <span className="block text-lg font-extrabold tabular-nums">{money(s.total)}</span>
                <span className="block text-xs text-muted-foreground">{s.count} cash-out{s.count === 1 ? '' : 's'}</span>
              </span>
            </div>
          ))}
          <div className="rounded-xl border border-border/70 p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">Latest cash-outs</p>
            {!data.recent.length ? <p className="text-xs text-muted-foreground">None yet.</p> : (
              <ul className="max-h-80 space-y-1.5 overflow-y-auto text-xs">
                {data.recent.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate"><b>{c.ticket}</b> · player {c.player_id}{!c.full && ' · partial'}</span>
                    <span className="shrink-0 tabular-nums">
                      {money(c.amount)} <span className="text-muted-foreground">of {money(c.potential)} possible</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
