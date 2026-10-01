import { LoadingState } from '@slyk/ui/components/spinner';

export default function GameLoading() {
  return <LoadingState className="min-h-[60vh]" size={36} label="Loading game" />;
}
