import { Spinner } from '@slyk/ui/components/spinner';

/** Building blocks for route loading screens (shown while a server page renders). */
export function Bone({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-muted ${className}`} />;
}

/** Small "Loading…" pill so a skeleton reads as in-progress, not empty. */
export function LoadingPill({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex justify-center">
      <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground shadow-sm">
        <Spinner size={13} className="text-secondary" label={label} /> {label}…
      </span>
    </div>
  );
}

/** A market list: header plus rows of teams and three price boxes. */
export function EventListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Bone className="h-4 w-4 rounded-full" />
        <Bone className="h-4 w-28" />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
          <Bone className="hidden h-8 w-12 md:block" />
          <div className="flex-1 space-y-2">
            <Bone className="h-3.5 w-2/5" />
            <Bone className="h-3.5 w-1/3" />
          </div>
          <div className="grid w-[178px] grid-cols-3 gap-1.5 sm:w-[222px]">
            <Bone className="h-11" /><Bone className="h-11" /><Bone className="h-11" />
          </div>
        </div>
      ))}
    </div>
  );
}
