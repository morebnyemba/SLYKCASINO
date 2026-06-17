import Link from 'next/link';

const legalLinks = [
  { href: '/legal/terms', label: 'Terms & Conditions' },
  { href: '/legal/privacy-policy', label: 'Privacy Policy' },
  { href: '/legal/cookie-policy', label: 'Cookie Policy' },
  { href: '/legal/responsible-gambling', label: 'Responsible Gambling' },
  { href: '/legal/aml-kyc-policy', label: 'AML & KYC Policy' },
];

export function LegalLayout({
  title,
  effectiveDate,
  children,
}: {
  title: string;
  effectiveDate: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-8 lg:flex-row">
      <aside className="lg:w-56 shrink-0">
        <nav className="flex flex-col gap-1 text-sm lg:sticky lg:top-6">
          {legalLinks.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="min-w-0 flex-1 max-w-3xl">
        <header className="mb-6 border-b border-border pb-4">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">Effective date: {effectiveDate}</p>
        </header>
        <div className="legal-prose flex flex-col gap-4 text-sm leading-relaxed text-foreground/90">
          {children}
        </div>
      </article>
    </div>
  );
}
