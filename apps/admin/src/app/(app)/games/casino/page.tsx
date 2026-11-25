'use client';

import { useEffect, useState } from 'react';
import { BsBellFill, BsController } from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Notice, PageHeader, Pager, Panel, Select, StatTile, TextInput, cx, inputClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Row {
  id: number; name: string; provider: string; category: string; slug: string; is_active: boolean; coming_soon: boolean;
  image_url: string; waiting: number;
}
interface Data {
  count: number; page: number; page_size: number; results: Row[]; categories: [string, string][];
  totals: { all: number; soon: number; waiting: number };
}

/** The casino catalogue: which games are live, which are "coming soon", and how many players
 *  asked to be told. Launching a game notifies them. */
export default function CasinoGamesPage() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setSearch(q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  const qs = new URLSearchParams({ page: String(page), ...(search && { q: search }), ...(category && { category }), ...(status && { status }) });
  const { data, refetch } = useApi<Data>(`/admin/casino/games/?${qs}`);
  const [busy, setBusy] = useState(0);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const label = Object.fromEntries(data?.categories ?? []);

  async function change(row: Row, body: Partial<Row>, confirmText?: string) {
    if (!accessToken || (confirmText && !window.confirm(confirmText))) return;
    setBusy(row.id); setNotice(null);
    const res = await authedRequest<{ notified: number }>('PATCH', `/admin/casino/games/${row.id}/`, accessToken, body);
    setBusy(0);
    if (res.error) setNotice({ tone: 'red', text: res.error });
    else if (body.coming_soon === false) setNotice({ tone: 'green', text: `${row.name} is live. ${res.data?.notified ?? 0} players were notified.` });
    refetch();
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={BsController} eyebrow="Games" title="Casino games"
        description="Games marked “coming soon” show in the lobby with a Notify me button. When a game is connected, launch it: everyone waiting gets a notification." />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="Games listed" value={data?.totals.all ?? '…'} icon={BsController} loading={!data} />
        <StatTile label="Coming soon" value={data?.totals.soon ?? '…'} icon={BsController} tone="gold" loading={!data} />
        <StatTile label="Players waiting" value={data?.totals.waiting ?? '…'} hint="Across all coming-soon games" icon={BsBellFill} tone="green" loading={!data} />
      </div>
      <Panel title="Catalogue" description="Most-wanted first."
        actions={
          <div className="flex flex-wrap gap-2">
            <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or studio…" className={cx(inputClass, 'w-52')} />
            <Select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
              <option value="">All categories</option>
              {data?.categories.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">Live and coming soon</option>
              <option value="soon">Coming soon</option>
              <option value="live">Live</option>
            </Select>
          </div>
        } bodyClassName="p-0">
        {!data ? <p className="p-4 text-sm text-muted-foreground">Loading…</p> : !data.results.length ? (
          <div className="p-4"><EmptyState icon={BsController} title="No games">Nothing matches.</EmptyState></div>
        ) : (
          <>
            <ul className="divide-y divide-border/70">
              {data.results.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="font-semibold">
                      {g.name}{' '}
                      {g.coming_soon ? <Badge tone="gold">Coming soon</Badge> : <Badge tone="green" dot>Live</Badge>}{' '}
                      {!g.is_active && <Badge tone="slate">Hidden</Badge>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {g.provider === 'TBA' ? 'Studio to be announced' : g.provider} · {label[g.category] ?? g.category}
                      {g.waiting > 0 && <> · <b className="text-foreground">{g.waiting} waiting</b></>}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    {g.coming_soon ? (
                      <Btn size="sm" variant="primary" busy={busy === g.id}
                        onClick={() => change(g, { coming_soon: false }, `Launch ${g.name}? Only do this once it is connected and playable. ${g.waiting} waiting players will be notified.`)}>
                        Launch
                      </Btn>
                    ) : (
                      <Btn size="sm" busy={busy === g.id} onClick={() => change(g, { coming_soon: true })}>Back to coming soon</Btn>
                    )}
                    <Btn size="sm" busy={busy === g.id} onClick={() => change(g, { is_active: !g.is_active })}>{g.is_active ? 'Hide' : 'Show'}</Btn>
                  </div>
                </li>
              ))}
            </ul>
            <Pager page={data.page} count={data.count} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Panel>
    </div>
  );
}
