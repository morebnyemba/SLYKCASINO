'use client';

import { useEffect, useRef, useState } from 'react';
import { BsSearch, BsXCircleFill } from 'react-icons/bs';
import { cx, inputClass } from '@/components/console/ui';
import { LeagueTag } from '@/components/sportsbook/match-bits';
import { useApi } from '@/lib/use-api';
import type { AdminLeague, LeagueRef, Paged } from '@/lib/sportsbook';

/** Searchable league chooser (type to search the league catalogue). */
export function LeaguePicker({ value, onChange }: {
  value: LeagueRef | null;
  onChange: (league: LeagueRef | null) => void;
}) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const { data, loading } = useApi<Paged<AdminLeague>>(
    open ? `/admin/sportsbook/leagues/?page_size=12&search=${encodeURIComponent(debounced)}` : null,
  );

  if (value && !open) {
    return (
      <div className={cx(inputClass, 'flex items-center gap-2')}>
        <LeagueTag league={value} className="min-w-0 flex-1 text-sm text-foreground" />
        <button type="button" onClick={() => setOpen(true)} className="text-xs font-semibold text-secondary hover:underline">Change</button>
        <button type="button" onClick={() => onChange(null)} aria-label="Clear league" className="text-muted-foreground hover:text-foreground">
          <BsXCircleFill size={13} />
        </button>
      </div>
    );
  }

  return (
    <div ref={box} className="relative">
      <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
      <input
        autoFocus={open}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        placeholder="Search leagues or countries…"
        className={cx(inputClass, 'pl-9')}
      />
      {open && (
        <div className="absolute z-20 mt-1.5 max-h-72 w-full overflow-y-auto rounded-xl border border-border bg-card p-1 shadow-xl">
          {loading && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {!loading && (data?.results ?? []).length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No leagues match. Add one on the Leagues page.</p>
          )}
          {(data?.results ?? []).map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => { onChange(l); setOpen(false); setQuery(''); }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-muted"
            >
              <LeagueTag league={l} className="min-w-0 flex-1 text-[13px] text-foreground" />
              {!l.enabled && <span className="text-[10px] font-bold uppercase text-muted-foreground">off</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
