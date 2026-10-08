'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { LoadingState } from '@slyk/ui/components/spinner';

/** Events moved to Sportsbook → Matches. */
export default function EventsRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace('/sportsbook/matches'); }, [router]);
  return <LoadingState className="py-24" />;
}
