'use client';

import { useState } from 'react';
import { BsSearch } from 'react-icons/bs';
import { Btn, Panel, TextInput } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';
import { TicketsTable, type TicketsResponse } from './tickets';

/** Find any ticket: by number as players see it (S12 / M5), a username or an email. */
export function TicketFinder() {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const params = new URLSearchParams({ ...(query && { q: query }), ...(status && { status }), ...(kind && { kind }) });
  const { data, loading } = useApi<TicketsResponse>(`/admin/tickets/?${params}`);
  const select = 'h-10 rounded-xl border border-border bg-background px-3 text-sm';
  return (
    <Panel title="Find tickets" description="Every player’s singles (#S…) and multiples (#M…), newest first. Click a multiple to see its legs." padded={false}>
      <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ticket (S12, M5), username or email" className="w-72" />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status" className={select}>
          <option value="">Any status</option>
          {['open', 'won', 'lost', 'void', 'cashed_out'].map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type" className={select}>
          <option value="">Singles & multiples</option><option value="single">Singles</option><option value="multiple">Multiples</option>
        </select>
        <Btn type="submit" variant="primary" icon={BsSearch}>Search</Btn>
        {query && <Btn type="button" onClick={() => { setQ(''); setQuery(''); }}>Clear</Btn>}
      </form>
      {loading && !data ? <div className="h-32 animate-pulse bg-muted/40" /> : (
        <div className="max-h-[560px] overflow-y-auto"><TicketsTable tickets={data?.results ?? []} /></div>
      )}
    </Panel>
  );
}
