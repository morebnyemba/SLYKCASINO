'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Event {
  id: number;
  name: string;
  sport: string;
  home_team: string;
  away_team: string;
  starts_at: string;
  status: string;
  odds_home: string;
  odds_draw: string;
  odds_away: string;
}

interface EventsResponse { results?: Event[] }

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  open: 'default',
  suspended: 'secondary',
  resulted: 'destructive',
};

const BLANK = { name: '', sport: '', home_team: '', away_team: '', starts_at: '', odds_home: '', odds_draw: '', odds_away: '' };

export default function EventsPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<EventsResponse>('/events/');
  const events = data?.results ?? [];

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...BLANK });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setSaving(true);
    setFormError('');
    const { error } = await authedPost('/events/', form, accessToken);
    setSaving(false);
    if (error) { setFormError(error); return; }
    setShowForm(false);
    setForm({ ...BLANK });
    refetch();
  }

  async function handleSuspend(event: Event) {
    if (!accessToken) return;
    const newStatus = event.status === 'suspended' ? 'open' : 'suspended';
    await fetch(`${config.apiUrl}/events/${event.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ status: newStatus }),
    });
    refetch();
  }

  async function handleDelete(id: number) {
    if (!accessToken || !confirm('Delete this event?')) return;
    await fetch(`${config.apiUrl}/events/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    refetch();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Events</h1>
          <p className="text-muted-foreground text-sm">Manage sportsbook events and odds.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? 'Cancel' : '+ New event'}
        </button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">Create event</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
              {[
                { label: 'Name', key: 'name', type: 'text', placeholder: 'Man Utd vs Arsenal' },
                { label: 'Sport', key: 'sport', type: 'text', placeholder: 'football' },
                { label: 'Home team', key: 'home_team', type: 'text', placeholder: 'Man Utd' },
                { label: 'Away team', key: 'away_team', type: 'text', placeholder: 'Arsenal' },
                { label: 'Starts at', key: 'starts_at', type: 'datetime-local', placeholder: '' },
                { label: 'Odds home', key: 'odds_home', type: 'number', placeholder: '1.90' },
                { label: 'Odds draw', key: 'odds_draw', type: 'number', placeholder: '3.50' },
                { label: 'Odds away', key: 'odds_away', type: 'number', placeholder: '4.20' },
              ].map(({ label, key, type, placeholder }) => (
                <div key={key} className="space-y-1">
                  <label className="text-sm font-medium">{label}</label>
                  <input
                    type={type}
                    required
                    value={form[key as keyof typeof form]}
                    onChange={(e) => set(key, e.target.value)}
                    placeholder={placeholder}
                    step={type === 'number' ? '0.01' : undefined}
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
                  {saving ? 'Creating…' : 'Create event'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading events…</p>}
          {!loading && events.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No events. Create one above.</p>
          )}
          {events.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Sport</th>
                  <th className="px-4 py-3 font-medium">Starts</th>
                  <th className="px-4 py-3 font-medium">Odds H/D/A</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium">{ev.home_team} vs {ev.away_team}</td>
                    <td className="px-4 py-3 text-muted-foreground">{ev.sport}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(ev.starts_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {ev.odds_home} / {ev.odds_draw} / {ev.odds_away}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_VARIANT[ev.status] ?? 'secondary'}>{ev.status}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleSuspend(ev)}
                          className="rounded px-2 py-1 text-xs border border-border hover:bg-accent"
                        >
                          {ev.status === 'suspended' ? 'Reopen' : 'Suspend'}
                        </button>
                        <button
                          onClick={() => handleDelete(ev.id)}
                          className="rounded px-2 py-1 text-xs border border-destructive text-destructive hover:bg-destructive/10"
                        >
                          Delete
                        </button>
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
