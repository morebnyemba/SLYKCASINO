'use client';

import { FaBolt, FaGift, FaLock } from 'react-icons/fa';
import { useSiteIdentity } from '@/lib/identity-context';

const PERKS = [
  { icon: FaGift, text: '200% welcome bonus up to $1,000' },
  { icon: FaBolt, text: 'Instant EcoCash & card payouts' },
  { icon: FaLock, text: 'Secure, licensed & encrypted' },
];

export const authInputClass =
  'w-full rounded-xl border border-border bg-input px-3.5 py-3 text-sm outline-none transition-shadow focus:ring-2 focus:ring-ring';
export const authButtonClass =
  'w-full rounded-xl bg-win px-4 py-3 text-sm font-extrabold text-win-foreground shadow-lg transition-opacity hover:opacity-90 disabled:opacity-50';

/** Two-panel sign-in/sign-up layout: brand promo on the left, form on the right. */
export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const identity = useSiteIdentity();
  return (
    <div className="flex min-h-[70vh] items-center justify-center py-4">
      <div className="grid w-full max-w-3xl overflow-hidden rounded-3xl border border-border bg-card shadow-2xl md:grid-cols-2">
        <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-secondary via-primary to-[#0f0a2b] p-8 text-white md:flex">
          <div className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-white/10 blur-2xl" />
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-white/60">{identity.site_name}</p>
            <p className="mt-3 text-3xl font-black leading-tight">{identity.tagline || 'Bet smart. Brag often.'}</p>
          </div>
          <ul className="space-y-3 text-sm font-semibold">
            {PERKS.map((p) => {
              const Icon = p.icon;
              return (
                <li key={p.text} className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15"><Icon size={13} /></span>
                  {p.text}
                </li>
              );
            })}
          </ul>
          <p className="text-[11px] text-white/50">18+ · Play responsibly</p>
        </div>
        <div className="p-6 sm:p-8">
          <h1 className="text-2xl font-black">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
