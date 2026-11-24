'use client';

import { useEffect, useRef, useState } from 'react';
import { Badge, Btn, Field, Notice, Panel, TextInput } from '@/components/console/ui';
import { config } from '@/lib/config';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Profile {
  about: string; description: string; address: string; email: string; vertical: string;
  websites: string[]; profile_picture_url: string;
}
interface ProfileResult { ok: boolean; error?: string; profile?: Profile }

const VERTICALS: [string, string][] = [
  ['', 'Not set'], ['ENTERTAIN', 'Entertainment'], ['OTHER', 'Other'], ['FINANCE', 'Finance'], ['PROF_SERVICES', 'Professional services'],
  ['RETAIL', 'Retail'], ['EVENT_PLAN', 'Events'], ['TRAVEL', 'Travel'], ['HOTEL', 'Hotel'], ['RESTAURANT', 'Restaurant'],
  ['EDU', 'Education'], ['HEALTH', 'Health'], ['BEAUTY', 'Beauty'], ['APPAREL', 'Clothing'], ['AUTO', 'Automotive'],
  ['GROCERY', 'Grocery'], ['GOVT', 'Government'], ['NONPROFIT', 'Non-profit'],
];
const LIMITS = { about: 139, description: 512, address: 256, email: 128 } as const;
type TextKey = keyof typeof LIMITS;

/** The bot number's WhatsApp business profile: what players see when they tap its name. */
export function BusinessProfile({ editable }: { editable: boolean }) {
  const { accessToken } = useAuth();
  const { data, refetch, loading } = useApi<ProfileResult>('/admin/chatbot/profile/');
  const [form, setForm] = useState<Profile | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (data?.profile) setForm({ ...data.profile, websites: [...data.profile.websites, '', ''].slice(0, 2) });
  }, [data]);

  async function save() {
    if (!accessToken || !form || !data?.profile) return;
    // Send only what changed, so an untouched field is never overwritten.
    const body: Record<string, unknown> = {};
    for (const k of Object.keys(LIMITS) as TextKey[]) if (form[k] !== data.profile[k]) body[k] = form[k];
    if (form.vertical !== data.profile.vertical) body.vertical = form.vertical;
    const sites = form.websites.map((w) => w.trim()).filter(Boolean);
    if (sites.join('\n') !== data.profile.websites.join('\n')) body.websites = sites;
    if (!Object.keys(body).length) { setNotice({ tone: 'green', text: 'Nothing changed.' }); return; }
    setBusy('save'); setNotice(null);
    const res = await authedRequest<{ ok: boolean; error?: string }>('PUT', '/admin/chatbot/profile/', accessToken, body);
    setBusy('');
    const out = res.data ?? { ok: false, error: res.error };
    setNotice(out.ok ? { tone: 'green', text: 'Profile saved. WhatsApp shows it within a few minutes.' } : { tone: 'red', text: out.error ?? 'Save failed.' });
    if (out.ok) refetch();
  }

  async function uploadPhoto(file: File) {
    if (!accessToken) return;
    setBusy('photo'); setNotice(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await fetch(`${config.apiUrl}/admin/chatbot/profile/photo/`, {
        method: 'POST', headers: { Authorization: `Bearer ${accessToken}` }, body,
      });
      const json = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string; detail?: string };
      if (json.ok) { setNotice({ tone: 'green', text: 'Photo updated.' }); refetch(); }
      else setNotice({ tone: 'red', text: json.error ?? json.detail ?? `Upload failed (${res.status}).` });
    } catch {
      setNotice({ tone: 'red', text: 'Upload failed. Check your connection and try again.' });
    } finally {
      setBusy('');
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  const text = (k: TextKey) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => f && { ...f, [k]: e.target.value.slice(0, LIMITS[k]) });

  return (
    <Panel title="WhatsApp business profile"
      description="What players see when they tap the bot’s name. The display name itself is changed in Meta’s WhatsApp Manager (Meta reviews it).">
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {loading && !data && <p className="text-sm text-muted-foreground">Loading from Meta…</p>}
      {data && !data.ok && <p className="text-sm text-destructive">✗ Could not load the profile: {data.error}</p>}
      {form && (
        <div className="space-y-5">
          <div className="flex items-center gap-4">
            {form.profile_picture_url
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={form.profile_picture_url} alt="Profile photo" className="h-16 w-16 rounded-full border border-border object-cover" />
              : <div className="flex h-16 w-16 items-center justify-center rounded-full border border-dashed border-border text-xs text-muted-foreground">No photo</div>}
            {editable && (
              <div className="space-y-1">
                <input ref={fileRef} type="file" accept="image/jpeg,image/png" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadPhoto(f); }} />
                <Btn size="sm" busy={busy === 'photo'} onClick={() => fileRef.current?.click()}>Change photo</Btn>
                <p className="text-xs text-muted-foreground">Square JPG or PNG, at least 192×192, under 5 MB. Needs the Meta app ID.</p>
              </div>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="About" hint={`Short line under the name. ${form.about.length}/${LIMITS.about}`}>
              <TextInput value={form.about} disabled={!editable} onChange={text('about')} placeholder="Bet on football from WhatsApp" />
            </Field>
            <Field label="Category">
              <select value={form.vertical} disabled={!editable}
                onChange={(e) => setForm((f) => f && { ...f, vertical: e.target.value })}
                className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm">
                {VERTICALS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </Field>
            <Field label="Description" hint={`${form.description.length}/${LIMITS.description}`}>
              <textarea value={form.description} disabled={!editable} onChange={text('description')} rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            </Field>
            <Field label="Address" hint={`${form.address.length}/${LIMITS.address}`}>
              <textarea value={form.address} disabled={!editable} onChange={text('address')} rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            </Field>
            <Field label="Email">
              <TextInput type="email" value={form.email} disabled={!editable} onChange={text('email')} placeholder="support@example.com" />
            </Field>
            <Field label="Websites" hint="Up to 2, starting with https://">
              <div className="space-y-2">
                {form.websites.map((w, i) => (
                  <TextInput key={i} value={w} disabled={!editable} placeholder="https://"
                    onChange={(e) => setForm((f) => f && { ...f, websites: f.websites.map((x, j) => (j === i ? e.target.value : x)) })} />
                ))}
              </div>
            </Field>
          </div>
          {editable
            ? <Btn variant="primary" busy={busy === 'save'} onClick={save}>Save profile</Btn>
            : <Badge tone="slate">Only a superuser can change the profile</Badge>}
        </div>
      )}
    </Panel>
  );
}
