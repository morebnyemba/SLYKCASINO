import { PageLoader } from '@/components/site-loader';

/** Shown instantly while any page without its own loading screen renders. */
export default function Loading() {
  return <PageLoader />;
}
