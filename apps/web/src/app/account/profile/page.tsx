'use client';

import Link from 'next/link';
import { FaCrown, FaMedal, FaEnvelope, FaCheckCircle, FaWallet, FaTicketAlt, FaDice } from 'react-icons/fa';
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
  bronze: 'bg-tier-bronze/10 text-tier-bronze',
  silver: 'bg-tier-silver/10 text-tier-silver',
  gold: 'bg-tier-gold/10 text-tier-gold',
};

export default function ProfilePage() {
  const { data: me, loading, error } = useApi<Me>('/players/me/');
  const { data: stats } = useApi<Stats>('/players/me/stats/');

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  const tier = me?.loyalty_tier ?? 'bronze';
  const verified = me?.kyc_status === 'verified';

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Card className="overflow-hidden rounded-2xl border-gold/20">
        <div className="bg-gradient-to-br from-primary via-primary to-secondary/80 px-6 py-7">
          <div className="flex items-center gap-4">
            {me?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={me.avatar_url}
                alt={me.username}
                className="h-16 w-16 rounded-full object-cover ring-2 ring-gold/60"
              />
            ) : (
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-gold to-gold/70 text-2xl font-bold text-gold-foreground shadow-inner shadow-black/10 ring-2 ring-gold/40">
                {me?.username?.[0]?.toUpperCase() ?? '?'}
              </span>
            )}
            <div>
              <p className="text-lg font-semibold text-white">{me?.username || '—'}</p>
              <Badge className={`mt-1.5 capitalize ${TIER_STYLE[tier] ?? TIER_STYLE.bronze}`} variant="secondary">
                {tier === 'gold' ? <FaCrown className="mr-1 inline" size={11} /> : <FaMedal className="mr-1 inline" size={11} />}
                {tier} tier
              </Badge>
            </div>
          </div>
        </div>
        <CardContent className="pt-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-chip text-secondary">
                <FaEnvelope size={13} />
              </span>
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">Email</p>
                <p className="truncate text-sm font-medium">{me?.email || '—'}</p>
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${verified ? 'bg-win/15 text-win' : 'bg-chip text-secondary'}`}>
                <FaCheckCircle size={13} />
              </span>
              <div>
                <p className="text-xs text-muted-foreground">KYC status</p>
                {verified ? (
                  <p className="text-sm font-medium">{KYC_LABEL[me?.kyc_status ?? ''] ?? me?.kyc_status ?? 'Unverified'}</p>
                ) : (
                  <Link href="/account/verification" className="text-sm font-medium text-gold hover:underline">
                    {KYC_LABEL[me?.kyc_status ?? ''] ?? me?.kyc_status ?? 'Unverified'} — verify now
                  </Link>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gold/15 text-gold">
                <FaWallet size={13} />
              </span>
              <div>
                <p className="text-xs text-muted-foreground">Balance</p>
                <p className="text-sm font-semibold">{me?.balance ?? '0.00'} {me?.currency ?? 'USD'}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {stats && (
        <div className="mt-6">
          <h2 className="mb-3 text-lg font-semibold">Lifetime stats</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="rounded-xl border-gold/10 p-4">
              <FaTicketAlt className="mb-2 text-secondary" size={16} />
              <p className="text-xs text-muted-foreground">Bets placed</p>
              <p className="text-lg font-bold">{stats.bets.count}</p>
              <p className="text-xs text-muted-foreground">{stats.bets.won} won</p>
            </Card>
            <Card className="rounded-xl border-gold/10 p-4">
              <FaWallet className="mb-2 text-secondary" size={16} />
              <p className="text-xs text-muted-foreground">Sportsbook staked</p>
              <p className="text-lg font-bold">{stats.bets.total_staked}</p>
            </Card>
            <Card className="rounded-xl border-gold/10 p-4">
              <FaDice className="mb-2 text-secondary" size={16} />
              <p className="text-xs text-muted-foreground">Casino rounds</p>
              <p className="text-lg font-bold">{stats.casino.count}</p>
            </Card>
            <Card className="rounded-xl border-gold/10 p-4">
              <FaCrown className="mb-2 text-gold" size={16} />
              <p className="text-xs text-muted-foreground">Casino won</p>
              <p className="text-lg font-bold text-win">{stats.casino.total_win}</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
