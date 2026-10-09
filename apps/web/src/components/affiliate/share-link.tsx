'use client';

import { useState } from 'react';
import { FaCheck, FaCopy, FaFacebookF, FaShareNodes, FaTelegram, FaWhatsapp, FaXTwitter } from 'react-icons/fa6';

/** The affiliate's referral link: campaign tag, copy, and one-tap sharing. */
export function ShareLink({ code, welcome }: { code: string; welcome?: string }) {
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const [campaign, setCampaign] = useState('');
  const [copied, setCopied] = useState<'link' | 'code' | null>(null);
  const link = `${origin}/?ref=${code}${campaign ? `&campaign=${encodeURIComponent(campaign)}` : ''}`;
  const pitch = welcome
    ? `Join me on BetBlits — sign up with my link and get a ${welcome} bonus on your first deposit:`
    : 'Join me on BetBlits:';
  const enc = encodeURIComponent;

  async function copy(what: 'link' | 'code') {
    try { await navigator.clipboard.writeText(what === 'link' ? link : code); setCopied(what); setTimeout(() => setCopied(null), 1500); } catch { /* no clipboard */ }
  }
  async function nativeShare() {
    try { await navigator.share({ title: 'BetBlits', text: pitch, url: link }); } catch { /* cancelled */ }
  }

  const shares = [
    { label: 'WhatsApp', icon: <FaWhatsapp />, href: `https://wa.me/?text=${enc(`${pitch} ${link}`)}`, cls: 'bg-[#25D366] text-white' },
    { label: 'Facebook', icon: <FaFacebookF />, href: `https://www.facebook.com/sharer/sharer.php?u=${enc(link)}`, cls: 'bg-[#1877F2] text-white' },
    { label: 'Telegram', icon: <FaTelegram />, href: `https://t.me/share/url?url=${enc(link)}&text=${enc(pitch)}`, cls: 'bg-[#229ED9] text-white' },
    { label: 'X', icon: <FaXTwitter />, href: `https://twitter.com/intent/tweet?text=${enc(pitch)}&url=${enc(link)}`, cls: 'bg-black text-white' },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <code className="min-w-0 flex-1 truncate rounded-lg border border-border bg-input px-3 py-2.5 text-sm">{link}</code>
        <button onClick={() => copy('link')} className="flex items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-2.5 text-sm font-bold text-white">
          {copied === 'link' ? <FaCheck size={12} /> : <FaCopy size={12} />} {copied === 'link' ? 'Copied' : 'Copy link'}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {shares.map((s) => (
          <a key={s.label} href={s.href} target="_blank" rel="noopener noreferrer" aria-label={`Share on ${s.label}`}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold transition-opacity hover:opacity-90 ${s.cls}`}>
            {s.icon}{s.label}
          </a>
        ))}
        {typeof navigator !== 'undefined' && 'share' in navigator && (
          <button onClick={nativeShare} className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-bold">
            <FaShareNodes /> More
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Or share your code <button onClick={() => copy('code')} className="rounded-md bg-muted px-1.5 py-0.5 font-mono font-bold text-foreground">{copied === 'code' ? 'copied!' : code}</button> — players enter it at sign-up.</span>
        <input
          value={campaign}
          onChange={(e) => setCampaign(e.target.value.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 50))}
          placeholder="campaign tag (optional)"
          aria-label="Campaign tag"
          className="ml-auto rounded-md border border-border bg-input px-2 py-1 text-xs outline-none"
        />
      </div>
    </div>
  );
}
