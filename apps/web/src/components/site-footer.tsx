'use client';

import Link from 'next/link';
import { useState } from 'react';
import { FaShieldAlt, FaLock, FaBolt, FaChevronDown } from 'react-icons/fa';
import { useSiteIdentity } from '@/lib/identity-context';

const TRUST = [
  { label: 'Licensed & regulated', icon: FaShieldAlt },
  { label: 'Secure encrypted wallet', icon: FaLock },
  { label: 'Fast local payouts', icon: FaBolt },
];

const PAYMENTS = ['EcoCash', 'OneMoney', 'Visa', 'Mastercard', 'USDT', 'Innbucks'];

/** Footer column: an accordion on phones, always open from `sm` up. */
function FooterSection({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-border sm:border-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between py-3.5 text-left font-bold text-foreground sm:pointer-events-none sm:py-0 sm:pb-2"
      >
        {title}
        <FaChevronDown size={11} className={`text-muted-foreground transition-transform sm:hidden ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className={`${open ? 'block' : 'hidden'} space-y-2 pb-4 sm:block sm:pb-0`}>{children}</div>
    </div>
  );
}

export function SiteFooter() {
  const identity = useSiteIdentity();
  return (
    <footer className="mt-10 border-t border-border bg-sidebar sm:mt-12">
      <div className="mx-auto max-w-[1440px] px-4 py-6 text-sm text-muted-foreground sm:px-5 sm:py-8">
        <div className="grid grid-cols-3 gap-2 border-b border-border pb-5 sm:flex sm:flex-wrap sm:items-center sm:gap-x-6 sm:gap-y-3 sm:pb-6">
          {TRUST.map((t) => {
            const Icon = t.icon;
            return (
              <span key={t.label} className="flex flex-col items-center gap-1.5 text-center text-[11px] font-semibold sm:flex-row sm:text-sm sm:font-normal">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-secondary/15 sm:h-auto sm:w-auto sm:bg-transparent">
                  <Icon size={14} className="text-secondary" />
                </span>
                {t.label}
              </span>
            );
          })}
        </div>

        <div className="grid sm:grid-cols-3 sm:gap-6 sm:pt-6">
          <FooterSection title={identity.site_name}>
            <p className="whitespace-pre-line text-xs leading-relaxed">{identity.license_text}</p>
          </FooterSection>

          <FooterSection title="Play responsibly">
            <p className="text-xs leading-relaxed">
              Gambling can be addictive. Set deposit limits, take breaks, and never bet more than you can
              afford to lose.
            </p>
            <Link href="/account/settings" className="text-xs font-semibold text-secondary underline-offset-2 hover:underline">
              Responsible gambling controls →
            </Link>
          </FooterSection>

          <FooterSection title="Help & info">
            <ul className="space-y-2 text-xs sm:space-y-1">
              <li><Link href="/promotions" className="hover:text-foreground">Promotions &amp; bonuses</Link></li>
              <li><Link href="/livechat" className="hover:text-foreground">Live support</Link></li>
            </ul>
          </FooterSection>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2 sm:mt-6 sm:border-t sm:border-border sm:pt-6">
          <span className="w-full text-xs font-semibold text-foreground sm:w-auto">Payments</span>
          {PAYMENTS.map((p) => (
            <span key={p} className="rounded-md bg-chip px-2 py-1 text-xs text-muted-foreground">
              {p}
            </span>
          ))}
        </div>

        <div className="mt-5 flex flex-col gap-3 border-t border-border pt-5 text-xs text-muted-foreground/70 sm:mt-6 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:pt-6">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-secondary text-[10px] font-bold text-secondary">
              18+
            </span>
            <p>© {new Date().getFullYear()} {identity.site_name}. Bet with your head, not over it.</p>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Link href="/legal/terms" className="hover:text-foreground">Terms</Link>
            <Link href="/legal/privacy" className="hover:text-foreground">Privacy</Link>
            <Link href="/legal/cookies" className="hover:text-foreground">Cookies</Link>
            <Link href="/legal/responsible-gambling" className="hover:text-foreground">Responsible gambling</Link>
            <Link href="/legal/aml-kyc-policy" className="hover:text-foreground">AML &amp; KYC</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
