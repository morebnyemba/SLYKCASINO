'use client';

import { useEffect, useState } from 'react';
import { Badge, Btn, Field, Notice, Panel, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Announcement {
  enabled: boolean; title: string; message: string; tone: 'info' | 'warning';
  show_withdraw_button: boolean; show_support_button: boolean; updated_at: string | null;
}

/** The notice bar across the top of every page of the player site. */
export function AnnouncementEditor() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Announcement>('/admin/announcement/');
  const [form, setForm] = useState<Announcement | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);

  async function save(patch: Partial<Announcement> = {}) {
    if (!accessToken || !form) return;
    setBusy(true);
    const res = await authedRequest('PUT', '/admin/announcement/', accessToken, { ...form, ...patch });
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Saved — players see it on their next page load.' });
    refetch();
  }

  const set = <K extends keyof Announcement>(k: K, v: Announcement[K]) => setForm((f) => f && { ...f, [k]: v });
  const check = 'h-4 w-4 accent-[hsl(var(--secondary))]';
  return (
    <Panel title="Site notice" description="A bar across the top of every page of the player site — for service updates such as withdrawals. Players can close it; it reappears when you change it."
      actions={data && <Badge tone={data.enabled ? 'green' : 'slate'} dot>{data.enabled ? 'Showing' : 'Off'}</Badge>}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {form && (
        <div className="space-y-4">
          <Field label="Title (optional)"><TextInput value={form.title} maxLength={80} onChange={(e) => set('title', e.target.value)} /></Field>
          <Field label="Message">
            <textarea value={form.message} maxLength={600} rows={3} onChange={(e) => set('message', e.target.value)}
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm" />
          </Field>
          <div className="flex flex-wrap gap-5 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" className={check} checked={form.show_withdraw_button} onChange={(e) => set('show_withdraw_button', e.target.checked)} /> “Request withdrawal” button</label>
            <label className="flex items-center gap-2"><input type="checkbox" className={check} checked={form.show_support_button} onChange={(e) => set('show_support_button', e.target.checked)} /> “Contact support” button (opens the chat)</label>
            <label className="flex items-center gap-2"><input type="checkbox" className={check} checked={form.tone === 'warning'} onChange={(e) => set('tone', e.target.checked ? 'warning' : 'info')} /> Highlight as important</label>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {data?.enabled
              ? <Btn variant="danger" busy={busy} onClick={() => save({ enabled: false })}>Hide notice</Btn>
              : <Btn variant="success" busy={busy} onClick={() => save({ enabled: true })}>Show notice</Btn>}
            <Btn variant="primary" busy={busy} onClick={() => save()}>Save</Btn>
          </div>
        </div>
      )}
    </Panel>
  );
}
