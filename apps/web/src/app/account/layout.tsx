import Link from 'next/link';

const tabs = [
  { href: '/account/profile', label: 'Profile' },
  { href: '/account/wallet', label: 'Wallet' },
  { href: '/account/bets', label: 'My Bets' },
];

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid gap-6 md:grid-cols-[180px_1fr]">
      <nav className="flex flex-col gap-2 text-sm">
        {tabs.map((t) => (
          <Link key={t.href} href={t.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {t.label}
          </Link>
        ))}
      </nav>
      <section>{children}</section>
    </div>
  );
}
