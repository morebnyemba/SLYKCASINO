import { Bone, LoadingPill } from '@/components/skeletons';

export default function CasinoLoading() {
  return (
    <div className="space-y-5">
      <LoadingPill label="Loading games" />
      <div className="flex gap-2 overflow-hidden">
        {Array.from({ length: 7 }, (_, i) => <Bone key={i} className="h-10 w-28 shrink-0 rounded-full" />)}
      </div>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 18 }, (_, i) => <Bone key={i} className="aspect-[3/4] rounded-xl" />)}
      </div>
    </div>
  );
}
