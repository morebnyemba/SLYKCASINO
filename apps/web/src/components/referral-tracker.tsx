'use client';

import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { captureReferral } from '@/lib/referral';

/** Picks up `?ref=` on any page an affiliate link lands on. */
export function ReferralTracker() {
  const pathname = usePathname();
  useEffect(() => { captureReferral(); }, [pathname]);
  return null;
}
