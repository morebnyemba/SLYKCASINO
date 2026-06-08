import { StatCard } from '@/components/stat-card';
import { RealtimeFeed } from '@/components/realtime-feed';
import { apiGet } from '@/lib/config';

interface Stats {
  online_players?: number;
  open_bets?: number;
  active_promotions?: number;
  open_chats?: number;
}

export default async function OverviewPage() {
  const stats = (await apiGet<Stats>('/admin/stats/')) as Stats;
  return (
    <div>
      <h1 className="text-2xl font-bold">Command Center</h1>
      <p className="mb-5 text-muted-foreground">Live operational overview. Figures from Django; feeds from the Erlang engine.</p>
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Online players" value={stats.online_players ?? '—'} hint="realtime" />
        <StatCard label="Open bets" value={stats.open_bets ?? '—'} />
        <StatCard label="Active promos" value={stats.active_promotions ?? '—'} />
        <StatCard label="Open chats" value={stats.open_chats ?? '—'} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <RealtimeFeed channel="admin:bets" title="Live Bet Stream" height={260} />
        <RealtimeFeed channel="admin:chat" title="Incoming Chats" height={260} />
      </div>
    </div>
  );
}
