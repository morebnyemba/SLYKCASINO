/**
 * Route loading screens shaped like the page that's coming, so the layout
 * appears instantly instead of a full-screen loader. Server components (no JS).
 */

const bar = 'animate-pulse rounded-lg bg-muted';

function MatchRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-3 py-3">
        <span className={`${bar} h-4 w-24`} />
        <span className="ml-auto flex w-[178px] gap-1.5 sm:w-[222px]">
          {[0, 1, 2].map((i) => <span key={i} className={`${bar} h-3 flex-1`} />)}
        </span>
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 border-b border-border px-3 py-3 last:border-b-0">
          <div className="min-w-0 flex-1 space-y-2">
            <span className={`${bar} block h-3 w-24`} />
            <span className={`${bar} block h-3.5 w-32`} />
            <span className={`${bar} block h-3.5 w-28`} />
          </div>
          <div className="grid w-[178px] grid-cols-3 gap-1.5 sm:w-[222px]">
            {[0, 1, 2].map((j) => <span key={j} className={`${bar} h-11`} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Sportsbook list: tabs, filters, then match rows. */
export function SportsbookSkeleton() {
  return (
    <div role="status" aria-label="Loading matches" className="space-y-3">
      <div className="grid grid-cols-4 gap-2">{[0, 1, 2, 3].map((i) => <span key={i} className={`${bar} h-11`} />)}</div>
      <div className="flex gap-2">{[0, 1, 2].map((i) => <span key={i} className={`${bar} h-11 flex-1`} />)}</div>
      <MatchRows rows={7} />
    </div>
  );
}

/** Match page: scoreboard, market tabs, market cards. */
export function MatchSkeleton() {
  return (
    <div role="status" aria-label="Loading markets" className="space-y-3">
      <span className={`${bar} block h-3 w-20`} />
      <div className="h-36 animate-pulse rounded-2xl bg-primary/25 sm:h-48" />
      <span className={`${bar} block h-11 w-full rounded-2xl`} />
      <div className="flex gap-2">{[0, 1, 2, 3].map((i) => <span key={i} className={`${bar} h-9 w-20`} />)}</div>
      {[3, 2, 3].map((n, i) => (
        <div key={i} className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <span className={`${bar} block h-4 w-36`} />
          <div className={`grid gap-2 ${n === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
            {Array.from({ length: n }, (_, j) => <span key={j} className={`${bar} h-12`} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Casino lobby: a grid of game tiles. */
export function GamesSkeleton() {
  return (
    <div role="status" aria-label="Loading games" className="space-y-3">
      <span className={`${bar} block h-5 w-32`} />
      <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 12 }, (_, i) => <span key={i} className={`${bar} aspect-[3/4] rounded-xl`} />)}
      </div>
    </div>
  );
}

/** Any other page: a heading and a few content blocks. */
export function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="space-y-3">
      <span className={`${bar} block h-6 w-40`} />
      <span className={`${bar} block h-24 w-full rounded-2xl`} />
      <span className={`${bar} block h-40 w-full rounded-2xl`} />
    </div>
  );
}
