import Link from 'next/link';
import { FaShieldAlt, FaLock, FaBolt } from 'react-icons/fa';

const TRUST = [
  { label: 'Licensed & regulated', icon: FaShieldAlt },
  { label: 'Secure encrypted wallet', icon: FaLock },
  { label: 'Fast local payouts', icon: FaBolt },
];

const PAYMENTS = ['EcoCash', 'OneMoney', 'Visa', 'Mastercard', 'USDT', 'Innbucks'];

export function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-border bg-card">
      <div className="mx-auto max-w-6xl px-6 py-8 text-sm text-muted-foreground">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-border pb-6">
          {TRUST.map((t) => {
            const Icon = t.icon;
            return (
              <span key={t.label} className="flex items-center gap-2">
                <Icon size={14} className="text-primary" />
                {t.label}
              </span>
            );
          })}
        </div>

        <div className="grid gap-6 pt-6 sm:grid-cols-3">
          <div className="space-y-2">
            <p className="font-semibold text-foreground">SLÝKBETS</p>
            <p className="text-xs leading-relaxed">
              Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe.
              <br />
              Licence No. LGB/SLYKBETS/2026 (demo).
            </p>
            <div className="flex items-center gap-2 pt-1">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-secondary text-xs font-bold text-secondary">
                18+
              </span>
              <span className="text-xs">No persons under 18 permitted.</span>
            </div>
          </div>

          <div className="space-y-2">
            <p className="font-semibold text-foreground">Play responsibly</p>
            <p className="text-xs leading-relaxed">
              Gambling can be addictive. Set deposit limits, take breaks, and never bet more than you can
              afford to lose.
            </p>
            <Link href="/account/settings" className="text-xs text-primary underline-offset-2 hover:underline">
              Responsible gambling controls →
            </Link>
          </div>

          <div className="space-y-2">
            <p className="font-semibold text-foreground">Help &amp; info</p>
            <ul className="space-y-1 text-xs">
              <li><Link href="/promotions" className="hover:text-foreground">Promotions &amp; bonuses</Link></li>
              <li><Link href="/tournaments" className="hover:text-foreground">Tournaments</Link></li>
              <li><Link href="/livechat" className="hover:text-foreground">Live support</Link></li>
              <li><Link href="/casino" className="hover:text-foreground">Game fairness &amp; RTP</Link></li>
            </ul>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-6">
          <span className="text-xs font-semibold text-foreground">Payments</span>
          {PAYMENTS.map((p) => (
            <span key={p} className="rounded-md bg-chip px-2 py-1 text-xs text-muted-foreground">
              {p}
            </span>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6 text-xs text-muted-foreground/70">
          <p>© {new Date().getFullYear()} SLÝKBETS. All rights reserved. Bet with your head, not over it.</p>
          <div className="flex items-center gap-4">
            <Link href="/legal/terms" className="hover:text-foreground">Terms</Link>
            <Link href="/legal/privacy" className="hover:text-foreground">Privacy</Link>
            <Link href="/legal/cookies" className="hover:text-foreground">Cookies</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
