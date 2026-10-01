'use client';

import { useState } from 'react';
import { FaGift } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Promo {
  id: number;
  name: string;
  kind: string;
  active: boolean;
  bonus_amount: string;
  wagering_multiplier: string;
  starts_at: string | null;
  ends_at: string | null;
  code: string;
  terms_html: string;
  claim_count: number;
}

interface PromosResponse { results?: Promo[] }

const KINDS = [
  { id: 'deposit', label: 'Deposit Bonus' },
  { id: 'freebet', label: 'Free Bet' },
  { id: 'cashback', label: 'Cashback' },
];

const BLANK = {
  name: '', kind: 'deposit', bonus_amount: '0', wagering_multiplier: '1',
  starts_at: '', ends_at: '', code: '', terms_html: '',
};

type FormState = typeof BLANK;

function toForm(p: Promo): FormState {
  return {
    name: p.name, kind: p.kind, bonus_amount: p.bonus_amount, wagering_multiplier: p.wagering_multiplier,
    starts_at: p.starts_at ? p.starts_at.slice(0, 16) : '',
    ends_at: p.ends_at ? p.ends_at.slice(0, 16) : '',
    code: p.code ?? '', terms_html: p.terms_html ?? '',
  };
}

function toPayload(form: FormState) {
  return {
    name: form.name,
    kind: form.kind,
    bonus_amount: form.bonus_amount || '0',
    wagering_multiplier: form.wagering_multiplier || '1',
    starts_at: form.starts_at || null,
    ends_at: form.ends_at || null,
    code: form.code,
    terms_html: form.terms_html,
  };
}

export default function PromotionsPage() {
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<PromosResponse>('/promotions/');
  const promos = data?.results ?? [];

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>({ ...BLANK });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const set = (k: keyof FormState, v: string) => setForm((f) => ({ ...f, [k]: v }));

  function startCreate() {
    setEditingId(null);
    setForm({ ...BLANK });
    setFormError('');
    setShowForm(true);
  }

  function startEdit(p: Promo) {
    setEditingId(p.id);
    setForm(toForm(p));
    setFormError('');
    setShowForm(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setSaving(true);
    setFormError('');
    const payload = toPayload(form);

    let error_: string | undefined;
    if (editingId == null) {
      ({ error: error_ } = await authedPost('/promotions/', payload, accessToken));
    } else {
      const res = await fetch(`${config.apiUrl}/promotions/${editingId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify(payload),
      });
      if (!res.ok) error_ = `API ${res.status}`;
    }

    setSaving(false);
    if (error_) { setFormError(error_); return; }
    setShowForm(false);
    setEditingId(null);
    setForm({ ...BLANK });
    refetch();
  }

  async function toggleActive(p: Promo) {
    if (!accessToken) return;
    await fetch(`${config.apiUrl}/promotions/${p.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ active: !p.active }),
    });
    refetch();
  }

  async function handleDelete(id: number) {
    if (!accessToken || !confirm('Delete this promotion?')) return;
    await fetch(`${config.apiUrl}/promotions/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    refetch();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
            <FaGift size={13} />
          </span>
          <h1 className="text-2xl font-bold">Promotions</h1>
        </div>
        <button
          onClick={() => (showForm ? setShowForm(false) : startCreate())}
          className={`rounded-md px-4 py-2 text-sm font-bold shadow transition-transform hover:scale-[1.02] ${
            showForm ? 'border border-border bg-background text-foreground hover:scale-100' : 'bg-gradient-to-br from-gold to-gold/70 text-gold-foreground'
          }`}
        >
          {showForm ? 'Cancel' : '+ New promotion'}
        </button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {showForm && (
        <Card className="rounded-2xl border-gold/15">
          <CardHeader><CardTitle className="text-base">{editingId == null ? 'Create promotion' : 'Edit promotion'}</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-sm font-medium">Name</label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  placeholder="Welcome Bonus"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Type</label>
                <select
                  value={form.kind}
                  onChange={(e) => set('kind', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Bonus amount</label>
                <input
                  type="number" step="0.01"
                  value={form.bonus_amount}
                  onChange={(e) => set('bonus_amount', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Wagering multiplier</label>
                <input
                  type="number" step="0.1"
                  value={form.wagering_multiplier}
                  onChange={(e) => set('wagering_multiplier', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Starts at (optional)</label>
                <input
                  type="datetime-local"
                  value={form.starts_at}
                  onChange={(e) => set('starts_at', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Ends at (optional)</label>
                <input
                  type="datetime-local"
                  value={form.ends_at}
                  onChange={(e) => set('ends_at', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">Promo code (optional)</label>
                <input
                  type="text"
                  value={form.code}
                  onChange={(e) => set('code', e.target.value)}
                  placeholder="WELCOME100"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className="text-sm font-medium">Terms (HTML, optional)</label>
                <textarea
                  value={form.terms_html}
                  onChange={(e) => set('terms_html', e.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              {formError && <p className="col-span-2 text-sm text-red-500">{formError}</p>}
              <div className="col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? 'Saving…' : editingId == null ? 'Create promotion' : 'Save changes'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading promotions…</p>}
          {!loading && promos.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No promotions yet. Create one above.</p>
          )}
          {promos.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Bonus</th>
                  <th className="px-4 py-3 font-medium">Wagering</th>
                  <th className="px-4 py-3 font-medium">Claims</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {promos.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium">{p.name}{p.code && <span className="ml-2 font-mono text-xs text-muted-foreground">{p.code}</span>}</td>
                    <td className="px-4 py-3">{KINDS.find((k) => k.id === p.kind)?.label ?? p.kind}</td>
                    <td className="px-4 py-3">{p.bonus_amount}</td>
                    <td className="px-4 py-3">{p.wagering_multiplier}×</td>
                    <td className="px-4 py-3">{p.claim_count}</td>
                    <td className="px-4 py-3">
                      {p.active ? <Badge variant="default">Active</Badge> : <Badge variant="secondary">Off</Badge>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => startEdit(p)} className="rounded px-2 py-1 text-xs border border-border hover:bg-accent">Edit</button>
                        <button onClick={() => toggleActive(p)} className="rounded px-2 py-1 text-xs border border-border hover:bg-accent">
                          {p.active ? 'Disable' : 'Enable'}
                        </button>
                        <button onClick={() => handleDelete(p.id)} className="rounded px-2 py-1 text-xs border border-destructive text-destructive hover:bg-destructive/10">Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
