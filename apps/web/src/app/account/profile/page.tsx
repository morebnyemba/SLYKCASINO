'use client';

import { FaCrown, FaMedal } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Me {
  username?: string;
  email?: string;
  kyc_status?: string;
  balance?: string;
  currency?: string;
  avatar_url?: string;
  loyalty_tier?: string;
}

interface Stats {
  bets: { count: number; won: number; total_staked: string; total_payout: string };
  casino: { count: number; total_staked: string; total_win: string };
}

const KYC_LABEL: Record<string, string> = {
  unverified: 'Unverified',
  pending: 'Pending review',
  verified: 'Verified',
};

const TIER_STYLE: Record<string, string> = {
  bronze: 'bg-amber-700/10 text-amber-700',
  silver: 'bg-slate-400/10 text-slate-500',
  gold: 'bg-gold/10 text-gold',
};

export default function ProfilePage() {
  const { data: me, loading, error } = useApi<Me>('/players/me/');
  const { data: stats } = useApi<Stats>('/players/me/stats/');

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  const tier = me?.loyalty_tier ?? 'bronze';

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Card>
        <CardContent className="pt-6">
          <div className="mb-4 flex items-center gap-4">
            {me?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={me.avatar_url} alt={me.username} className="h-16 w-16 rounded-full object-cover" />
            ) : (
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold text-primary">
                {me?.username?.[0]?.toUpperCase() ?? '?'}
              </span>
            )}
            <div>
              <p className="text-lg font-semibold">{me?.username || '—'}</p>
              <Badge className={`mt-1 capitalize ${TIER_STYLE[tier] ?? TIER_STYLE.bronze}`} variant="secondary">
                {tier === 'gold' ? <FaCrown className="mr-1 inline" size={11} /> : <FaMedal className="mr-1 inline" size={11} />}
                {tier} tier
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-[120px_1fr] gap-2 text-sm">
            <span className="text-muted-foreground">Email</span>
            <span>{me?.email || '—'}</span>
            <span className="text-muted-foreground">KYC status</span>
            <span>{KYC_LABEL[me?.kyc_status ?? ''] ?? me?.kyc_status ?? 'Unverified'}</span>
            <span className="text-muted-foreground">Balance</span>
            <span className="font-medium">{me?.balance ?? '0.00'} {me?.currency ?? 'USD'}</span>
          </div>
        </CardContent>
      </Card>

      {stats && (
        <div className="mt-6">
          <h2 className="mb-3 text-lg font-semibold">Lifetime stats</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-4">
              <p className="text-xs text-muted-foreground">Bets placed</p>
              <p className="text-lg font-bold">{stats.bets.count}</p>
              <p className="text-xs text-muted-foreground">{stats.bets.won} won</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-muted-foreground">Sportsbook staked</p>
              <p className="text-lg font-bold">{stats.bets.total_staked}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-muted-foreground">Casino rounds</p>
              <p className="text-lg font-bold">{stats.casino.count}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-muted-foreground">Casino won</p>
              <p className="text-lg font-bold text-green-600">{stats.casino.total_win}</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
