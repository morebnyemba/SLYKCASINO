import type { Metadata } from 'next';
import { RealtimeFeed } from '@/components/realtime-feed';

export const metadata: Metadata = { title: 'Live Chat Console — SLYK Admin' };

export default function LiveChatConsolePage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Live Chat Console</h1>
      <p className="mb-5 text-muted-foreground">Monitor and respond to player conversations in real time.</p>
      <div className="grid gap-5 lg:grid-cols-2">
        <RealtimeFeed channel="chat:lobby" title="Lobby" />
        <RealtimeFeed channel="chat:support" title="Support Queue" />
      </div>
    </div>
  );
}
