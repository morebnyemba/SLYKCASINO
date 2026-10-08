'use client';

import { useEffect, useState } from 'react';
import { BsPencil, BsPlusLg, BsSearch, BsToggleOff, BsToggleOn, BsTrash3, BsTrophy } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Pager, Panel, Select, Switch, Tabs, TextInput,
  cx, inputClass, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import type { AdminLeague, Paged } from '@/lib/sportsbook';
import { LoadingState } from '@slyk/ui/components/spinner';

const PAGE_SIZE = 50;
type Filter = 'all' | 'enabled' | 'disabled';
const EMPTY = { name: '', country: '', logo_url: '', flag_url: '', sort_order: '1000', enabled: true };

function LeagueDrawer({ league, open, onClose, onSaved }: {
  league: AdminLeague | null; open: boolean; onClose: () => void; onSaved: (text: string) => void;
}) {
  const { accessToken } = useAuth();
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    setForm(league ? {
      name: league.name, country: league.country, logo_url: league.logo_url, flag_url: league.flag_url,
      sort_order: String(league.sort_order), enabled: league.enabled,
    } : { ...EMPTY });
  }, [league, open]);
  const set = <K extends keyof typeof EMPTY>(k: K, v: (typeof EMPTY)[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true); setError('');
    const body = { ...form, sort_order: Number(form.sort_order) || 0 };
    const res = league
      ? await authedRequest('PATCH', `/admin/sportsbook/leagues/${league.id}/`, accessToken, body)
      : await authedRequest('POST', '/admin/sportsbook/leagues/', accessToken, body);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    onSaved(league ? `${form.name} updated.` : `${form.name} added.`);
  }

  const preview = form.flag_url || form.logo_url;
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={league ? 'Edit league' : 'Add league'}
      description={league ? `${league.provider === 'manual' ? 'Added by hand' : `api-football league #${league.league_id}`}` : 'For competitions the feed doesn’t cover, e.g. local leagues.'}
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn variant="primary" type="submit" form="league-form" busy={busy}>{league ? 'Save league' : 'Add league'}</Btn></>}
    >
      <form id="league-form" onSubmit={submit} className="space-y-4">
        <div className="flex items-center gap-3 rounded-xl border border-border/70 bg-muted/30 p-4">
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="" className="h-10 w-14 rounded-md object-cover" />
          ) : <span className="flex h-10 w-14 items-center justify-center rounded-md bg-muted text-muted-foreground"><BsTrophy /></span>}
          <div className="min-w-0">
            <p className="truncate font-bold">{form.name || 'League name'}</p>
            <p className="truncate text-xs text-muted-foreground">{form.country || 'Country'}</p>
          </div>
        </div>
        <Field label="Name"><TextInput required value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Castle Lager Premier Soccer League" /></Field>
        <Field label="Country"><TextInput value={form.country} onChange={(e) => set('country', e.target.value)} placeholder="Zimbabwe" /></Field>
        <Field label="Flag image URL" hint="Shown next to the league name in the sportsbook."><TextInput type="url" value={form.flag_url} onChange={(e) => set('flag_url', e.target.value)} placeholder="https://…" /></Field>
        <Field label="Logo image URL"><TextInput type="url" value={form.logo_url} onChange={(e) => set('logo_url', e.target.value)} placeholder="https://…" /></Field>
        <Field label="Display order" hint="Lower numbers show first. Featured competitions use 10–160; everything else 1000.">
          <TextInput type="number" min={0} value={form.sort_order} onChange={(e) => set('sort_order', e.target.value)} />
        </Field>
        <label className="flex items-center justify-between gap-3 rounded-xl border border-border/70 p-3.5 text-sm">
          <span><span className="font-semibold">Enabled</span><span className="block text-xs text-muted-foreground">Disabled leagues aren&apos;t imported from the feed, which also saves API quota.</span></span>
          <Switch checked={form.enabled} onChange={(v) => set('enabled', v)} label="Enabled" />
        </label>
        {error && <Notice tone="red">{error}</Notice>}
      </form>
    </Drawer>
  );
}

