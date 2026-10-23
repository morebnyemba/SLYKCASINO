'use client';

import { FaGift } from 'react-icons/fa';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';

interface Tier {
  id: number; name: string; min_deposit: string; max_deposit: string | null; percent: string; max_bonus: string;
  wagering_multiplier: string; limit: 'every' | 'daily' | 'once'; ends_at: string | null; used?: boolean;
}
interface Claim {
  id: number; promotion_name: string; promotion_code: string; bonus_amount: string;
  wagering_required: string; wagering_progress: string; status: string; created_at: string;
}

const money = (v: string | number) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const LIMIT: Record<Tier['limit'], string> = { every: 'Every deposit', daily: 'Once a day', once: 'Once per player' };

/** Every running deposit bonus (what each deposit size earns) and the ones this player has received. */
export function DepositBonuses({ onDeposit, showReceived = true }: { onDeposit?: (amount?: number) => void; showReceived?: boolean }) {
  const { accessToken } = useAuth();
  const { data: tierData } = useApi<Tier[]>('/promotions/deposit-bonuses/', { public: !accessToken });
  const { data: claimData } = useApi<Claim[] | { results: Claim[] }>(accessToken && showReceived ? '/promotions/my-claims/' : null);
  const tiers = Array.isArray(tierData) ? tierData : [];
  const claims = (Array.isArray(claimData) ? claimData : claimData?.results ?? [])
    .filter((c) => c.promotion_code?.startsWith('deposit-bonus:'));
  if (tiers.length === 0 && claims.length === 0) return null;

  return (
    <section className="space-y-3 rounded-2xl border border-gold/25 bg-card p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gold/15 text-gold"><FaGift size={15} /></span>
        <div>
          <h2 className="text-base font-bold">Deposit bonuses</h2>
          <p className="text-xs text-muted-foreground">The more you deposit, the bigger the bonus. Added automatically with your deposit.</p>
        </div>
      </div>

      {tiers.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {tiers.map((t) => (
            <li key={t.id} className={`flex flex-col rounded-xl border p-3 ${t.used ? 'border-border opacity-60' : 'border-gold/30 bg-gold/5'}`}>
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-bold">{t.name}</p>
                <p className="text-xl font-extrabold leading-none text-gold">{Number(t.percent)}%</p>
              </div>
              <p className="mt-1 text-sm">
                Deposit {t.max_deposit ? <>{money(t.min_deposit)} – {money(t.max_deposit)}</> : <>{money(t.min_deposit)} or more</>}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {Number(t.max_bonus) > 0 && <>Up to {money(t.max_bonus)} bonus · </>}
                {Number(t.wagering_multiplier) > 0 ? `Bet ${Number(t.wagering_multiplier)}× the bonus to withdraw it` : 'Withdraw any time'}
                {' · '}{LIMIT[t.limit]}
                {t.ends_at && <> · ends {new Date(t.ends_at).toLocaleDateString()}</>}
              </p>
              <div className="mt-auto pt-2">
                {t.used ? (
                  <span className="text-xs font-semibold text-muted-foreground">{t.limit === 'daily' ? 'Used today, back tomorrow' : 'Already used'}</span>
                ) : onDeposit && (
                  <button onClick={() => onDeposit(Number(t.min_deposit))}
                    className="rounded-lg bg-gold px-3 py-1.5 text-xs font-bold text-gold-foreground hover:brightness-110">
                    Deposit {money(t.min_deposit)}{t.max_deposit ? '+' : ' or more'}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {claims.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">Your deposit bonuses</p>
          <ul className="divide-y divide-border">
            {claims.slice(0, 10).map((c) => {
              const need = Number(c.wagering_required), done = Math.min(Number(c.wagering_progress), need);
              const pct = need > 0 ? Math.round((done / need) * 100) : 100;
              return (
                <li key={c.id} className="py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{c.promotion_name}</p>
                      <p className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleDateString()}</p>
                    </div>
                    <p className="shrink-0 font-bold tabular-nums text-gold">+{money(c.bonus_amount)}</p>
                  </div>
                  {need > 0 && (
                    <div className="mt-1.5">
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className={`h-full rounded-full ${pct >= 100 ? 'bg-win' : 'bg-gold'}`} style={{ width: `${pct}%` }} />
                      </div>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {pct >= 100 ? 'Unlocked: yours to withdraw' : `Bet ${money(need - done)} more to unlock (${money(done)} of ${money(need)})`}
                      </p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
