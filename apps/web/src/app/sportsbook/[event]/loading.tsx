import { Bone, LoadingPill } from '@/components/skeletons';

export default function MatchLoading() {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Bone className="h-4 w-24" />
      <div className="flex h-[188px] items-center justify-between rounded-2xl bg-gradient-to-br from-primary/60 to-muted/40 px-8">
        <Bone className="h-14 w-14 rounded-full bg-white/10" />
        <Bone className="h-9 w-24 bg-white/10" />
        <Bone className="h-14 w-14 rounded-full bg-white/10" />
      </div>
      <LoadingPill label="Loading markets" />
      <Bone className="h-12 rounded-2xl" />
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <Bone className="h-4 w-40" />
          <div className="grid grid-cols-3 gap-2"><Bone className="h-12" /><Bone className="h-12" /><Bone className="h-12" /></div>
        </div>
      ))}
    </div>
  );
}
