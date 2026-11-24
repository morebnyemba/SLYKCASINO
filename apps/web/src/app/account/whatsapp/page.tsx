'use client';

import { useState } from 'react';
import { FaWhatsapp } from 'react-icons/fa';
import { FaCheck, FaCopy, FaLock } from 'react-icons/fa6';
import { Card, CardContent } from '@slyk/ui/components/card';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { authedDelete, authedPost, useApi } from '@/lib/use-api';

interface ChatStatus {
  enabled: boolean;
  bot_number: string;
  linked: boolean;
  number: string | null;
  linked_at: string | null;
  has_pin: boolean;
  daily_limit: string | null;
  operator_daily_limit: string;
  max_stake: string;
  pin_above: string;
  require_login?: boolean; session_minutes?: number;
  staked_today: string;
}

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;

const COMMANDS: [string, string][] = [
  ['GAMES', 'upcoming matches with their IDs'],
  ['LIVE', 'matches in play now'],
  ['1234', 'open a match and tap a pick'],
  ['1234 1', 'or type the match ID and pick (X 2 1X 12 X2 GG NG O2.5 U2.5)'],
  ['SLIP', 'see your ticket'],
  ['Place bet → Confirm', 'choose a stake, check the ticket, press Confirm'],
  ['BALANCE · TICKETS', 'your money and latest tickets'],
  ['DEPOSIT 10', 'EcoCash prompt to your phone'],
  ['STOP', 'unlink the number'],
];

