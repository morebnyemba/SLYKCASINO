import Link from 'next/link';

const legalLinks = [
  { href: '/legal/terms', label: 'Terms & Conditions' },
  { href: '/legal/privacy-policy', label: 'Privacy Policy' },
  { href: '/legal/cookie-policy', label: 'Cookie Policy' },
  { href: '/legal/responsible-gambling', label: 'Responsible Gambling' },
  { href: '/legal/aml-kyc-policy', label: 'AML & KYC Policy' },
];

export function SiteFooter() {
  return (
    <footer className="mt-12 border-t border-border bg-primary/5 px-6 py-8 text-sm">
      <div className="mx-auto flex max-w-6xl flex-col gap-4">
        <nav className="flex flex-wrap gap-4">
          {legalLinks.map((l) => (
            <Link key={l.href} href={l.href} className="text-muted-foreground hover:text-foreground hover:underline">
              {l.label}
            </Link>
          ))}
        </nav>
        <p className="text-muted-foreground">
          SLYK Casino is intended for players aged 18 and over. Gambling can be addictive — please play
          responsibly. See our <Link href="/legal/responsible-gambling" className="underline">Responsible Gambling</Link> page for tools and support.
        </p>
        <p className="text-xs text-muted-foreground/70">
          &copy; {new Date().getFullYear()} [COMPANY LEGAL NAME]. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
