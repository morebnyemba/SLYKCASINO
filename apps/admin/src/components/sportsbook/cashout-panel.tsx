'use client';

import { useEffect, useState } from 'react';
import { BsCashCoin } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, Switch, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface CashoutSettings {
  enabled: boolean;
  allow_partial: boolean;
  in_play: boolean;
  margin_percent: string;
  min_amount: string;
  stats: { today: { count: number; total: string }; all_time: { count: number; total: string } };
}

/** Cash-out switches, margin and minimum — and what has been cashed out. */
export function CashoutSettingsPanel() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<CashoutSettings>('/admin/sportsbook/cashout/');
  const [form, setForm] = useState({ enabled: true, allow_partial: true, in_play: true, margin_percent: '5', min_amount: '1' });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        enabled: data.enabled, allow_partial: data.allow_partial, in_play: data.in_play,
        margin_percent: data.margin_percent, min_amount: data.min_amount,
      });
    }
  }, [data]);

  if (!data) return <Panel title="Cash-out"><div className="h-32 animate-pulse rounded-xl bg-muted/50" /></Panel>;

  const dirty = form.enabled !== data.enabled || form.allow_partial !== data.allow_partial || form.in_play !== data.in_play
    || Number(form.margin_percent) !== Number(data.margin_percent) || Number(form.min_amount) !== Number(data.min_amount);
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    if (!accessToken) return;
    setBusy(true); setNotice(null);
    const res = await authedRequest('PUT', '/admin/sportsbook/cashout/', accessToken, form);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Cash-out settings saved.' });
    if (!res.error) refetch();
  }

  // Worked example for the margin: $10 at 2.00, price now 1.25.
  const example = (10 * 2 / 1.25) * (1 - (Number(form.margin_percent) || 0) / 100);

  return (
    <Panel
      title="Cash-out"
      description="Let players settle open tickets early at what they are worth right now."
      actions={data.enabled ? <Badge tone="green" dot>On</Badge> : <Badge tone="slate">Off</Badge>}
    >
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <div className="space-y-3 rounded-xl border border-border/70 p-4">
            {([
              ['enabled', 'Offer cash-out', 'Show the cash-out button on open tickets.'],
              ['allow_partial', 'Partial cash-out', 'Players can take part of the value and leave the rest riding.'],
              ['in_play', 'Cash-out in play', 'Keep offering it while matches are being played (needs live odds).'],
            ] as const).map(([key, label, hint]) => (
              <label key={key} className="flex items-center justify-between gap-4">
                <span>
                  <span className="block text-sm font-semibold">{label}</span>
                  <span className="block text-xs text-muted-foreground">{hint}</span>
                </span>
                <Switch checked={form[key]} onChange={(v) => set(key, v)} label={label} disabled={key !== 'enabled' && !form.enabled} />
              </label>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Margin (%)" hint={`Taken off the fair value. E.g. $10 at 2.00, now priced 1.25 → offer ${money(example)}.`}>
              <TextInput inputMode="decimal" value={form.margin_percent} onChange={(e) => set('margin_percent', e.target.value.replace(/[^0-9.]/g, ''))} />
            </Field>
            <Field label="Minimum offer ($)" hint="Smaller offers aren’t shown; partial cash-outs keep at least this much on each side.">
              <TextInput inputMode="decimal" value={form.min_amount} onChange={(e) => set('min_amount', e.target.value.replace(/[^0-9.]/g, ''))} />
            </Field>
          </div>
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
          <p className="text-xs text-muted-foreground">
            Offers use live prices only: when a market is suspended, or a match has kicked off without in-play odds, there is no offer.
          </p>
        </div>
      </div>
    </Panel>
  );
}