export default function WhatsAppBettingPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<ChatStatus>('/chatbot/me/');
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [pin, setPin] = useState('');
  const [limit, setLimit] = useState('');
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  async function run(key: string, fn: () => Promise<{ error?: string }>, ok: string) {
    if (!accessToken) return;
    setBusy(key); setNote(null);
    const res = await fn();
    setBusy('');
    setNote(res.error ? { ok: false, text: res.error } : { ok: true, text: ok });
    if (!res.error) refetch();
  }

  async function getCode() {
    if (!accessToken) return;
    setBusy('code'); setNote(null);
    const res = await authedPost<{ code: string; expires_at: string }>('/chatbot/me/link-code/', {}, accessToken);
    setBusy('');
    if (res.data) setCode(res.data);
    else setNote({ ok: false, text: res.error ?? 'Could not get a code.' });
  }

  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* no clipboard */ }
  }

  const waLink = (text: string) =>
    data?.bot_number ? `https://wa.me/${data.bot_number.replace(/\D/g, '')}?text=${encodeURIComponent(text)}` : null;

  if (loading && !data) return <LoadingState />;
  if (!data) return <p className="text-sm text-destructive">Couldn’t load this page. Please try again.</p>;

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><FaWhatsapp className="text-[#25D366]" /> WhatsApp betting</h1>

      {!data.enabled && (
        <p className="rounded-xl border border-gold/40 bg-gold/10 px-4 py-3 text-sm">Betting through WhatsApp is paused right now.</p>
      )}

      {!data.linked ? (
        <Card className="rounded-2xl">
          <CardContent className="space-y-4 pt-5">
            <p className="text-sm text-muted-foreground">
              Browse matches by their ID, build a slip and bet from WhatsApp. Link your number once:
            </p>
            <ol className="space-y-2 text-sm">
              <li><b>1.</b> Get a one-time code below (it works for 10 minutes).</li>
              <li><b>2.</b> Send it to our WhatsApp number{data.bot_number && <> <b>{data.bot_number}</b></>} as <code className="rounded bg-muted px-1.5 py-0.5 font-mono">LINK 123456</code>.</li>
            </ol>
            {code ? (
              <div className="space-y-3 rounded-xl border border-border p-4">
                <p className="text-xs text-muted-foreground">Send this to the bot</p>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-2xl font-extrabold tracking-widest">LINK {code.code}</span>
                  <button onClick={() => copy(`LINK ${code.code}`)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-bold">
                    {copied ? <FaCheck size={11} className="text-win" /> : <FaCopy size={11} />} {copied ? 'Copied' : 'Copy'}
                  </button>
                  {waLink(`LINK ${code.code}`) && (
                    <a href={waLink(`LINK ${code.code}`)!} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-lg bg-[#25D366] px-3 py-1.5 text-sm font-bold text-white">
                      <FaWhatsapp /> Open WhatsApp
                    </a>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Expires at {new Date(code.expires_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}.
                  Then <button onClick={refetch} className="font-bold underline">refresh</button> this page.
                </p>
              </div>
            ) : (
              <button onClick={getCode} disabled={busy === 'code'}
                className="inline-flex items-center gap-2 rounded-lg bg-[#25D366] px-5 py-2.5 text-sm font-extrabold text-white disabled:opacity-60">
                {busy === 'code' ? <Spinner size={14} /> : <FaWhatsapp />} Get my link code
              </button>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card className="rounded-2xl">
          <CardContent className="space-y-4 pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm text-muted-foreground">Linked number</p>
                <p className="text-lg font-extrabold">{data.number}</p>
                {data.linked_at && <p className="text-xs text-muted-foreground">since {new Date(data.linked_at).toLocaleDateString()}</p>}
              </div>
              <button onClick={() => run('unlink', () => authedDelete('/chatbot/me/', accessToken!), 'Unlinked.')}
                disabled={busy === 'unlink'} className="rounded-lg border border-destructive/40 px-4 py-2 text-sm font-bold text-destructive">
                Unlink
              </button>
            </div>
            <div className="grid gap-3 border-t border-border pt-4 text-sm sm:grid-cols-3">
              <div><p className="text-xs text-muted-foreground">Staked through chat today</p><p className="font-extrabold">{money(data.staked_today)}</p></div>
              <div><p className="text-xs text-muted-foreground">Daily chat limit</p><p className="font-extrabold">{money(data.daily_limit ?? data.operator_daily_limit)}</p></div>
              <div><p className="text-xs text-muted-foreground">Most per ticket</p><p className="font-extrabold">{money(data.max_stake)}</p></div>
            </div>
          </CardContent>
        </Card>
      )}

      {data.linked && (
        <Card className="rounded-2xl">
          <CardContent className="space-y-5 pt-5">
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-sm font-bold"><FaLock size={12} /> Chat PIN {data.has_pin && <span className="text-xs font-semibold text-win">set</span>}</p>
              <p className="text-xs text-muted-foreground">
                {data.require_login
                  ? (data.has_pin
                    ? `You log in on WhatsApp with this PIN (send LOGIN 1234). You are logged out after ${data.session_minutes ?? 5} minutes without a message.`
                    : 'You need a PIN to log in on WhatsApp (send LOGIN and your PIN). Set one now.')
                  : data.has_pin
                    ? 'Every bet from WhatsApp needs your PIN (reply YES 1234).'
                    : `Bets above ${money(data.pin_above)} need a PIN. Set one to protect your account if someone else uses your phone.`}
              </p>
              <div className="flex flex-wrap gap-2">
                <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric"
                  placeholder="4–6 digits" type="password" aria-label="New chat PIN"
                  className="w-40 rounded-lg border border-border bg-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring" />
                <button onClick={() => run('pin', () => authedPost('/chatbot/me/pin/', { pin }, accessToken!), 'PIN saved.').then(() => setPin(''))}
                  disabled={pin.length < 4 || busy === 'pin'} className="rounded-lg bg-secondary px-4 py-2 text-sm font-bold text-secondary-foreground disabled:opacity-50">
                  {data.has_pin ? 'Change PIN' : 'Set PIN'}
                </button>
                {data.has_pin && !data.require_login && (
                  <button onClick={() => run('nopin', () => authedDelete('/chatbot/me/pin/', accessToken!), 'PIN removed.')}
                    className="rounded-lg border border-border px-4 py-2 text-sm font-bold">Remove</button>
                )}
              </div>
            </div>
            <div className="space-y-2 border-t border-border pt-4">
              <p className="text-sm font-bold">My daily chat limit</p>
              <p className="text-xs text-muted-foreground">Lower than {money(data.operator_daily_limit)} if you want. Leave blank for the standard limit.</p>
              <div className="flex flex-wrap gap-2">
                <input value={limit} onChange={(e) => setLimit(e.target.value.replace(/[^\d.]/g, ''))} inputMode="decimal"
                  placeholder={data.daily_limit ?? data.operator_daily_limit} aria-label="Daily chat limit"
                  className="w-40 rounded-lg border border-border bg-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring" />
                <button onClick={() => run('limit', () => authedPost('/chatbot/me/limit/', { daily_limit: limit }, accessToken!), 'Limit saved.').then(() => setLimit(''))}
                  disabled={busy === 'limit'} className="rounded-lg bg-secondary px-4 py-2 text-sm font-bold text-secondary-foreground disabled:opacity-50">
                  Save limit
                </button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {note && <p className={`text-sm font-semibold ${note.ok ? 'text-win' : 'text-destructive'}`}>{note.text}</p>}

      <Card className="rounded-2xl">
        <CardContent className="pt-5">
          <p className="mb-3 text-sm font-bold">What you can send</p>
          <dl className="divide-y divide-border text-sm">
            {COMMANDS.map(([cmd, what]) => (
              <div key={cmd} className="flex items-center justify-between gap-3 py-2">
                <dt className="shrink-0 font-mono font-bold">{cmd}</dt>
                <dd className="text-right text-muted-foreground">{what}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">
            Each selection is confirmed back to you, and nothing is placed until you press Confirm on the ticket, at the current price and with the same rules as the website.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
