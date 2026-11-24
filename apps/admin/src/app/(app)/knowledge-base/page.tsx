'use client';

import { useEffect, useMemo, useState } from 'react';
import { BsBook, BsChatQuote, BsCheck2, BsLightbulb, BsPlus, BsQuestionCircle, BsRobot } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Pager, Panel, Select, StatTile, Switch, Tabs, TextInput, cx, inputClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Article {
  id?: number; question: string; example_questions: string; learned_questions: string; keywords: string; answer: string;
  preview?: string; buttons: string; category: string; category_label?: string; is_active: boolean; is_draft?: boolean;
  times_asked?: number; hit_count?: number; last_used_at?: string | null; updated_by?: string;
}
interface KbData {
  results: Article[]; categories: [string, string][];
  placeholders: { name: string; label: string; value: string }[];
  counts: { answers: number; drafts: number; unanswered: number; asked_30d: number; answered_30d: number; kb_30d: number };
}
interface Asked {
  id: number; text: string; source: string; source_label: string; article: number | null; article_question: string;
  score: number; reply: string; reviewed: boolean; address: string; created_at: string;
}
interface AskedPage { count: number; page: number; pages: number; results: Asked[] }
interface TryResult {
  action: 'kb' | 'ai' | 'suggest' | 'none'; problem: boolean; ai_enabled: boolean; score: number; reply: string; buttons: string[];
  article: { id: number; question: string } | null; handoff: boolean; known: boolean | null; reason?: string; detail?: string;
  matches: { id: number; question: string; score: number }[];
  thresholds: { sure: number; answer: number; suggest: number };
}

type Tab = 'answers' | 'drafts' | 'asked' | 'try';
const SOURCE_TONE: Record<string, 'green' | 'gold' | 'red' | 'indigo' | 'slate'> = {
  kb: 'green', ai: 'green', ai_facts: 'indigo', ai_unsure: 'gold', suggested: 'gold', handoff: 'slate', none: 'red',
};
const ACTION_LABEL: Record<TryResult['action'], string> = {
  kb: 'Sent from the knowledge base (no AI call)', ai: 'Answered by the AI', suggest: 'Offered close answers to tap',
  none: 'Not answered',
};
const blank = (question = ''): Article => ({
  question, example_questions: '', learned_questions: '', keywords: '', answer: '', buttons: 'MENU', category: 'other', is_active: true,
});
const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : '—');

/** The WhatsApp bot's knowledge base: staff-written answers sent as written when a question matches,
 *  read by the AI for everything else, and the questions players asked that nothing answered. */
