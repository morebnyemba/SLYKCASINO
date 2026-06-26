'use client';

import { FaUsers, FaTicketAlt, FaGift, FaRegCommentDots } from 'react-icons/fa';
import { StatCard } from '@/components/stat-card';
import { RealtimeFeed } from '@/components/realtime-feed';
import { useApi } from '@/lib/use-api';

interface Stats {
  online_players?: number;
  open_bets?: number;
  active_promotions?: number;
  open_chats?: number;
}

export default function OverviewPage() {
  const { data: stats, loading } = useApi<Stats>('/admin/stats/');

  return (
    <div>
      <h1 className="text-2xl font-bold">Command Center</h1>
      <p className="mb-5 text-muted-foreground">Live operational overview. Figures from Django; feeds from the Erlang engine.</p>
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={FaUsers} label="Online players" value={loading ? '…' : (stats?.online_players ?? '—')} hint="realtime" />
        <StatCard icon={FaTicketAlt} label="Open bets" value={loading ? '…' : (stats?.open_bets ?? '—')} />
        <StatCard icon={FaGift} label="Active promos" value={loading ? '…' : (stats?.active_promotions ?? '—')} />
        <StatCard icon={FaRegCommentDots} label="Open chats" value={loading ? '…' : (stats?.open_chats ?? '—')} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <RealtimeFeed channel="admin:bets" title="Live Bet Stream" height={260} />
        <RealtimeFeed channel="admin:chat" title="Incoming Chats" height={260} />
      </div>
    </div>
  );
}
