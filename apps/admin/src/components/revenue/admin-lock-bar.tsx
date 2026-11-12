'use client';

import Link from 'next/link';
import { BsLockFill } from 'react-icons/bs';
import { usePolling } from '@slyk/ui/components/analytics';
import { useApi } from '@/lib/use-api';

/** On every admin page: when two weekly pool audits in a row are missed the
 *  whole admin is read-only (every change is refused) until they're approved. */
export function AdminLockBar() {
  const { data, refetch } = useApi<{ locked: boolean; message: string }>('/admin/lock-status/');
  usePolling(refetch, 60000, [refetch]);
  if (!data?.locked) return null;
  return (
    <div role="alert" className="sticky top-0 z-40 flex flex-wrap items-center gap-3 bg-live px-4 py-2.5 text-sm font-semibold text-white">
      <BsLockFill />
      <span className="min-w-0 flex-1">{data.message}</span>
      <Link href="/revenue-share" className="rounded-lg bg-white/15 px-3 py-1 text-xs font-bold hover:bg-white/25">Open the audit</Link>
    </div>
  );
}
