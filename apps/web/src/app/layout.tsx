import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Providers } from '@/components/providers';
import { SiteHeader } from '@/components/site-header';
import { SiteFooter } from '@/components/site-footer';
import { BottomNav } from '@/components/bottom-nav';
import { AgeGate } from '@/components/age-gate';
import { ServiceWorkerRegistration } from '@/components/service-worker-registration';

export const metadata: Metadata = {
  title: 'SLÝKBETS — Player',
  description: 'Real-time betting & livechat platform',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'SLÝKBETS',
  },
  icons: {
    icon: '/icons/icon-192.png',
    apple: '/icons/apple-touch-icon.png',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#4ab8e8',
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <ServiceWorkerRegistration />
        <AgeGate />
        <Providers>
          <div className="flex min-h-screen flex-col">
            <SiteHeader />
            <main className="mx-auto w-full max-w-6xl flex-1 p-6 pb-24 lg:pb-6">{children}</main>
            <SiteFooter />
            <div className="h-20 lg:hidden" />
            <BottomNav />
          </div>
        </Providers>
      </body>
    </html>
  );
}
