'use client';

import { useState } from 'react';
import { FaWallet, FaGift, FaCoins } from 'react-icons/fa6';
import type { IconType } from 'react-icons';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
interface Promo {
  id: number;
  name: string;
  kind: string;
  active: boolean;
  bonus_amount: string;
  wagering_multiplier: string;
  ends_at?: string;
}

interface PromosResponse { results?: Promo[] }

interface Claim {
  id: number;
  promotion: number;
  promotion_name: string;
  bonus_amount: string;
  wagering_required: string;
  wagering_progress: string;
  status: string;
}

interface ClaimsResponse { results?: Claim[] }

const KIND_ICON: Record<string, IconType> = {
  deposit: FaWallet,
  freebet: FaGift,
  cashback: FaCoins,
};

export default function PromotionsPage() {
  const { user, accessToken } = useAuth();
  const { data: promosData, loading: promosLoading } = useApi<PromosResponse>('/promotions/');
  const { data: claimsData, loading: claimsLoading, refetch: refetchClaims } = useApi<ClaimsResponse>(
    user ? '/promotions/my-claims/' : null,
  );

  const promos = promosData?.results ?? [];
  const claims = claimsData?.results ?? [];
  const claimedIds = new Set(claims.map((c) => c.promotion));

  const [claiming, setClaiming] = useState<number | null>(null);
  const [messages, setMessages] = useState<Record<number, string>>({});

  async function handleClaim(promoId: number) {
    if (!accessToken) return;
    setClaiming(promoId);
    const { error } = await authedPost(`/promotions/${promoId}/claim/`, {}, accessToken);
    setMessages((m) => ({ ...m, [promoId]: error ? error : 'Bonus claimed.' }));
    setClaiming(null);
    refetchClaims();
  }

  function wageringPct(claim: Claim): number {
    const req = parseFloat(claim.wagering_required);
    if (req === 0) return 100;
    return Math.min(100, (parseFloat(claim.wagering_progress) / req) * 100);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Promotions</h1>
        <p className="text-muted-foreground">Claim a bonus and start playing.</p>
      </div>

      {/* Available promotions */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {promosLoading && <p className="text-sm text-muted-foreground col-span-3">Loading promotions…</p>}
        {!promosLoading && promos.length === 0 && (
          <p className="text-sm text-muted-foreground col-span-3">No active promotions right now. Check back soon.</p>
        )}
        {promos.map((p) => {
          const claimed = claimedIds.has(p.id);
          const msg = messages[p.id];
          const Icon = KIND_ICON[p.kind] ?? FaGift;
          return (
            <Card key={p.id} className={claimed ? 'opacity-70' : ''}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary/10 text-secondary">
                    <Icon size={16} />
                  </span>
                  <Badge variant={p.active ? 'default' : 'secondary'}>{p.active ? 'Active' : 'Off'}</Badge>
                </div>
                <CardTitle className="text-base">{p.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-1 text-sm">
                  <span className="text-muted-foreground">Bonus</span>
                  <span className="font-medium">{p.bonus_amount}</span>
                  <span className="text-muted-foreground">Wagering</span>
                  <span>{p.wagering_multiplier}×</span>
                  {p.ends_at && (
                    <>
                      <span className="text-muted-foreground">Expires</span>
                      <span>{new Date(p.ends_at).toLocaleDateString()}</span>
                    </>
                  )}
                </div>

                {msg && <p className="text-sm text-muted-foreground">{msg}</p>}

                {user ? (
                  claimed ? (
                    <p className="text-sm text-green-600 font-medium">Already claimed</p>
                  ) : (
                    <button
                      onClick={() => handleClaim(p.id)}
                      disabled={claiming === p.id}
                      className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                    >
                      {claiming === p.id ? 'Claiming…' : 'Claim bonus'}
                    </button>
                  )
                ) : (
                  <a
                    href="/login"
                    className="block w-full rounded-md border border-primary px-4 py-2 text-center text-sm font-medium text-primary hover:bg-primary/10"
                  >
                    Log in to claim
                  </a>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* My active claims */}
      {user && claims.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">My bonuses</h2>
          <div className="space-y-3">
            {claims.map((c) => {
              const pct = wageringPct(c);
              return (
                <Card key={c.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-medium">{c.promotion_name}</p>
                      <Badge variant={c.status === 'completed' ? 'default' : c.status === 'active' ? 'secondary' : 'destructive'}>
                        {c.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">
                      Wagering: {c.wagering_progress} / {c.wagering_required}
                    </p>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