export default function LeaguesPage() {
  const { accessToken } = useAuth();
  const [filter, setFilter] = useState<Filter>('all');
  const [country, setCountry] = useState('');
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [editing, setEditing] = useState<AdminLeague | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  useEffect(() => { const t = setTimeout(() => setQ(search.trim()), 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => { setPage(1); setSelected(new Set()); }, [filter, country, q]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (filter !== 'all') query.set('enabled', String(filter === 'enabled'));
  if (country) query.set('country', country);
  if (q) query.set('search', q);
  const { data, loading, refetch } = useApi<Paged<AdminLeague>>(`/admin/sportsbook/leagues/?${query}`);
  const { data: countries } = useApi<{ country: string; count: number }[]>('/admin/sportsbook/leagues/countries/');
  const rows = data?.results ?? [];
  const allOnPage = rows.length > 0 && rows.every((l) => selected.has(l.id));

  async function patch(l: AdminLeague, body: Partial<AdminLeague>, text: string) {
    if (!accessToken) return;
    const res = await authedRequest('PATCH', `/admin/sportsbook/leagues/${l.id}/`, accessToken, body);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text });
    refetch();
  }
  async function bulk(enabled: boolean) {
    if (!accessToken || selected.size === 0) return;
    const res = await authedRequest<{ updated: number }>('POST', '/admin/sportsbook/leagues/bulk/', accessToken, { ids: [...selected], enabled });
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${res.data?.updated ?? 0} league(s) ${enabled ? 'enabled' : 'disabled'}.` });
    setSelected(new Set());
    refetch();
  }
  async function remove(l: AdminLeague) {
    if (!accessToken || !confirm(`Delete ${l.name}?`)) return;
    const res = await authedRequest('DELETE', `/admin/sportsbook/leagues/${l.id}/`, accessToken);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${l.name} deleted.` });
    refetch();
  }

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BsTrophy}
        eyebrow="Sportsbook"
        title="Leagues"
        description="Which competitions are imported from the feed and the order they appear in. Disabled leagues aren't fetched at all."
        actions={<Btn variant="primary" icon={BsPlusLg} onClick={() => { setEditing(null); setDrawer(true); }}>Add league</Btn>}
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <Tabs value={filter} onChange={setFilter} items={[{ id: 'all', label: 'All' }, { id: 'enabled', label: 'Enabled' }, { id: 'disabled', label: 'Disabled' }]} />
        <div className="flex flex-1 gap-2 lg:justify-end">
          <div className="relative min-w-0 flex-1 sm:max-w-sm">
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="League, country or id" className={cx(inputClass, 'pl-9')} />
          </div>
          <div className="w-48 shrink-0">
            <Select value={country} onChange={(e) => setCountry(e.target.value)}>
              <option value="">All countries</option>
              {(countries ?? []).map((c) => <option key={c.country} value={c.country}>{c.country} ({c.count})</option>)}
            </Select>
          </div>
        </div>
      </div>

      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-secondary/40 bg-secondary/10 px-4 py-2.5 text-sm">
          <span className="font-semibold">{selected.size} selected</span>
          <Btn size="sm" variant="success" icon={BsToggleOn} onClick={() => bulk(true)}>Enable</Btn>
          <Btn size="sm" icon={BsToggleOff} onClick={() => bulk(false)}>Disable</Btn>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs font-semibold text-muted-foreground hover:text-foreground">Clear selection</button>
        </div>
      )}

      <Panel padded={false}>
        {loading && !data ? (
          <LoadingState className="py-16" label="Loading leagues…" />
        ) : rows.length === 0 ? (
          <EmptyState icon={BsTrophy} title="No leagues found">
            Leagues are added automatically the first time the feed imports fixtures. You can also add one by hand.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead>
                <tr>
                  <th className={cx(thClass, 'w-10')}>
                    <input
                      type="checkbox"
                      aria-label="Select all on this page"
                      checked={allOnPage}
                      onChange={() => setSelected(allOnPage ? new Set() : new Set(rows.map((l) => l.id)))}
                      className="h-4 w-4 accent-[var(--secondary)]"
                    />
                  </th>
                  <th className={thClass}>League</th>
                  <th className={thClass}>Source</th>
                  <th className={cx(thClass, 'text-center')}>Upcoming</th>
                  <th className={thClass}>Order</th>
                  <th className={cx(thClass, 'text-center')}>Enabled</th>
                  <th className={thClass} />
                </tr>
              </thead>
              <tbody>
                {rows.map((l) => {
                  const icon = l.flag_url || l.logo_url;
                  return (
                    <tr key={l.id} className={cx(trClass, !l.enabled && 'opacity-60')}>
                      <td className={tdClass}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${l.name}`}
                          checked={selected.has(l.id)}
                          onChange={() => setSelected((s) => { const n = new Set(s); if (n.has(l.id)) n.delete(l.id); else n.add(l.id); return n; })}
                          className="h-4 w-4 accent-[var(--secondary)]"
                        />
                      </td>
                      <td className={tdClass}>
                        <div className="flex items-center gap-3">
                          {icon ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={icon} alt="" className="h-7 w-9 shrink-0 rounded-md bg-muted object-cover" />
                          ) : <span className="flex h-7 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground"><BsTrophy size={12} /></span>}
                          <div className="min-w-0">
                            <p className="truncate font-semibold">{l.name || `League ${l.league_id}`}</p>
                            <p className="truncate text-xs text-muted-foreground">{l.country || '—'}</p>
                          </div>
                        </div>
                      </td>
                      <td className={tdClass}>{l.provider === 'manual' ? <Badge tone="gold">Manual</Badge> : <Badge tone="indigo">Feed #{l.league_id}</Badge>}</td>
                      <td className={cx(tdClass, 'text-center font-mono tabular-nums')}>{l.upcoming_count || '—'}</td>
                      <td className={tdClass}>
                        <input
                          type="number"
                          min={0}
                          defaultValue={l.sort_order}
                          aria-label={`Display order for ${l.name}`}
                          onBlur={(e) => { const v = Number(e.target.value); if (v !== l.sort_order) void patch(l, { sort_order: v }, `${l.name} moved to position ${v}.`); }}
                          className="h-8 w-20 rounded-lg border border-border bg-input/60 px-2 text-center font-mono text-xs outline-none focus:border-secondary"
                        />
                      </td>
                      <td className={cx(tdClass, 'text-center')}>
                        <Switch checked={l.enabled} onChange={(v) => patch(l, { enabled: v }, `${l.name} ${v ? 'enabled' : 'disabled'}.`)} label={`${l.name} enabled`} />
                      </td>
                      <td className={cx(tdClass, 'whitespace-nowrap text-right')}>
                        <button onClick={() => { setEditing(l); setDrawer(true); }} aria-label={`Edit ${l.name}`} className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"><BsPencil size={13} /></button>
                        {l.provider === 'manual' && (
                          <button onClick={() => remove(l)} aria-label={`Delete ${l.name}`} className="rounded-lg p-2 text-muted-foreground hover:bg-live/10 hover:text-live"><BsTrash3 size={13} /></button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <Pager page={page} count={data?.count ?? 0} pageSize={PAGE_SIZE} onPage={setPage} />
      </Panel>

      <LeagueDrawer
        league={editing}
        open={drawer}
        onClose={() => setDrawer(false)}
        onSaved={(text) => { setDrawer(false); setNotice({ tone: 'green', text }); refetch(); }}
      />
    </div>
  );
}
