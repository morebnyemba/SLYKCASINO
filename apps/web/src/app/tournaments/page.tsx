'use client';

import { useCallback, useEffect, useState } from 'react';
import { FaTrophy, FaUsers } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Tournament {
  id: number;
  name: string;
  description: string;
  metric: string;
  prize_pool: string;
  currency: string;
  active: boolean;
  is_live: boolean;
  starts_at: string | null;
  ends_at: string | null;
  entry_count: number;
}

interface Entry {
  id: number;
  player_name: string;
  score: string;
  updated_at: string;
}

function timeLeft(endsAt: string | null): string {
  if (!endsAt) return 'Open-ended';
  const diff = new Date(endsAt).getTime() - Date.now();
  if (diff <= 0) return 'Ended';
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  if (days > 0) return `${days}d ${hours}h left`;
  return `${hours}h left`;
}

const RANK_COLORS = ['text-yellow-400', 'text-zinc-300', 'text-amber-600'];

function Leaderboard({ tournamentId, refreshKey }: { tournamentId: number; refreshKey: number }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`${config.apiUrl}/promotions/tournaments/${tournamentId}/leaderboard/`, { cache: 'no-store' });
        if (res.ok && !cancelled) setEntries((await res.json()) as Entry[]);
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    }
    void load();
    return () => { cancelled = true; };
  }, [tournamentId, refreshKey]);

  if (loading) return <p className="px-4 py-3 text-sm text-muted-foreground">Loading leaderboard…</p>;
  if (entries.length === 0) return <p className="px-4 py-3 text-sm text-muted-foreground">No players yet — be the first to join.</p>;

  return (
    <table className="w-full text-sm">
      <tbody>
        {entries.slice(0, 10).map((e, i) => (
          <tr key={e.id} className="border-b border-border last:border-0">
            <td className={`w-10 px-4 py-2 font-mono font-bold ${RANK_COLORS[i] ?? 'text-muted-foreground'}`}>#{i + 1}</td>
            <td className="px-2 py-2 font-medium">{e.player_name || 'Player'}</td>
            <td className="px-4 py-2 text-right font-mono text-muted-foreground">{e.score}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TournamentsPage() {
  const { user, accessToken } = useAuth();
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState<number | null>(null);
  const [messages, setMessages] = useState<Record<number, string>>({});
  const [refreshKey, setRefreshKey] = useState(0);

  const loadTournaments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${config.apiUrl}/promotions/tournaments/`, { cache: 'no-store' });
      if (res.ok) {
        const json = await res.json();
        setTournaments((json.results ?? json) as Tournament[]);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { void loadTournaments(); }, [loadTournaments]);

  async function join(id: number) {
    if (!accessToken) return;
    setJoining(id);
    const { error } = await authedPost(`/promotions/tournaments/${id}/join/`, {}, accessToken);
    setMessages((m) => ({ ...m, [id]: error ? error : 'You\'re in! Your wagering now counts toward this race.' }));
    setJoining(null);
    setRefreshKey((k) => k + 1);
    void loadTournaments();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Tournaments</h1>
        <p className="text-muted-foreground">Join a race, wager to climb the leaderboard, and win a share of the prize pool.</p>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading tournaments…</p>}
      {!loading && tournaments.length === 0 && (
        <p className="text-sm text-muted-foreground">No tournaments running right now. Check back soon.</p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {tournaments.map((t) => {
          const msg = messages[t.id];
          return (
            <Card key={t.id}>
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FaTrophy className="text-gold" size={16} />
                    {t.name}
                  </CardTitle>
                  <Badge variant={t.is_live ? 'default' : 'secondary'}>{t.is_live ? 'Live' : 'Closed'}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">{t.description}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary" className="bg-gold/10 text-gold">
                    Prize pool {t.prize_pool} {t.currency}
                  </Badge>
                  <Badge variant="secondary">{timeLeft(t.ends_at)}</Badge>
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <FaUsers size={11} /> {t.entry_count}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 p-0">
                <div className="border-t border-border">
                  <Leaderboard tournamentId={t.id} refreshKey={refreshKey} />
                </div>
                <div className="px-4 pb-4">
                  {msg && <p className="mb-2 text-sm text-muted-foreground">{msg}</p>}
                  {user ? (
                    <button
                      onClick={() => join(t.id)}
                      disabled={joining === t.id || !t.is_live}
                      className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                    >
                      {joining === t.id ? 'Joining…' : t.is_live ? 'Join tournament' : 'Closed'}
                    </button>
                  ) : (
                    <a
                      href="/login"
                      className="block w-full rounded-md border border-primary px-4 py-2 text-center text-sm font-medium text-primary hover:bg-primary/10"
                    >
                      Log in to join
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
