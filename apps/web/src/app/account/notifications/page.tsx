'use client';

import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';

interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
}

const KIND_LABEL: Record<string, string> = {
  bet_won: 'Bet won',
  bet_lost: 'Bet lost',
  deposit_confirmed: 'Deposit',
  withdrawal_processed: 'Withdrawal',
  bonus_credited: 'Bonus',
  promo_expiring: 'Promotion',
  account_alert: 'Account',
};

export default function NotificationsPage() {
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<Notification[]>('/notifications/');
  const notifications = data ?? [];

  async function markRead(id: number) {
    if (!accessToken) return;
    await authedPost(`/notifications/${id}/read/`, {}, accessToken);
    refetch();
  }

  async function markAllRead() {
    if (!accessToken) return;
    await authedPost('/notifications/read-all/', {}, accessToken);
    refetch();
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Notifications</h1>
        {notifications.some((n) => !n.read) && (
          <button
            onClick={markAllRead}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent"
          >
            Mark all read
          </button>
        )}
      </div>

      <div className="space-y-2">
        {notifications.length === 0 && (
          <p className="text-sm text-muted-foreground">No notifications yet.</p>
        )}
        {notifications.map((n) => (
          <Card key={n.id} className={n.read ? 'opacity-60' : ''}>
            <CardContent className="flex items-start justify-between gap-3 pt-4">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant="secondary">{KIND_LABEL[n.kind] ?? n.kind}</Badge>
                  {!n.read && <span className="h-2 w-2 rounded-full bg-secondary" />}
                </div>
                <p className="text-sm font-medium">{n.title}</p>
                {n.body && <p className="text-sm text-muted-foreground">{n.body}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  {new Date(n.created_at).toLocaleString()}
                </p>
              </div>
              {!n.read && (
                <button
                  onClick={() => markRead(n.id)}
                  className="shrink-0 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
                >
                  Mark read
                </button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
