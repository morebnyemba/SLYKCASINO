'use client';

import { useEffect, useState } from 'react';
import { BsCheckCircleFill, BsClipboard, BsLightningCharge, BsPlug, BsShieldCheck } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, TextInput, cx } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

type Provider = 'paynow' | 'stub';

interface Gateway {
  provider: Provider;
  provider_setting: '' | Provider;
  server_provider: string;
  paynow: {
    integration_id: string;
    key_hint: string;
    key_set: boolean;
    auth_email: string;
    configured: boolean;
    from_server: { integration_id: boolean; integration_key: boolean; auth_email: boolean };
    result_url: string;
    return_url: string;
  };
  updated_at: string | null;
  updated_by: string;
}

const OPTIONS: { id: Provider; title: string; text: string; icon: typeof BsShieldCheck }[] = [
  { id: 'paynow', title: 'Paynow', text: 'Real payments: EcoCash, OneMoney, InnBucks and cards, paid into your Paynow merchant account.', icon: BsShieldCheck },
  { id: 'stub', title: 'Test processor', text: 'Deposits credit instantly and no money moves. For demos and testing only.', icon: BsLightningCharge },
];

/** Where deposits are processed, and the Paynow credentials. */
export function GatewayPanel({ onChanged }: { onChanged: () => void }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Gateway>('/admin/payment-gateway/');
  const [provider, setProvider] = useState<Provider>('stub');
  const [integrationId, setIntegrationId] = useState('');
  const [key, setKey] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState<'save' | 'test' | null>(null);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!data) return;
    setProvider(data.provider);
    setIntegrationId(data.paynow.integration_id);
    setEmail(data.paynow.auth_email);
    setKey('');
  }, [data]);

  if (!data) return <Panel title="Payment gateway"><div className="h-40 animate-pulse rounded-xl bg-muted/50" /></Panel>;

  const pn = data.paynow;
  const dirty = provider !== data.provider || integrationId !== pn.integration_id || email !== pn.auth_email || key !== '';

  async function save() {
    if (!accessToken) return;
    const toTest = provider === 'stub' && data!.provider !== 'stub';
    if (toTest && !confirm('Switch to the test processor? Deposits will be credited WITHOUT taking any money. Only do this on a demo site.')) return;
    setBusy('save'); setNotice(null);
    const res = await authedRequest<Gateway>('PUT', '/admin/payment-gateway/', accessToken, {
      provider, paynow_integration_id: integrationId, paynow_auth_email: email,
      ...(key ? { paynow_integration_key: key } : {}), ...(toTest ? { confirm_test_mode: true } : {}),
    });
    setBusy(null);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: provider === 'paynow' ? 'Saved — deposits now go through Paynow.' : 'Saved.' });
    refetch(); onChanged();
  }

  async function test() {
    if (!accessToken) return;
    setBusy('test'); setNotice(null);
    const res = await authedRequest<{ ok: boolean; error?: string; paynow_reference?: string }>('POST', '/admin/payment-gateway/test/', accessToken);
    setBusy(null);
    if (res.error || !res.data) { setNotice({ tone: 'red', text: res.error ?? 'Test failed.' }); return; }
    setNotice(res.data.ok
      ? { tone: 'green', text: `Paynow accepted the credentials (test checkout ${res.data.paynow_reference || 'created'} — nothing is charged).` }
      : { tone: 'red', text: `Paynow said: ${res.data.error}` });
  }

  async function copyResultUrl() {
    try { await navigator.clipboard.writeText(pn.result_url); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
  }

  const fromServer = (on: boolean) => (on ? 'Currently taken from the server’s .env file — saving a value here overrides it.' : undefined);

  return (
    <Panel
      title="Payment gateway"
      description="Where player deposits are processed."
      actions={data.provider === 'paynow'
        ? <Badge tone="green" dot>Live: Paynow</Badge>
        : <Badge tone="gold" dot>Test processor — no real money</Badge>}
    >
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Gateway">
          {OPTIONS.map((o) => {
            const Icon = o.icon;
            const on = provider === o.id;
            return (
              <button
                key={o.id}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setProvider(o.id)}
                className={cx(
                  'flex items-start gap-3 rounded-2xl border p-4 text-left transition-colors',
                  on ? 'border-secondary bg-secondary/10 ring-1 ring-secondary/40' : 'border-border hover:border-secondary/50',
                )}
              >
                <span className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', on ? 'bg-secondary text-white' : 'bg-muted text-muted-foreground')}>
                  <Icon size={17} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-bold">
                    {o.title}
                    {data.provider === o.id && <BsCheckCircleFill size={12} className="text-win" aria-label="Active" />}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">{o.text}</span>
                </span>
              </button>
            );
          })}
        </div>

        <div className={cx('space-y-4 rounded-2xl border border-border/70 p-4', provider !== 'paynow' && 'opacity-70')}>
          <div className="flex items-center gap-2">
            <p className="text-sm font-bold">Paynow credentials</p>
            {pn.configured ? <Badge tone="green">Set</Badge> : <Badge tone="slate">Not set</Badge>}
          </div>
          <p className="-mt-2 text-xs text-muted-foreground">
            From paynow.co.zw → Receive Payments → your integration. The key is stored securely and never shown again.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Integration ID" hint={fromServer(pn.from_server.integration_id)}>
              <TextInput inputMode="numeric" value={integrationId} onChange={(e) => setIntegrationId(e.target.value.replace(/\D/g, ''))} placeholder="12345" />
            </Field>
            <Field label="Integration Key" hint={pn.key_set ? `Saved key ${pn.key_hint}. ${pn.from_server.integration_key ? 'From the server’s .env file. ' : ''}Paste a new one to replace it.` : undefined}>
              <TextInput type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={pn.key_set ? pn.key_hint : 'Paste the integration key'} />
            </Field>
            <Field label="Merchant email" hint={fromServer(pn.from_server.auth_email) ?? 'The email on your Paynow account — needed for EcoCash, OneMoney and InnBucks.'} className="sm:col-span-2">
              <TextInput type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="payments@betblits.com" />
            </Field>
          </div>
          <Field label="Result URL" hint="Paste this into the result URL setting of your Paynow integration so payments are confirmed even if the player closes the page.">
            <div className="flex gap-2">
              <TextInput readOnly value={pn.result_url} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
              <Btn type="button" icon={BsClipboard} onClick={copyResultUrl}>{copied ? 'Copied' : 'Copy'}</Btn>
            </div>
          </Field>
        </div>

        {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

        <div className="flex flex-wrap items-center justify-end gap-2">
          {data.updated_by && (
            <span className="mr-auto text-xs text-muted-foreground">
              Last changed by {data.updated_by}{data.updated_at ? ` · ${new Date(data.updated_at).toLocaleString()}` : ''}
            </span>
          )}
          <Btn icon={BsPlug} onClick={test} busy={busy === 'test'} disabled={!pn.configured || dirty}
            title={dirty ? 'Save first, then test' : undefined}>
            Test connection
          </Btn>
          <Btn variant="primary" onClick={save} busy={busy === 'save'} disabled={!dirty}>Save gateway</Btn>
        </div>
      </div>
    </Panel>
  );
}
