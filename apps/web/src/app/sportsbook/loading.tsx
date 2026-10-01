import { Bone, EventListSkeleton, LoadingPill } from '@/components/skeletons';

export default function SportsbookLoading() {
  return (
    <div className="space-y-5">
      <LoadingPill label="Loading matches" />
      <div className="flex gap-3 overflow-hidden">
        {Array.from({ length: 3 }, (_, i) => <Bone key={i} className="h-[190px] w-[280px] shrink-0 rounded-2xl sm:w-[300px]" />)}
      </div>
      <div className="flex gap-2 overflow-hidden">
        {Array.from({ length: 8 }, (_, i) => <Bone key={i} className="h-16 w-24 shrink-0 rounded-xl" />)}
      </div>
      <EventListSkeleton />
    </div>
  );
}
