'use client';

import { useState } from 'react';
import { BsLockFill, BsUnlockFill } from 'react-icons/bs';
import { Btn, Field, Notice, Panel, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface LockStatus {
  locked: boolean; owner: string | null; set_at: string | null; can_manage: boolean; has_access: boolean; unlock_hours: number;
}
const URL = '/admin/revenue-share/lock/';

/** Shows the revenue share only to whoever may open it now: the founder who locked it, or an admin who
 *  entered the password. Everyone else sees the password box. The founder also gets the lock controls. */
export function RevenueLockGate({ children }: { children: React.ReactNode }) {
  const { data, refetch } = useApi<LockStatus>(URL);
  if (!data) return <div className="h-32 animate-pulse rounded-2xl bg-muted/40" />;
  if (data.locked && !data.has_access) return <UnlockForm status={data} onOpened={refetch} />;
  return (
    <>
      {(data.can_manage || data.locked) && <LockPanel status={data} onChanged={refetch} />}
      {children}
    </>
  );
}

function UnlockForm({ status, onOpened }: { status: LockStatus; onOpened: () => void }) {
  const { accessToken } = useAuth();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function open(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost<LockStatus>(`${URL}unlock/`, { password }, accessToken);
    setBusy(false);
    if (res.error) setError(res.error);
    else { setPassword(''); onOpened(); window.location.reload(); }
  }
  return (
    <Panel title="Revenue share is locked">
      <form onSubmit={open} className="max-w-md space-y-4">
        <div className="flex items-start gap-3 text-sm text-muted-foreground">
          <BsLockFill className="mt-0.5 shrink-0 text-gold" size={18} />
          <p>
            <b className="text-foreground">{status.owner ?? 'The founder'}</b> has locked the revenue share. Ask them for the password;
            it opens it for your login for {status.unlock_hours} hours.
          </p>
        </div>
        {error && <Notice tone="red">{error}</Notice>}
        <Field label="Password">
          <TextInput type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Btn variant="primary" busy={busy} disabled={!password} type="submit">Open revenue share</Btn>
      </form>
    </Panel>
  );
}

function LockPanel({ status, onChanged }: { status: LockStatus; onChanged: () => void }) {
  const { accessToken } = useAuth();
  const [mode, setMode] = useState<'' | 'set' | 'remove'>('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [current, setCurrent] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  async function run(method: 'POST' | 'DELETE', body: unknown, ok: string) {
    if (!accessToken) return;
    setBusy(true); setNotice(null);
    const res = await authedRequest(method, URL, accessToken, body);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: ok });
    setMode(''); setPassword(''); setConfirm(''); setCurrent('');
    onChanged();
  }
  async function closeForMe() {
    if (!accessToken) return;
    await authedPost(`${URL}unlock/`, { close: true }, accessToken);
    window.location.reload();
  }

  // An admin who opened it with the password (not the owner): only "lock it again for me".
  if (status.locked && !status.can_manage) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gold/40 bg-gold/10 px-4 py-2.5 text-sm">
        <BsUnlockFill className="text-gold" />
        <span>Opened with {status.owner}’s password for this login.</span>
        <Btn size="sm" onClick={closeForMe}>Lock it again</Btn>
      </div>
    );
  }
  return (
    <Panel title={status.locked ? 'Revenue share is password-locked' : 'Lock the revenue share'}
      description={status.locked
        ? `Only you open it as usual. Every other admin needs the password, which opens it for their login for ${status.unlock_hours} hours. Changing the password closes it for everyone again.`
        : 'Set a password so no other admin, superusers included, can open the revenue share without it. You open it as usual.'}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {mode === '' && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-2 text-sm font-semibold">
            {status.locked ? <><BsLockFill className="text-gold" /> Locked{status.set_at && ` since ${new Date(status.set_at).toLocaleString()}`}</>
              : <><BsUnlockFill className="text-muted-foreground" /> Not locked</>}
          </span>
          <Btn variant="primary" onClick={() => setMode('set')}>{status.locked ? 'Change password' : 'Set a password'}</Btn>
          {status.locked && <Btn onClick={() => setMode('remove')}>Remove lock</Btn>}
        </div>
      )}
      {mode === 'set' && (
        <div className="grid max-w-2xl gap-3 sm:grid-cols-3">
          {status.locked && (
            <Field label="Current password">
              <TextInput type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            </Field>
          )}
          <Field label="New password" hint="At least 8 characters.">
            <TextInput type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Repeat it">
            <TextInput type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <div className="flex items-center gap-2 sm:col-span-3">
            <Btn variant="primary" busy={busy} disabled={password.length < 8 || password !== confirm}
              onClick={() => run('POST', { password, current }, status.locked ? 'Password changed. Everyone else needs the new one.' : 'Locked. Other admins now need the password.')}>
              {status.locked ? 'Change password' : 'Lock it'}
            </Btn>
            <Btn onClick={() => setMode('')}>Cancel</Btn>
            {password && confirm && password !== confirm && <span className="text-xs text-live">The two don’t match.</span>}
          </div>
        </div>
      )}
      {mode === 'remove' && (
        <div className="flex max-w-xl flex-wrap items-end gap-3">
          <Field label="Password" className="w-60">
            <TextInput type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Btn variant="danger" busy={busy} disabled={!current} onClick={() => run('DELETE', { password: current }, 'Lock removed.')}>Remove lock</Btn>
          <Btn onClick={() => setMode('')}>Cancel</Btn>
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        If the password is lost, it can be cleared on the server with <code>manage.py revenue_lock --clear</code>.
      </p>
    </Panel>
  );
}
