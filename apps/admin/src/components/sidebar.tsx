import Link from 'next/link';

// hrefs omit the /admin-portal prefix — Next.js basePath prepends it and Nginx
// routes /admin-portal to this app.
const nav = [
  { href: '/', label: 'Overview' },
  { href: '/livechat', label: 'Live Chat Console' },
  { href: '/betting-feeds', label: 'Betting Feeds' },
  { href: '/promotions', label: 'Promotions' },
  { href: '/users', label: 'Players' },
];

export function Sidebar() {
  return (
    <aside className="flex min-h-screen w-56 flex-col gap-6 border-r border-border bg-card p-5">
      <div className="text-base font-bold">🛡️ SLYK Admin</div>
      <nav className="flex flex-col gap-2 text-sm">
        {nav.map((n) => (
          <Link key={n.href} href={n.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto text-xs text-muted-foreground">
        Raw DB intervention →{' '}
        <a href="/django-admin/" className="text-primary underline-offset-4 hover:underline">Django Admin</a>
      </div>
    </aside>
  );
}
