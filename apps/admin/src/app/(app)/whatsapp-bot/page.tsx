'use client';

import { useEffect, useState } from 'react';
import { BsWhatsapp } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, Switch, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface BotSettings {
  enabled: boolean; allow_betting: boolean; allow_deposits: boolean;
  max_stake: string; daily_cap: string; pin_above: string;
  configured: boolean; webhook_path: string;
  linked_players: number; messages_24h: number; tickets_24h: number; staked_24h: string;
}

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;

/** WhatsApp betting bot: on/off switches, chat stake limits, usage, and the Meta setup checklist. */
export default function WhatsAppBotPage() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<BotSettings>('/admin/chatbot/');
  const [form, setForm] = useState<BotSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true);
    const { enabled, allow_betting, allow_deposits, max_stake, daily_cap, pin_above } = form;
    const res = await authedRequest('PUT', '/admin/chatbot/', accessToken,
      { enabled, allow_betting, allow_deposits, max_stake, daily_cap, pin_above });
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'WhatsApp bot settings saved.' });
    refetch();
  }
  const set = (k: 'max_stake' | 'daily_cap' | 'pin_above') => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((v) => v && { ...v, [k]: e.target.value.replace(/[^0-9.]/g, '') });
  const webhook = typeof window !== 'undefined' && data ? `${window.location.origin}${data.webhook_path}` : '';

  return (
    <div className="space-y-6">
      <PageHeader icon={BsWhatsapp} eyebrow="Channels" title="WhatsApp bot"
        description="Players browse matches by ID, build a slip, bet (after replying YES) and deposit from WhatsApp. Every bet goes through the same rules as the website." />

      <div className="grid gap-3 sm:grid-cols-4">
        {([['Linked players', data?.linked_players ?? '—'], ['Messages (24h)', data?.messages_24h ?? '—'],
          ['Tickets (24h)', data?.tickets_24h ?? '—'], ['Staked (24h)', data ? money(data.staked_24h) : '—']] as [string, string | number][]).map(([k, v]) => (
          <div key={k} className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">{k}</p>
            <p className="mt-1 text-xl font-bold tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <Panel title="Switches and limits"
        actions={data && (data.configured ? <Badge tone="green" dot>Connected to Meta</Badge> : <Badge tone="red" dot>Not connected</Badge>)}>
        {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
        {form && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-6">
              <Switch checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} label="Bot on" />
              <Switch checked={form.allow_betting} onChange={(v) => setForm({ ...form, allow_betting: v })} label="Betting" />
              <Switch checked={form.allow_deposits} onChange={(v) => setForm({ ...form, allow_deposits: v })} label="Deposits" />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Most per ticket ($)" hint="The highest stake one chat ticket may have.">
                <TextInput inputMode="decimal" value={form.max_stake} onChange={set('max_stake')} />
              </Field>
              <Field label="Daily chat limit per player ($)" hint="Total stakes through chat per day. Players can set lower.">
                <TextInput inputMode="decimal" value={form.daily_cap} onChange={set('daily_cap')} />
              </Field>
              <Field label="PIN needed above ($)" hint="Players with a PIN always use it. 0 = every bet needs a PIN.">
                <TextInput inputMode="decimal" value={form.pin_above} onChange={set('pin_above')} />
              </Field>
            </div>
            <Btn variant="primary" busy={busy} onClick={save}>Save</Btn>
          </div>
        )}
      </Panel>

      <Panel title="Connecting the WhatsApp number (Meta)">
        <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
          <li>In Meta Business, create an app with the <b className="text-foreground">WhatsApp</b> product and add a phone number. Use a number you can afford to lose, not your main support line.</li>
          <li>Create a system user with a permanent token that has <code>whatsapp_business_messaging</code>.</li>
          <li>Put these in <code>.env.prod</code> and redeploy: <code>WHATSAPP_TOKEN</code>, <code>WHATSAPP_PHONE_NUMBER_ID</code>, <code>WHATSAPP_APP_SECRET</code>, <code>WHATSAPP_VERIFY_TOKEN</code> (any long random string) and <code>WHATSAPP_DISPLAY_NUMBER</code> (shown to players).</li>
          <li>Under WhatsApp → Configuration, set the callback URL to <code className="text-foreground">{webhook || '…/api/chatbot/whatsapp/webhook/'}</code> with the same verify token, and subscribe to <b className="text-foreground">messages</b>.</li>
          <li>Meta’s policy restricts real-money gambling on WhatsApp without its written approval. Apply for it; until then the number can be banned if reported.</li>
        </ol>
      </Panel>
    </div>
  );
}
