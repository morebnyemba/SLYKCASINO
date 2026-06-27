'use client';

import { useState } from 'react';
import { FaImages } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Banner {
  id: number;
  title: string;
  subtitle: string;
  image_url: string;
  link_url: string;
  cta_label: string;
  sort_order: number;
  active: boolean;
  is_live: boolean;
  starts_at: string | null;
  ends_at: string | null;
}

interface BannersResponse { results?: Banner[] }

const BLANK = {
  title: '', subtitle: '', image_url: '', link_url: '', cta_label: '', sort_order: '0',
  starts_at: '', ends_at: '',
};

type FormState = typeof BLANK;

function toForm(b: Banner): FormState {
  return {
    title: b.title, subtitle: b.subtitle ?? '', image_url: b.image_url,
    link_url: b.link_url ?? '', cta_label: b.cta_label ?? '',
    sort_order: String(b.sort_order ?? 0),
    starts_at: b.starts_at ? b.starts_at.slice(0, 16) : '',
    ends_at: b.ends_at ? b.ends_at.slice(0, 16) : '',
  };
}

function toPayload(form: FormState) {
  return {
    title: form.title,
    subtitle: form.subtitle,
    image_url: form.image_url,
    link_url: form.link_url,
    cta_label: form.cta_label,
    sort_order: Number(form.sort_order) || 0,
    starts_at: form.starts_at || null,
    ends_at: form.ends_at || null,
  };
}

export default function BannersPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<BannersResponse>('/promotions/banners/?all=true');
  const banners = data?.results ?? [];

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

  function startEdit(b: Banner) {
    setEditingId(b.id);
    setForm(toForm(b));
    setFormError('');
    setShowForm(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setSaving(true);
    setFormError('');
    const payload = toPayload(form);

    let error: string | undefined;
    if (editingId == null) {
      ({ error } = await authedPost('/promotions/banners/', payload, accessToken));
    } else {
      const res = await fetch(`${config.apiUrl}/promotions/banners/${editingId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify(payload),
      });
      if (!res.ok) error = `API ${res.status}`;
    }

    setSaving(false);
    if (error) { setFormError(error); return; }
    setShowForm(false);
    setEditingId(null);
    setForm({ ...BLANK });
    refetch();
  }

  async function toggleActive(b: Banner) {
    if (!accessToken) return;
    await fetch(`${config.apiUrl}/promotions/banners/${b.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ active: !b.active }),
    });
    refetch();
  }

  async function handleDelete(id: number) {
    if (!accessToken || !confirm('Delete this banner?')) return;
    await fetch(`${config.apiUrl}/promotions/banners/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    refetch();
  }

  const FIELDS: { label: string; key: keyof FormState; type: string; placeholder: string; full?: boolean }[] = [
    { label: 'Title', key: 'title', type: 'text', placeholder: 'SLÝKBETS Aviator' },
    { label: 'Sort order', key: 'sort_order', type: 'number', placeholder: '0' },
    { label: 'Subtitle', key: 'subtitle', type: 'text', placeholder: 'Cash out before the crash', full: true },
    { label: 'Image URL', key: 'image_url', type: 'text', placeholder: 'https://…/banner.jpg', full: true },
    { label: 'Link URL', key: 'link_url', type: 'text', placeholder: '/casino/crash' },
    { label: 'CTA label', key: 'cta_label', type: 'text', placeholder: 'Play now' },
    { label: 'Starts at (optional)', key: 'starts_at', type: 'datetime-local', placeholder: '' },
    { label: 'Ends at (optional)', key: 'ends_at', type: 'datetime-local', placeholder: '' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
            <FaImages size={13} />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Site Banners</h1>
            <p className="text-muted-foreground text-sm">Wide promotional banners shown on the player homepage.</p>
          </div>
        </div>
        <button
          onClick={() => (showForm ? setShowForm(false) : startCreate())}
          className={`rounded-md px-4 py-2 text-sm font-bold shadow transition-transform hover:scale-[1.02] ${
            showForm ? 'border border-border bg-background text-foreground hover:scale-100' : 'bg-gradient-to-br from-gold to-gold/70 text-[#1A1538]'
          }`}
        >
          {showForm ? 'Cancel' : '+ New banner'}
        </button>
      </div>

      {showForm && (
        <Card className="rounded-2xl border-gold/15">
          <CardHeader><CardTitle className="text-base">{editingId == null ? 'Create banner' : 'Edit banner'}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {form.image_url && (
              <div className="relative h-40 overflow-hidden rounded-xl">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={form.image_url} alt="preview" className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent" />
                <div className="absolute inset-0 flex flex-col justify-center gap-1.5 p-6">
                  <p className="max-w-md text-2xl font-extrabold text-white drop-shadow">{form.title || 'Banner title'}</p>
                  {form.subtitle && <p className="max-w-sm text-sm text-white/85">{form.subtitle}</p>}
                  {form.cta_label && (
                    <span className="mt-1 w-fit rounded-lg bg-secondary px-4 py-1.5 text-xs font-bold uppercase tracking-wide text-white">
                      {form.cta_label}
                    </span>
                  )}
                </div>
              </div>
            )}
            <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
              {FIELDS.map(({ label, key, type, placeholder, full }) => (
                <div key={key} className={`space-y-1 ${full ? 'sm:col-span-2' : ''}`}>
                  <label className="text-sm font-medium">{label}</label>
                  <input
                    type={type}
                    required={key === 'title' || key === 'image_url'}
                    value={form[key]}
                    onChange={(e) => set(key, e.target.value)}
                    placeholder={placeholder}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              ))}
              {formError && <p className="col-span-2 text-sm text-red-500">{formError}</p>}
              <div className="col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? 'Saving…' : editingId == null ? 'Create banner' : 'Save changes'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading banners…</p>}
          {!loading && banners.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No banners yet. Create one above.</p>
          )}
          {banners.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Banner</th>
                  <th className="px-4 py-3 font-medium">Link</th>
                  <th className="px-4 py-3 font-medium">Order</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {banners.map((b) => (
                  <tr key={b.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={b.image_url} alt="" className="h-10 w-16 shrink-0 rounded object-cover bg-muted" />
                        <div>
                          <p className="font-medium">{b.title}</p>
                          <p className="text-xs text-muted-foreground">{b.subtitle || '—'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{b.link_url || '—'}</td>
                    <td className="px-4 py-3">{b.sort_order}</td>
                    <td className="px-4 py-3">
                      {b.active
                        ? <Badge variant={b.is_live ? 'default' : 'secondary'}>{b.is_live ? 'Live' : 'Scheduled'}</Badge>
                        : <Badge variant="secondary">Off</Badge>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => startEdit(b)} className="rounded px-2 py-1 text-xs border border-border hover:bg-accent">Edit</button>
                        <button onClick={() => toggleActive(b)} className="rounded px-2 py-1 text-xs border border-border hover:bg-accent">
                          {b.active ? 'Disable' : 'Enable'}
                        </button>
                        <button onClick={() => handleDelete(b.id)} className="rounded px-2 py-1 text-xs border border-destructive text-destructive hover:bg-destructive/10">Delete</button>
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
