'use client';

import { useState } from 'react';
import { BsCheck2, BsClipboard, BsShare, BsWhatsapp } from 'react-icons/bs';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { useBetslip } from '@/lib/betslip-context';
import { bookingLink, createBooking } from '@/lib/booking';

/** "Have a code?" field: replaces the slip with a booked one. */
export function LoadCodeForm({ className = '' }: { className?: string }) {
  const { loadCode } = useBetslip();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    const { ok, message: text } = await loadCode(code);
    setBusy(false);
    setMessage({ ok, text });
    if (ok) setCode('');
  }

  return (
    <form onSubmit={submit} className={className}>
      <label htmlFor="booking-code" className="mb-1.5 block text-left text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        Have a booking code?
      </label>
      <div className="flex gap-1.5">
        <input
          id="booking-code"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="e.g. 7K2QXB"
          autoComplete="off"
          spellCheck={false}
          maxLength={12}
          className="min-w-0 flex-1 rounded-lg border border-border bg-input px-3 py-2 text-sm font-extrabold uppercase tracking-[0.15em] outline-none placeholder:font-semibold placeholder:tracking-normal focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={busy || !code.trim()}
          className="flex min-w-[64px] items-center justify-center rounded-lg bg-secondary px-3 text-xs font-extrabold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {busy ? <Spinner size={13} /> : 'Load'}
        </button>
      </div>
      {message && (
        <p className={`mt-1.5 text-left text-[11.5px] font-semibold ${message.ok ? 'text-win' : 'text-destructive'}`}>{message.text}</p>
      )}
    </form>
  );
}

/** Book the current slip and show its code with copy / WhatsApp share. */
export function ShareSlip() {
  const { legs } = useBetslip();
  const { accessToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [bookedFor, setBookedFor] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // A code belongs to the picks it was booked for; changing the slip retires it.
  const signature = legs.map((l) => (l.outcomeId != null ? `o${l.outcomeId}` : `${l.eventId}${l.selection}`)).join(',');
  const current = code && bookedFor === signature ? code : null;

  async function book() {
    setBusy(true); setError(null);
    const res = await createBooking(legs, accessToken);
    setBusy(false);
    if (res.code) { setCode(res.code); setBookedFor(signature); } else setError(res.error ?? 'Could not book this slip.');
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked: the code is on screen */ }
  }

  if (!current) {
    return (
      <div>
        <button
          onClick={book}
          disabled={busy || legs.length === 0}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-card py-2 text-xs font-bold text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
        >
          {busy ? <Spinner size={12} /> : <BsShare size={11} />} Share slip · get booking code
        </button>
        {error && <p className="mt-1 text-[11.5px] font-semibold text-destructive">{error}</p>}
      </div>
    );
  }

  const link = bookingLink(current);
  const whatsapp = `https://wa.me/?text=${encodeURIComponent(`My BetBlits slip — booking code ${current}\n${link}`)}`;
  return (
    <div className="flex items-center gap-2 rounded-lg border border-secondary/40 bg-secondary/10 px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Booking code</p>
        <p className="text-base font-black tracking-[0.2em]">{current}</p>
      </div>
      <button
        onClick={() => copy(link)}
        aria-label="Copy share link"
        className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
      >
        {copied ? <BsCheck2 size={15} className="text-win" /> : <BsClipboard size={14} />}
      </button>
      <a
        href={whatsapp}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Share on WhatsApp"
        className="rounded-md bg-[#25D366] p-2 text-white transition-opacity hover:opacity-90"
      >
        <BsWhatsapp size={14} />
      </a>
    </div>
  );
}
