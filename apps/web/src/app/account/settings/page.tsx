'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';



interface RGSettings {
  deposit_limit_daily: string | null;
  self_excluded: boolean;
  exclusion_ends_at: string | null;
}

export default function SettingsPage() {
  const { accessToken, logout } = useAuth();

  // GDPR state
  const [exportLoading, setExportLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);

  const handleExport = async () => {
    if (!accessToken) return;
    setExportLoading(true);
    try {
      const res = await fetch(`${config.apiUrl}/players/me/export/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'my-slyk-data.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert('Failed to export data. Please try again.');
    } finally {
      setExportLoading(false);
    }
  };

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeleteError('');
    setDeleteLoading(true);
    try {
      const res = await fetch(`${config.apiUrl}/players/me/delete/`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken ?? ''}` },
        body: JSON.stringify({ password: deletePassword }),
      });
      if (res.ok) {
        logout();
        window.location.href = '/';
      } else {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setDeleteError(data.detail || 'Incorrect password or request failed.');
      }
    } catch {
      setDeleteError('Network error. Please try again.');
    } finally {
      setDeleteLoading(false);
    }
  };
  const { data: rg, loading, refetch } = useApi<RGSettings>('/players/me/rg/');

  const [limitInput, setLimitInput] = useState('');
  const [limitMsg, setLimitMsg] = useState('');
  const [limitBusy, setLimitBusy] = useState(false);

  const [excludeDays, setExcludeDays] = useState('30');
  const [excludeMsg, setExcludeMsg] = useState('');
  const [excludeBusy, setExcludeBusy] = useState(false);
  const [confirmExclude, setConfirmExclude] = useState(false);

  // Pre-fill current limit when data arrives
  useEffect(() => {
    if (rg?.deposit_limit_daily) setLimitInput(rg.deposit_limit_daily);
  }, [rg?.deposit_limit_daily]);

  async function saveLimit() {
    if (!accessToken) return;
    setLimitBusy(true); setLimitMsg('');
    const res = await fetch(`${config.apiUrl}/players/me/rg/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ deposit_limit_daily: limitInput || null }),
    });
    const json = await res.json();
    setLimitMsg(res.ok ? 'Deposit limit saved.' : (json.detail ?? 'Failed'));
    setLimitBusy(false);
    refetch();
  }

  async function removeLimit() {
    if (!accessToken) return;
    setLimitBusy(true); setLimitMsg('');
    const res = await fetch(`${config.apiUrl}/players/me/rg/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ deposit_limit_daily: null }),
    });
    setLimitMsg(res.ok ? 'Deposit limit removed' : 'Failed');
    setLimitInput('');
    setLimitBusy(false);
    refetch();
  }

  async function selfExclude() {
    if (!accessToken || !confirmExclude) return;
    setExcludeBusy(true); setExcludeMsg('');
    const days = excludeDays === 'indefinite' ? null : parseInt(excludeDays);
    const { error } = await authedPost('/players/me/self-exclude/', { days }, accessToken);
    setExcludeMsg(error ?? 'Self-exclusion applied. Contact support to discuss reinstatement.');
    setConfirmExclude(false);
    setExcludeBusy(false);
    refetch();
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Responsible Gambling</h1>
      <p className="text-sm text-muted-foreground">
        These controls help you manage your gaming activity. Changes take effect immediately.
        If you need help, contact{' '}
        <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
          BeGambleAware
        </a>.
      </p>

      {/* Self-exclusion status banner */}
      {rg?.self_excluded && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <p className="font-semibold text-destructive">Your account is self-excluded</p>
          <p className="text-sm text-muted-foreground mt-1">
            {rg.exclusion_ends_at
              ? `Active until ${new Date(rg.exclusion_ends_at).toLocaleDateString()}`
              : 'Exclusion is indefinite. Contact support to discuss reinstatement.'}
          </p>
        </div>
      )}

      {/* Deposit limits */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Daily deposit limit</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Set the maximum amount you can deposit in a single day.
            {rg?.deposit_limit_daily && (
              <> Current limit: <span className="font-medium text-foreground">{rg.deposit_limit_daily}</span></>
            )}
            {!rg?.deposit_limit_daily && ' No limit currently set.'}
          </p>
          <div className="flex gap-2">
            <input
              type="number"
              value={limitInput}
              onChange={(e) => setLimitInput(e.target.value)}
              placeholder="e.g. 100"
              min="1"
              className="w-32 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              onClick={saveLimit}
              disabled={limitBusy || !limitInput}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {limitBusy ? 'Saving…' : 'Set limit'}
            </button>
            {rg?.deposit_limit_daily && (
              <button
                onClick={removeLimit}
                disabled={limitBusy}
                className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent disabled:opacity-50"
              >
                Remove
              </button>
            )}
          </div>
          {limitMsg && <p className="text-sm text-muted-foreground">{limitMsg}</p>}
        </CardContent>
      </Card>

      {/* Self-exclusion */}
      {!rg?.self_excluded && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Self-exclusion</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Self-exclusion prevents you from depositing, betting, or playing casino games
              for the chosen period. This cannot be reversed during the exclusion period.
            </p>
            <div className="flex flex-wrap gap-2">
              {['7', '30', '90', '180', '365', 'indefinite'].map((d) => (
                <button
                  key={d}
                  onClick={() => setExcludeDays(d)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${excludeDays === d ? 'bg-destructive text-white' : 'bg-muted hover:bg-accent'}`}
                >
                  {d === 'indefinite' ? 'Indefinite' : `${d} days`}
                </button>
              ))}
            </div>
            {!confirmExclude ? (
              <button
                onClick={() => setConfirmExclude(true)}
                className="rounded-md border border-destructive px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10"
              >
                Exclude myself
              </button>
            ) : (
              <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 space-y-3">
                <p className="text-sm font-medium">
                  Are you sure? You will be excluded for{' '}
                  {excludeDays === 'indefinite' ? 'an indefinite period' : `${excludeDays} days`}.
                  Deposits and gambling will be blocked immediately.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={selfExclude}
                    disabled={excludeBusy}
                    className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                  >
                    {excludeBusy ? 'Applying…' : 'Yes, exclude me'}
                  </button>
                  <button
                    onClick={() => setConfirmExclude(false)}
                    className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {excludeMsg && <p className="text-sm text-muted-foreground">{excludeMsg}</p>}
          </CardContent>
        </Card>
      )}

      {/* GDPR / Your data */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your data</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground mb-2">
              Download a copy of all your personal data (GDPR data export).
            </p>
            <button
              onClick={handleExport}
              disabled={exportLoading}
              className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent disabled:opacity-50"
            >
              {exportLoading ? 'Preparing…' : 'Export my data'}
            </button>
          </div>
          <div className="border-t border-border pt-4">
            <p className="text-sm text-muted-foreground mb-2">
              Permanently delete your account and all associated data. This cannot be undone.
            </p>
            {!showDeleteConfirm ? (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="rounded-md border border-destructive px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/10"
              >
                Delete my account
              </button>
            ) : (
              <form onSubmit={handleDeleteAccount} className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 space-y-3">
                <p className="text-sm font-medium">Enter your password to confirm account deletion.</p>
                {deleteError && <p className="text-sm text-red-500">{deleteError}</p>}
                <input
                  type="password"
                  required
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  placeholder="Your current password"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={deleteLoading}
                    className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                  >
                    {deleteLoading ? 'Deleting…' : 'Confirm delete'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowDeleteConfirm(false); setDeleteError(''); setDeletePassword(''); }}
                    className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </CardContent>
      </Card>

      {/* External resources */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Need help?</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 text-sm">
            {[
              { name: 'BeGambleAware', url: 'https://www.begambleaware.org' },
              { name: 'GamCare', url: 'https://www.gamcare.org.uk' },
              { name: 'Gambling Therapy', url: 'https://www.gamblingtherapy.org' },
            ].map((r) => (
              <a
                key={r.name}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-md border border-border px-4 py-2 hover:bg-accent"
              >
                <span>{r.name}</span>
                <span className="text-muted-foreground">→</span>
              </a>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
