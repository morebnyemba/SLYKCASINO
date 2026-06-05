import type { Metadata } from 'next';
import { LiveFeed } from '@/components/live-feed';

export const metadata: Metadata = { title: 'Live Chat — SLYK' };

export default function PlayerLiveChatPage() {
  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">Live Chat</h1>
      <p className="mb-4 text-muted-foreground">Chat with support and other players in real time over the Erlang WebSocket engine.</p>
      <LiveFeed channel="chat:lobby" title="Lobby Chat" height={360} />
    </div>
  );
}
