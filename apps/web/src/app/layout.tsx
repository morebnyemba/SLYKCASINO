import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from '@/components/providers';
import { SiteHeader } from '@/components/site-header';
import { SiteFooter } from '@/components/site-footer';
import { BottomNav } from '@/components/bottom-nav';
import { AppSidebar, MobileMenu } from '@/components/app-sidebar';
import { BetslipDrawer } from '@/components/betslip-panel';
import { GlobalSearch } from '@/components/global-search';
import { MobileQuickNav } from '@/components/mobile-quick-nav';
import { AgeGate } from '@/components/age-gate';
import { ServiceWorkerRegistration } from '@/components/service-worker-registration';
import { fetchSiteThemeCss } from '@/lib/site-theme';
import { fetchSiteIdentity } from '@/lib/site-identity';
import { IdentityProvider } from '@/lib/identity-context';

export async function generateMetadata(): Promise<Metadata> {
  const identity = await fetchSiteIdentity();
  return {
    title: `${identity.site_name} — Player`,
    description: 'Real-time betting & livechat platform',
    manifest: '/manifest.json',
    appleWebApp: {
      capable: true,
      statusBarStyle: 'black-translucent',
      title: identity.site_name,
    },
    icons: {
      icon: '/icons/icon-192.png',
      apple: '/icons/apple-touch-icon.png',
    },
  };
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Lets the header pad itself below the notch (env(safe-area-inset-top)).
  viewportFit: 'cover',
  themeColor: '#110B2E',
};

// Applied before paint so switching themes never flashes the previous theme on load.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var raw = window.localStorage.getItem('slyk:settings');
    var s = raw ? JSON.parse(raw) : null;
    document.documentElement.dataset.theme = (s && s.theme) || 'dark';
    if (s && s.accent) {
      document.documentElement.style.setProperty('--secondary', s.accent);
      document.documentElement.style.setProperty('--ring', s.accent);
    }
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();
`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [themeCss, identity] = await Promise.all([fetchSiteThemeCss(), fetchSiteIdentity()]);
  return (
    // data-theme is set by THEME_INIT_SCRIPT before hydration.
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Operator-configured brand colors from the admin dashboard, layered
            over the static defaults in @slyk/ui/globals.css. */}
        {themeCss && <style id="site-theme" dangerouslySetInnerHTML={{ __html: themeCss }} />}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <IdentityProvider value={identity}>
          <ServiceWorkerRegistration />
          <AgeGate />
          <Providers>
            <div className="flex min-h-screen">
              <AppSidebar />
              <div className="flex min-w-0 flex-1 flex-col">
                <SiteHeader />
                <MobileQuickNav />
                <main className="mx-auto w-full max-w-[1440px] flex-1 px-3 py-4 sm:px-5 sm:py-6">{children}</main>
                <SiteFooter />
                {/* Keeps the footer clear of the fixed mobile tab bar. */}
                <div className="h-20 lg:hidden" />
              </div>
            </div>
            <MobileMenu />
            <GlobalSearch />
            <BetslipDrawer />
            <BottomNav />
          </Providers>
        </IdentityProvider>
      </body>
    </html>
  );
}
