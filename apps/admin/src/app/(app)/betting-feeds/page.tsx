import type { Metadata } from 'next';
import { RealtimeFeed } from '@/components/realtime-feed';

export const metadata: Metadata = { title: 'Betting Feeds — SLYK Admin' };

export default function BettingFeedsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Live Betting Feeds</h1>
      <p className="mb-5 text-muted-foreground">Monitor incoming bets and odds movements across markets as they happen.</p>
      <div className="grid gap-5 lg:grid-cols-2">
        <RealtimeFeed channel="admin:bets" title="Bet Placements" />
        <RealtimeFeed channel="odds" title="Odds Movements" />
      </div>
    </div>
  );
}
