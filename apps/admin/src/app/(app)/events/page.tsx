'use client';

import { useState } from 'react';
import { FaCalendarAlt } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Button } from '@slyk/ui/components/button';
import { Input } from '@slyk/ui/components/input';
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
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
            <FaCalendarAlt size={13} />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Events</h1>
            <p className="text-muted-foreground text-sm">Manage sportsbook events and odds.</p>
          </div>
        </div>
        <Button
          onClick={() => setShowForm((v) => !v)}
          className={showForm ? '' : 'bg-gradient-to-br from-gold to-gold/70 text-[#1A1538] hover:opacity-90'}
        >
          {showForm ? 'Cancel' : '+ New event'}
        </Button>
      </div>

      {showForm && (
        <Card className="rounded-2xl border-gold/15">
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
                  <Input
                    type={type}
                    required
                    value={form[key as keyof typeof form]}
                    onChange={(e) => set(key, e.target.value)}
                    placeholder={placeholder}
                    step={type === 'number' ? '0.01' : undefined}
                  />
                </div>
              ))}
              {formError && <p className="col-span-2 text-sm text-red-500">{formError}</p>}
              <div className="col-span-2">
                <Button type="submit" disabled={saving}>
                  {saving ? 'Creating…' : 'Create event'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-2xl border-gold/15">
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
                        <Button size="sm" variant="outline" onClick={() => handleSuspend(ev)}>
                          {ev.status === 'suspended' ? 'Reopen' : 'Suspend'}
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => handleDelete(ev.id)}>
                          Delete
                        </Button>
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
