'use client';

import { useEffect, useState } from 'react';
import { BsWhatsapp } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, Switch, Tabs, TextInput } from '@/components/console/ui';
import { DeliveryHealth, Inbox } from '@/components/chatbot/inbox';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

type Source = 'admin' | 'env' | 'default' | 'unset' | 'unreadable';
interface PlainSetting { label: string; source: Source; env: string; secret: false; value: string }
interface SecretSetting { label: string; source: Source; env: string; secret: true; set: boolean; hint: string }
type ConnKey = 'phone_number_id' | 'display_number' | 'token' | 'app_secret' | 'verify_token' | 'graph_version' | 'time_zone';
type Connection = Record<ConnKey, PlainSetting | SecretSetting> & { updated_by: string; updated_at: string | null };

interface BotSettings {
  enabled: boolean; allow_betting: boolean; allow_deposits: boolean;
  max_stake: string; daily_cap: string; pin_above: string;
  configured: boolean; webhook_path: string; webhook_url: string;
  linked_players: number; messages_24h: number; tickets_24h: number; staked_24h: string;
  connection: Connection; can_edit_connection: boolean;
}
interface CheckResult { ok: boolean; error?: string; verified_name?: string; display_phone_number?: string; quality_rating?: string }

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;
const PLAIN: { key: ConnKey; hint: string; placeholder: string }[] = [
  { key: 'phone_number_id', hint: 'Meta → WhatsApp → API setup → Phone number ID (digits, not the number itself).', placeholder: '123456789012345' },
  { key: 'display_number', hint: 'The bot’s number as players should save it. Shown on the website.', placeholder: '+263 77 000 1111' },
  { key: 'graph_version', hint: 'Meta’s Graph API version. Leave as is unless Meta retires it.', placeholder: 'v21.0' },
  { key: 'time_zone', hint: 'Kick-off times in chat and the daily chat limit’s day.', placeholder: 'Africa/Harare' },
];
const SECRETS: { key: ConnKey; hint: string }[] = [
  { key: 'token', hint: 'A permanent system-user token with whatsapp_business_messaging.' },
  { key: 'app_secret', hint: 'Meta app → Settings → Basic → App secret. Checks every webhook is really from Meta.' },
  { key: 'verify_token', hint: 'Any long random string. Enter the same one in Meta’s webhook settings.' },
];
const SOURCE: Record<Source, { label: string; tone: 'green' | 'slate' | 'red' | 'gold' }> = {
  admin: { label: 'Set here', tone: 'green' }, env: { label: 'From .env.prod', tone: 'slate' },
  default: { label: 'Default', tone: 'slate' }, unset: { label: 'Not set', tone: 'red' },
  unreadable: { label: 'Re-enter (key changed)', tone: 'gold' },
};

