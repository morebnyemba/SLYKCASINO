'use client';

import { Suspense } from 'react';
import { usePathname } from 'next/navigation';
import { SiteHeader } from '@/components/site-header';
import { SiteFooter } from '@/components/site-footer';
import { BottomNav } from '@/components/bottom-nav';
import { AppSidebar, MobileMenu } from '@/components/app-sidebar';
import { BetslipDrawer } from '@/components/betslip-panel';
import { ReferralTracker } from '@/components/referral-tracker';
import { NavigationLoader } from '@/components/site-loader';
import { BetRail } from '@/components/bet-rail';
import { GlobalSearch } from '@/components/global-search';
import { MobileQuickNav } from '@/components/mobile-quick-nav';

/** Games embedded in an iframe (/play/...) render bare: no site navigation around them. */
export function isGameFrameRoute(pathname: string | null) {
  return !!pathname && pathname.startsWith('/play/');
}

/** The site chrome — sidebar, header, footer, rails and mobile bars — around every page except embedded games. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (isGameFrameRoute(pathname)) {
    return <main className="min-h-dvh">{children}</main>;
  }
  return (
    <>
      <div className="flex min-h-screen">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <SiteHeader />
          <MobileQuickNav />
          {/* Desktop: content column + bet-slip rail, both under the header. */}
          <div className="flex min-w-0 flex-1">
            <div className="flex min-w-0 flex-1 flex-col">
              <main className="mx-auto w-full max-w-[1600px] flex-1 px-3 py-4 sm:px-5 sm:py-6 xl:px-6">{children}</main>
              <SiteFooter />
              {/* Keeps the footer clear of the fixed mobile tab bar. */}
              <div className="h-20 lg:hidden" />
            </div>
            <BetRail />
          </div>
        </div>
      </div>
      <MobileMenu />
      <GlobalSearch />
      <BetslipDrawer />
      <ReferralTracker />
      {/* useSearchParams needs a Suspense boundary. */}
      <Suspense><NavigationLoader /></Suspense>
      <BottomNav />
    </>
  );
}
