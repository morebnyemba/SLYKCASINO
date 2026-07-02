import type { Metadata } from 'next';
import './globals.css';
import { Providers } from '@/components/providers';
import { fetchSiteIdentity } from '@/lib/site-identity';
import { IdentityProvider } from '@/lib/identity-context';

export async function generateMetadata(): Promise<Metadata> {
  const identity = await fetchSiteIdentity();
  return {
    title: `${identity.site_name} — Admin`,
    description: 'Operator command center: livechat, promotions, live betting feeds',
  };
}

// Applied before paint so switching themes never flashes the previous theme on load.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem('slyk-admin:theme');
    document.documentElement.dataset.theme = (stored === 'light' || stored === 'dark') ? stored : 'dark';
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();
`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const identity = await fetchSiteIdentity();
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <IdentityProvider value={identity}>
          <Providers>{children}</Providers>
        </IdentityProvider>
      </body>
    </html>
  );
}