function randomToken() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** WhatsApp betting bot: the Meta connection, on/off switches, chat stake limits and usage. */
export default function WhatsAppBotPage() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<BotSettings>('/admin/chatbot/');
  const [form, setForm] = useState<BotSettings | null>(null);
  const [conn, setConn] = useState<Partial<Record<ConnKey, string>>>({});
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const [check, setCheck] = useState<CheckResult | null>(null);
  useEffect(() => {
    if (!data) return;
    setForm(data);
    const plain: Partial<Record<ConnKey, string>> = {};
    for (const { key } of PLAIN) {
      const s = data.connection[key] as PlainSetting;
      plain[key] = s.source === 'admin' ? s.value : '';
    }
    setConn(plain);
  }, [data]);

  async function put(body: Record<string, unknown>, ok: string, key: string) {
    if (!accessToken) return;
    setBusy(key); setNotice(null);
    const res = await authedRequest('PUT', '/admin/chatbot/', accessToken, body);
    setBusy('');
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok });
    if (!res.error) refetch();
  }

  function saveLimits() {
    if (!form) return;
    const { enabled, allow_betting, allow_deposits, max_stake, daily_cap, pin_above } = form;
    void put({ enabled, allow_betting, allow_deposits, max_stake, daily_cap, pin_above }, 'Switches and limits saved.', 'limits');
  }

  function saveConnection() {
    // Plain fields: what's in the box (blank = clear, so .env.prod applies). Secrets: only when typed.
    const body: Record<string, unknown> = { clear: [] as string[] };
    for (const { key } of PLAIN) {
      const v = (conn[key] ?? '').trim();
      if (v) body[key] = v;
      else if ((data?.connection[key] as PlainSetting).source === 'admin') (body.clear as string[]).push(key);
    }
    for (const { key } of SECRETS) if ((conn[key] ?? '').trim()) body[key] = conn[key]!.trim();
    void put({ connection: body }, 'WhatsApp connection saved. It applies to the next message.', 'conn').then(() =>
      setConn((c) => ({ ...c, token: '', app_secret: '', verify_token: '' })));
  }

  async function testConnection() {
    if (!accessToken) return;
    setBusy('test'); setCheck(null);
    const res = await authedPost<CheckResult>('/admin/chatbot/test/', {}, accessToken);
    setBusy('');
    setCheck(res.data ?? { ok: false, error: res.error });
  }

  const set = (k: 'max_stake' | 'daily_cap' | 'pin_above') => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((v) => v && { ...v, [k]: e.target.value.replace(/[^0-9.]/g, '') });
  const webhook = data?.webhook_url ?? '';
  const editable = !!data?.can_edit_connection;
  const [tab, setTab] = useState<'inbox' | 'setup'>('inbox');

  return (
    <div className="space-y-6">
      <PageHeader icon={BsWhatsapp} eyebrow="Channels" title="WhatsApp bot"
        description="Players browse matches by ID, build a ticket, press Confirm to bet, and deposit from WhatsApp. Every bet goes through the same rules as the website." />

      <div className="grid gap-3 sm:grid-cols-4">
        {([['Linked players', data?.linked_players ?? '—'], ['Messages (24h)', data?.messages_24h ?? '—'],
          ['Tickets (24h)', data?.tickets_24h ?? '—'], ['Staked (24h)', data ? money(data.staked_24h) : '—']] as [string, string | number][]).map(([k, v]) => (
          <div key={k} className="rounded-xl border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">{k}</p>
            <p className="mt-1 text-xl font-bold tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <Tabs value={tab} onChange={setTab} items={[{ id: 'inbox', label: 'Inbox' }, { id: 'setup', label: 'Setup & limits' }]} />

      {tab === 'inbox' && (
        <>
          <DeliveryHealth />
          <Inbox />
        </>
      )}

      {tab === 'setup' && (<>
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <Panel title="WhatsApp connection (Meta Cloud API)"
        description={editable
          ? 'Saved here, these replace the WHATSAPP_* values in .env.prod (clear a box to use .env.prod again). Secrets are stored encrypted and never shown again; type a new one to replace it.'
          : 'Only a superuser can change the connection.'}
        actions={data && (data.configured ? <Badge tone="green" dot>Connected</Badge> : <Badge tone="red" dot>Not connected</Badge>)}>
        {data && (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              {PLAIN.map(({ key, hint, placeholder }) => {
                const s = data.connection[key] as PlainSetting;
                return (
                  <Field key={key} label={s.label} hint={<>{hint} <Badge tone={SOURCE[s.source].tone}>{SOURCE[s.source].label}</Badge></>}>
                    <TextInput value={conn[key] ?? ''} disabled={!editable}
                      placeholder={s.source !== 'admin' && s.value ? s.value : placeholder}
                      onChange={(e) => setConn((c) => ({ ...c, [key]: e.target.value }))} />
                  </Field>
                );
              })}
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              {SECRETS.map(({ key, hint }) => {
                const s = data.connection[key] as SecretSetting;
                return (
                  <Field key={key} label={s.label} hint={<>{hint} <Badge tone={SOURCE[s.source].tone}>{SOURCE[s.source].label}</Badge></>}>
                    <div className="flex gap-2">
                      <TextInput type="password" autoComplete="new-password" value={conn[key] ?? ''} disabled={!editable}
                        placeholder={s.set ? `Set (${s.hint}). Type to replace` : 'Not set'}
                        onChange={(e) => setConn((c) => ({ ...c, [key]: e.target.value }))} />
                      {editable && key === 'verify_token' && (
                        <Btn size="sm" onClick={() => setConn((c) => ({ ...c, verify_token: randomToken() }))}>Generate</Btn>
                      )}
                      {editable && s.source === 'admin' && (
                        <Btn size="sm" onClick={() => put({ connection: { clear: [key] } }, `${s.label} cleared.`, `clear-${key}`)}
                          busy={busy === `clear-${key}`}>Clear</Btn>
                      )}
                    </div>
                  </Field>
                );
              })}
            </div>
            {conn.verify_token && (
              <p className="rounded-lg bg-muted/40 px-3 py-2 text-xs">
                New verify token: <code className="select-all font-mono">{conn.verify_token}</code>. Copy it into Meta’s webhook settings before saving.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              {editable && <Btn variant="primary" busy={busy === 'conn'} onClick={saveConnection}>Save connection</Btn>}
              <Btn busy={busy === 'test'} onClick={testConnection}>Test connection</Btn>
              {check && (check.ok
                ? <span className="text-sm text-win">✓ Meta knows this number: <b>{check.verified_name}</b> ({check.display_phone_number}{check.quality_rating ? `, quality ${check.quality_rating}` : ''})</span>
                : <span className="text-sm text-destructive">✗ {check.error}</span>)}
            </div>
            <div className="rounded-xl border border-border/70 p-3 text-sm">
              <p className="text-xs text-muted-foreground">Webhook callback URL (Meta → WhatsApp → Configuration; subscribe to “messages”)</p>
              <code className="select-all break-all font-mono">{webhook || '…/api/chatbot/whatsapp/webhook/'}</code>
            </div>
            {data.connection.updated_at && (
              <p className="text-xs text-muted-foreground">
                Last changed by {data.connection.updated_by} on {new Date(data.connection.updated_at).toLocaleString()}.
              </p>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Switches and limits">
        {form && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-6">
              {([['enabled', 'Bot on'], ['allow_betting', 'Betting'], ['allow_deposits', 'Deposits']] as const).map(([k, label]) => (
                <span key={k} className="flex items-center gap-2 text-sm font-semibold">
                  <Switch checked={form[k]} onChange={(v) => setForm({ ...form, [k]: v })} label={label} /> {label}
                </span>
              ))}
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
            <Btn variant="primary" busy={busy === 'limits'} onClick={saveLimits}>Save</Btn>
          </div>
        )}
      </Panel>

      <Panel title="Before going live">
        <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
          <li>In Meta Business, create an app with the <b className="text-foreground">WhatsApp</b> product and add a phone number. Use a number you can afford to lose, not your main support line.</li>
          <li>Create a system user with a permanent token that has <code>whatsapp_business_messaging</code>, then fill in the connection above and press <b className="text-foreground">Test connection</b>.</li>
          <li>Set the webhook callback URL and verify token in Meta, and subscribe to <b className="text-foreground">messages</b>.</li>
          <li>Meta’s policy restricts real-money gambling on WhatsApp without its written approval. Apply for it; until then the number can be banned if reported.</li>
        </ol>
      </Panel>
      </>)}
    </div>
  );
}
