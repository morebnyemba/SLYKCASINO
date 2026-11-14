import { PageSkeleton } from '@/components/skeletons';

/** Shown instantly while a page without its own loading screen renders. */
export default function Loading() {
  return <PageSkeleton />;
}
