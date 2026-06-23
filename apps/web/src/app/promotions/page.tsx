'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Carousel, CarouselItem } from '@/components/carousel';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { gameAvatarUrl, CASINO_HERO_IMAGES } from '@/lib/game-images';
import { sanitizeHtml } from '@/lib/sanitize';
interface Promo {
  id: number;
  name: string;
  kind: string;
  active: boolean;
  bonus_amount: string;
  wagering_multiplier: string;
  ends_at?: string;
  code?: string;
  terms_html?: string;
  claim_count?: number;
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

function timeLeft(endsAt: string, now: number): string {
  const diff = new Date(endsAt).getTime() - now;
  if (diff <= 0) return 'Expired';
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  const minutes = Math.floor((diff % 3_600_000) / 60_000);
  if (days > 0) return `${days}d ${hours}h left`;
  if (hours > 0) return `${hours}h ${minutes}m left`;
  return `${minutes}m left`;
}

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
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

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

      {promos.length > 0 && (
        <Carousel>
          {promos.slice(0, 6).map((p, i) => (
            <CarouselItem key={p.id} className="w-[260px] sm:w-[320px]">
              <div className="relative h-32 overflow-hidden rounded-xl sm:h-36">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={CASINO_HERO_IMAGES[i % CASINO_HERO_IMAGES.length]}
                  alt={p.name}
                  className="h-full w-full object-cover"
                />
                <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/75 to-transparent p-3">
                  <p className="font-semibold text-white">{p.name}</p>
                  <p className="text-xs text-white/80">{p.bonus_amount} bonus</p>
                </div>
              </div>
            </CarouselItem>
          ))}
        </Carousel>
      )}

      {/* Available promotions */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {promosLoading && <p className="text-sm text-muted-foreground col-span-3">Loading promotions…</p>}
        {!promosLoading && promos.length === 0 && (
          <p className="text-sm text-muted-foreground col-span-3">No active promotions right now. Check back soon.</p>
        )}
        {promos.map((p) => {
          const claimed = claimedIds.has(p.id);
          const msg = messages[p.id];
          return (
            <Card key={p.id} className={claimed ? 'opacity-70' : ''}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={gameAvatarUrl(`promo-${p.kind}-${p.id}`)}
                    alt={p.kind}
                    className="h-9 w-9 rounded-lg bg-secondary/10 object-cover"
                  />
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
                </div>

                <div className="flex items-center gap-2">
                  {p.ends_at && (
                    <Badge variant="secondary" className="bg-gold/10 text-gold">
                      {timeLeft(p.ends_at, now)}
                    </Badge>
                  )}
                  {typeof p.claim_count === 'number' && p.claim_count > 0 && (
                    <Badge variant="secondary">{p.claim_count} claimed</Badge>
                  )}
                </div>

                {p.code && (
                  <button
                    onClick={() => navigator.clipboard?.writeText(p.code!)}
                    className="w-full rounded-md border border-dashed border-border px-3 py-1.5 text-center font-mono text-sm tracking-wider hover:bg-accent/10"
                    title="Click to copy"
                  >
                    {p.code}
                  </button>
                )}

                {p.terms_html && (
                  <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer select-none">Terms &amp; conditions</summary>
                    <div
                      className="mt-1"
                      suppressHydrationWarning
                      dangerouslySetInnerHTML={{ __html: sanitizeHtml(p.terms_html) }}
                    />
                  </details>
                )}

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
