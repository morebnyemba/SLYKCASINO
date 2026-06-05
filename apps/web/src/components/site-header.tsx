import Link from 'next/link';

const links = [
  { href: '/', label: 'Lobby' },
  { href: '/sportsbook', label: 'Sportsbook' },
  { href: '/livechat', label: 'Live Chat' },
  { href: '/account/wallet', label: 'Wallet' },
  { href: '/account/bets', label: 'My Bets' },
];

export function SiteHeader() {
  return (
    <header className="flex items-center gap-6 border-b border-border bg-card px-6 py-3">
      <Link href="/" className="text-lg font-bold">🎰 SLYK</Link>
      <nav className="flex flex-1 gap-4 text-sm">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {l.label}
          </Link>
        ))}
      </nav>
      <Link href="/account/profile" className="text-sm font-medium">Account</Link>
    </header>
  );
}
