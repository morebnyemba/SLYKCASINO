import { LoadingState } from '@slyk/ui/components/spinner';

/** Shown instantly while any page without its own loading screen renders. */
export default function Loading() {
  return <LoadingState className="min-h-[50vh]" size={36} />;
}
