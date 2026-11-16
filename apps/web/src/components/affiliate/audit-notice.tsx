'use client';

import { useEffect, useState } from 'react';
import { FaCircleCheck, FaScaleBalanced, FaXmark } from 'react-icons/fa6';
import { HonestNumbers, type AuditEconomics } from './honest-numbers';

export interface AuditNoticeData {
  audited_on: string;
  affected: boolean;
  turnover_multiple: string;
  min_deposit: string;
  reversed_total: string;
  from_wallet: string;
  from_balance: string;
  still_owed: string;
  restored_total?: string;
  restored_count?: number;
  restored_percent?: string;
  economics?: AuditEconomics;
  items: { customer: string; earned_on: string; paid: string; kept: string; reversed: string; reason: string }[];
}

const money = (v: string | number) =>
  `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const date = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

/** Tells every agent about the deposit-commission audit; affected agents see
 *  exactly what was reversed and how it was recovered. Unaffected agents can
 *  dismiss it; it stays for affected agents until the server stops sending it. */
export function AuditNotice({ n }: { n: AuditNoticeData }) {
  const key = `cpa-audit-dismissed:${n.audited_on}`;
  const [hidden, setHidden] = useState(true);
  useEffect(() => {
    let dismissed = false;
    try { dismissed = window.localStorage.getItem(key) === '1'; } catch { /* storage blocked: show it */ }
    setHidden(!n.affected && dismissed);
  }, [key, n.affected]);
  if (hidden) return null;

  const dismiss = () => {
    try { window.localStorage.setItem(key, '1'); } catch { /* ignore */ }
    setHidden(true);
  };
  const multiple = Number(n.turnover_multiple);
  const rules = (
    <ul className="mt-2 list-disc space-y-0.5 pl-5">
      {Number(n.min_deposit) > 0 && <li>deposit at least {money(n.min_deposit)}</li>}
      <li>bet at least {multiple}× their first deposit with their own money (bonus money doesn’t count)</li>
      <li>not share a payment number with your account</li>
    </ul>
  );

  return (
    <section
      role="status"
      className={`relative rounded-2xl border p-4 text-sm sm:p-5 ${n.affected ? 'border-gold/40 bg-gold/10' : 'border-border bg-card'}`}
    >
      {!n.affected && (
        <button onClick={dismiss} aria-label="Dismiss" className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:text-foreground">
          <FaXmark size={14} />
        </button>
      )}
      <div className="flex items-start gap-3 pr-6">
        <span className={`mt-0.5 shrink-0 ${n.affected ? 'text-gold' : 'text-win'}`}>
          {n.affected ? <FaScaleBalanced size={18} /> : <FaCircleCheck size={18} />}
        </span>
        <div className="min-w-0 space-y-2">
          <p className="font-bold">Commission audit · {date(n.audited_on)}</p>
          <p className="text-muted-foreground">
            We checked every new-customer (deposit) commission paid since the agent programme started. A customer earns you
            this commission only once they:
          </p>
          <div className="text-muted-foreground">{rules}</div>
          {n.economics && <HonestNumbers e={n.economics} />}
          {!n.affected ? (
            <p className="font-semibold text-foreground">All your commissions passed. Nothing on your account has changed.</p>
          ) : (
            <>
              {Number(n.restored_total ?? 0) > 0 && (
                <p className="rounded-xl bg-win/10 px-3 py-2 text-foreground">
                  Good news: we’ve given back <b>{money(n.restored_total!)}</b> ({n.restored_count} commission
                  {n.restored_count === 1 ? '' : 's'}): those customers met the rules in force when you were paid, so we’ve
                  restored {n.restored_percent ? `${Number(n.restored_percent)}%` : 'part'} of their first deposit. It’s back in
                  your agent wallet.
                </p>
              )}
              {n.items.length > 0 && (
                <p className="text-foreground">
                  These commissions were paid for customers who hadn’t played their deposit through with their own money (an
                  earlier version of our system counted bonus money), so they stay reversed: <b>{money(n.reversed_total)}</b>.
                </p>
              )}
              {n.items.length > 0 && <ul className="divide-y divide-border rounded-xl border border-border bg-card">
                {n.items.map((it, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <p className="font-semibold">{it.customer} · earned {date(it.earned_on)}</p>
                      <p className="text-xs text-muted-foreground">Why: {it.reason}</p>
                    </div>
                    <div className="shrink-0 text-right tabular-nums">
                      <p className="font-bold">−{money(it.reversed)}</p>
                      <p className="text-xs text-muted-foreground">
                        was {money(it.paid)}{Number(it.kept) > 0 && `, you keep ${money(it.kept)}`}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>}
              {n.items.length > 0 && <p className="text-muted-foreground">
                How it was recovered:
                {Number(n.from_balance) > 0 && <> {money(n.from_balance)} from your agent wallet before it was paid out;</>}
                {Number(n.from_wallet) > 0 && <> {money(n.from_wallet)} from your Winnings wallet;</>}
                {Number(n.still_owed) > 0
                  ? <> the remaining <b className="text-foreground">{money(n.still_owed)}</b> will come off your next commissions.</>
                  : <> nothing more is owed.</>}
              </p>}
              <p className="text-muted-foreground">
                Your lost-ticket and net-loss commissions are not affected. If you think we got a customer wrong, contact support
                and we’ll review it.
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