export default function KnowledgeBasePage() {
  const { accessToken } = useAuth();
  const [tab, setTab] = useState<Tab>('answers');
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  useEffect(() => { const t = setTimeout(() => setSearch(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const drafts = tab === 'drafts';
  const { data, refetch } = useApi<KbData>(`/admin/chatbot/knowledge/?drafts=${drafts ? 1 : 0}${search ? `&q=${encodeURIComponent(search)}` : ''}`);
  const [askedFilter, setAskedFilter] = useState('unanswered');
  const [page, setPage] = useState(1);
  const { data: asked, refetch: refetchAsked } = useApi<AskedPage>(tab === 'asked' ? `/admin/chatbot/knowledge/questions/?status=${askedFilter}&page=${page}` : null);
  const [editing, setEditing] = useState<Article | null>(null);
  const [fromQuestion, setFromQuestion] = useState<number | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const [tryQ, setTryQ] = useState('');
  const [useAi, setUseAi] = useState(true);
  const [tried, setTried] = useState<TryResult | null>(null);

  const c = data?.counts;
  const grouped = useMemo(() => {
    const out: Record<string, Article[]> = {};
    for (const a of data?.results ?? []) (out[a.category_label ?? a.category] ??= []).push(a);
    return out;
  }, [data]);

  function open(a: Article, question: number | null = null) { setEditing({ ...a }); setFromQuestion(question); }

  async function save() {
    if (!accessToken || !editing) return;
    setBusy('save'); setNotice(null);
    const body = { ...editing, ...(fromQuestion ? { from_question: fromQuestion } : {}) };
    const res = editing.id
      ? await authedRequest<Article>('PATCH', `/admin/chatbot/knowledge/${editing.id}/`, accessToken, body)
      : await authedPost<Article>('/admin/chatbot/knowledge/', body, accessToken);
    setBusy('');
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setEditing(null); setNotice({ tone: 'green', text: 'Saved. The bot uses it from the next message.' });
    refetch(); if (fromQuestion) refetchAsked();
  }

  async function approve(a: Article, edited?: Article) {
    if (!accessToken || !a.id) return;
    setBusy(`approve-${a.id}`);
    const res = await authedRequest<Article>('PATCH', `/admin/chatbot/knowledge/${a.id}/`, accessToken, { ...(edited ?? {}), approve: true });
    setBusy('');
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Approved: players get this answer now.' });
    setEditing(null); refetch();
  }

  async function remove(a: Article) {
    if (!accessToken || !a.id || !window.confirm(`Delete “${a.question}”?`)) return;
    setBusy(`del-${a.id}`);
    await authedRequest('DELETE', `/admin/chatbot/knowledge/${a.id}/`, accessToken);
    setBusy(''); setEditing(null); refetch();
  }

  async function markReviewed(ids: number[]) {
    if (!accessToken || !ids.length) return;
    await authedPost('/admin/chatbot/knowledge/questions/', { ids, reviewed: true }, accessToken);
    refetchAsked(); refetch();
  }

  async function tryIt() {
    if (!accessToken || !tryQ.trim()) return;
    setBusy('try'); setTried(null);
    const res = await authedPost<TryResult>('/admin/chatbot/knowledge/try/', { question: tryQ, use_ai: useAi }, accessToken);
    setBusy('');
    if (res.error && !res.data) setNotice({ tone: 'red', text: res.error });
    else setTried(res.data ?? null);
  }

  function insert(name: string) {
    if (!editing) return;
    setEditing({ ...editing, answer: `${editing.answer}{${name}}` });
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={BsBook} eyebrow="Marketing" title="Knowledge base"
        description="Answers the WhatsApp bot sends as written when a question matches: instant, free and the same every time. The AI reads them for everything else, and learns new wordings from what it answers. {placeholders} fill in live fees and limits, so answers never go stale."
        actions={<Btn variant="primary" icon={BsPlus} onClick={() => open(blank())}>New answer</Btn>} />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile label="Answers" value={c?.answers ?? '…'} icon={BsBook} loading={!c} />
        <StatTile label="Questions, last 30 days" value={c?.asked_30d ?? '…'} hint={c ? `${pct(c.answered_30d, c.asked_30d)} answered` : undefined} icon={BsChatQuote} loading={!c} />
        <StatTile label="Answered without AI" value={c ? pct(c.kb_30d, c.asked_30d) : '…'} hint="Free and instant" icon={BsLightbulb} tone="green" loading={!c} />
        <StatTile label="Waiting for an answer" value={c ? c.unanswered + c.drafts : '…'} hint={c ? `${c.unanswered} unanswered · ${c.drafts} AI drafts` : undefined} icon={BsQuestionCircle} tone="gold" loading={!c} />
      </div>

      <Tabs<Tab> value={tab} onChange={(t) => { setTab(t); setPage(1); }} items={[
        { id: 'answers', label: 'Answers', count: c?.answers },
        { id: 'drafts', label: 'AI drafts', count: c?.drafts, tone: c?.drafts ? 'red' : undefined },
        { id: 'asked', label: 'What players asked', count: c?.unanswered, tone: c?.unanswered ? 'red' : undefined },
        { id: 'try', label: 'Try it' },
      ]} />

      {(tab === 'answers' || tab === 'drafts') && (
        <Panel title={drafts ? 'AI drafts' : 'Answers'}
          description={drafts
            ? 'The AI answered these from the site facts because no answer covered them. Players never get a draft: edit it if needed and approve it, or delete it. Most asked first.'
            : 'Grouped by category. Tap one to edit. Learned wordings were added by the bot when the AI answered from that answer.'}
          actions={<TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className={cx(inputClass, 'w-48')} />}>
          {!data ? <p className="text-sm text-muted-foreground">Loading…</p> : !data.results.length ? (
            <EmptyState icon={drafts ? BsRobot : BsBook} title={drafts ? 'No drafts' : 'No answers yet'}>
              {drafts ? 'When the AI answers something new, it lands here for you to check.' : 'Add the questions players ask most.'}
            </EmptyState>
          ) : drafts ? (
            <ul className="divide-y divide-border/70">
              {data.results.map((a) => (
                <li key={a.id} className="flex flex-wrap items-start justify-between gap-3 py-3 text-sm">
                  <button className="min-w-0 flex-1 text-left" onClick={() => open(a)}>
                    <p className="font-semibold">{a.question} <Badge tone="gold">asked {a.times_asked}×</Badge></p>
                    <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">{a.answer}</p>
                  </button>
                  <div className="flex gap-2">
                    <Btn size="sm" variant="primary" icon={BsCheck2} busy={busy === `approve-${a.id}`} onClick={() => approve(a)}>Approve</Btn>
                    <Btn size="sm" onClick={() => open(a)}>Edit</Btn>
                    <Btn size="sm" busy={busy === `del-${a.id}`} onClick={() => remove(a)}>Delete</Btn>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="space-y-5">
              {Object.entries(grouped).map(([cat, items]) => (
                <div key={cat}>
                  <p className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">{cat}</p>
                  <ul className="divide-y divide-border/70 rounded-xl border border-border/70">
                    {items.map((a) => (
                      <li key={a.id}>
                        <button className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-muted/40" onClick={() => open(a)}>
                          <span className="min-w-0 flex-1">
                            <span className="font-semibold">{a.question}</span>
                            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{a.preview}</span>
                          </span>
                          <span className="flex items-center gap-2 text-xs text-muted-foreground">
                            {a.learned_questions && <Badge tone="indigo">{a.learned_questions.split('\n').length} learned</Badge>}
                            {!a.is_active && <Badge tone="slate">Off</Badge>}
                            <span className="tabular-nums">{a.hit_count} sent</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === 'asked' && (
        <Panel title="What players asked"
          description="Every question the bot tried to answer, kept 90 days. Unanswered ones show what to add: write an answer and the bot handles it from the next message."
          actions={
            <Select value={askedFilter} onChange={(e) => { setAskedFilter(e.target.value); setPage(1); }}>
              <option value="unanswered">Unanswered</option>
              <option value="handoff">Handed to a person</option>
              <option value="kb">Knowledge base</option>
              <option value="ai">AI, from an answer</option>
              <option value="ai_facts">AI, from the site facts</option>
              <option value="all">All</option>
            </Select>
          } bodyClassName="p-0">
          {!asked ? <p className="p-4 text-sm text-muted-foreground">Loading…</p> : !asked.results.length ? (
            <div className="p-4"><EmptyState icon={BsChatQuote} title="Nothing here">No questions in this list.</EmptyState></div>
          ) : (
            <>
              <ul className="divide-y divide-border/70">
                {asked.results.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3 text-sm">
                    <div className="min-w-0 flex-1 space-y-1">
                      <p className="font-semibold">“{r.text}”</p>
                      <p className="text-xs text-muted-foreground">
                        <Badge tone={SOURCE_TONE[r.source] ?? 'slate'}>{r.source_label}</Badge>{' '}
                        {r.article_question && <>closest: {r.article_question} ({Math.round(r.score * 100)}%) · </>}
                        …{r.address.slice(-4)} · {new Date(r.created_at).toLocaleString()}
                      </p>
                      {r.reply && <p className="line-clamp-2 text-xs text-muted-foreground">↳ {r.reply}</p>}
                    </div>
                    <div className="flex gap-2">
                      <Btn size="sm" variant="primary" onClick={() => open(
                        { ...blank(r.text), answer: r.source.startsWith('ai') ? r.reply : '' }, r.id)}>Write answer</Btn>
                      {!r.reviewed && <Btn size="sm" onClick={() => markReviewed([r.id])}>Dismiss</Btn>}
                    </div>
                  </li>
                ))}
              </ul>
              <Pager page={asked.page} count={asked.count} pageSize={50} onPage={setPage} />
            </>
          )}
        </Panel>
      )}

      {tab === 'try' && (
        <Panel title="Try it" description="What the bot would answer, and why. Nothing is logged, learned or sent.">
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="A question, as a player would type it" className="min-w-[260px] flex-1">
                <TextInput value={tryQ} onChange={(e) => setTryQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && tryIt()}
                  placeholder="how much do you charge to withdrw?" />
              </Field>
              <span className="flex items-center gap-2 pb-2 text-sm"><Switch checked={useAi} onChange={setUseAi} label="Use the AI" /> Use the AI</span>
              <Btn variant="primary" busy={busy === 'try'} onClick={tryIt}>Try</Btn>
            </div>
            {tried && (
              <div className="space-y-3 rounded-xl border border-border/70 p-4 text-sm">
                <p className="font-semibold">
                  {ACTION_LABEL[tried.action]}
                  {tried.problem && <Badge tone="gold" className="ml-2">Sounds like a problem: no general answer</Badge>}
                  {tried.handoff && <Badge tone="red" className="ml-2">Hands over to a person</Badge>}
                  {!tried.ai_enabled && <Badge tone="slate" className="ml-2">AI off</Badge>}
                </p>
                {tried.detail && <p className="text-xs text-destructive">{tried.detail}</p>}
                {tried.reply && <p className="whitespace-pre-line rounded-lg bg-muted/40 p-3">{tried.reply}</p>}
                {!!tried.buttons.length && <p className="text-xs text-muted-foreground">Buttons: {tried.buttons.join(' · ')}</p>}
                {tried.article && <p className="text-xs">Based on: <b>{tried.article.question}</b></p>}
                <div>
                  <p className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">Closest answers</p>
                  {!tried.matches.length ? <p className="text-xs text-muted-foreground">None share a word with the question.</p> : (
                    <ul className="space-y-1 text-xs">
                      {tried.matches.map((m) => (
                        <li key={m.id} className="flex items-center gap-2">
                          <span className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                            <span className={cx('block h-full', m.score >= tried.thresholds.sure ? 'bg-green-500' : m.score >= tried.thresholds.suggest ? 'bg-amber-500' : 'bg-muted-foreground/40')}
                              style={{ width: `${Math.round(m.score * 100)}%` }} />
                          </span>
                          <span className="tabular-nums">{Math.round(m.score * 100)}%</span> {m.question}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Sent as written from {Math.round(tried.thresholds.sure * 100)}% ({Math.round(tried.thresholds.answer * 100)}% with the AI off);
                    offered to tap from {Math.round(tried.thresholds.suggest * 100)}%. Low? Add the player’s wording to the answer’s other wordings.
                  </p>
                </div>
              </div>
            )}
          </div>
        </Panel>
      )}

      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing?.is_draft ? 'AI draft' : editing?.id ? 'Edit answer' : 'New answer'}
        description={editing?.is_draft ? 'Check it carefully: approving sends it to every player who asks.' : undefined}
        footer={editing && (
          <>
            {editing.id && <Btn busy={busy === `del-${editing.id}`} onClick={() => remove(editing)}>Delete</Btn>}
            {editing.is_draft
              ? <Btn variant="primary" busy={busy === `approve-${editing.id}`} onClick={() => approve(editing, editing)}>Save & approve</Btn>
              : <Btn variant="primary" busy={busy === 'save'} onClick={save}>Save</Btn>}
          </>
        )}>
        {editing && (
          <div className="space-y-4">
            <Field label="Question" hint="As a player would ask it.">
              <TextInput value={editing.question} maxLength={200} onChange={(e) => setEditing({ ...editing, question: e.target.value })} />
            </Field>
            <Field label="Other ways players ask it" hint="One per line. Typos and plurals are matched anyway; add different words.">
              <textarea className={cx(inputClass, 'min-h-[90px]')} value={editing.example_questions}
                onChange={(e) => setEditing({ ...editing, example_questions: e.target.value })} />
            </Field>
            {!!editing.id && !editing.is_draft && (
              <Field label="Learned wordings" hint="Added by the bot when the AI answered from this answer. They only help matching: delete any that don't belong.">
                <textarea className={cx(inputClass, 'min-h-[70px]')} value={editing.learned_questions}
                  onChange={(e) => setEditing({ ...editing, learned_questions: e.target.value })} />
              </Field>
            )}
            <Field label="Keywords" hint="Comma-separated. A keyword in a message is a strong match, so keep them specific (“withdrawal fee”, not “fee”).">
              <TextInput value={editing.keywords} onChange={(e) => setEditing({ ...editing, keywords: e.target.value })} />
            </Field>
            <Field label="Answer" hint="Short, WhatsApp style. *bold* works. Tap a value below to insert it.">
              <textarea className={cx(inputClass, 'min-h-[140px]')} value={editing.answer} maxLength={2000}
                onChange={(e) => setEditing({ ...editing, answer: e.target.value })} />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {data?.placeholders.map((p) => (
                <button key={p.name} type="button" title={`${p.label}: ${p.value}`} onClick={() => insert(p.name)}
                  className="rounded-md border border-border/70 px-1.5 py-0.5 font-mono text-[11px] hover:bg-muted">{`{${p.name}}`}</button>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Buttons" hint="Up to 3 bot commands, e.g. DEPOSIT, MENU.">
                <TextInput value={editing.buttons} onChange={(e) => setEditing({ ...editing, buttons: e.target.value })} />
              </Field>
              <Field label="Category">
                <Select value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })}>
                  {data?.categories.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </Field>
            </div>
            {!editing.is_draft && (
              <span className="flex items-center gap-2 text-sm font-semibold">
                <Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} label="On" /> Players get this answer
              </span>
            )}
            {editing.id && <p className="text-xs text-muted-foreground">Sent {editing.hit_count ?? 0} times{editing.updated_by ? ` · last changed by ${editing.updated_by}` : ''}.</p>}
          </div>
        )}
      </Drawer>
    </div>
  );
}
