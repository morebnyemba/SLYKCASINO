'use client';

export interface AuditEconomics {
  deposit_percent: string;
  lost_percent: string;
  agent_cents: string;
  example_kept_cents: string;
  example_winnings_cents: string;
  example_fee_cents: string;
  example_result_cents: string;
}

const cents = (v: string | number) => `${Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 1 })}¢`;

/** Why the old terms couldn't last: what an agent earned on a customer's lost
 *  $1, against an illustrative (not real) house margin and payment charge. */
export function HonestNumbers({ e }: { e: AuditEconomics }) {
  const result = Number(e.example_result_cents);
  const row = 'flex items-baseline justify-between gap-3 py-1.5';
  return (
    <details className="group rounded-xl border border-border bg-card">
      <summary className="cursor-pointer list-none px-3 py-2 font-semibold text-foreground">
        Why the rules changed <span className="text-muted-foreground group-open:hidden">▸</span>
      </summary>
      <div className="space-y-3 border-t border-border px-3 py-3 text-muted-foreground">
        <p>
          Take a customer who deposits <b className="text-foreground">$1</b> and loses it. Under the old terms you earned:
        </p>
        <div className="divide-y divide-border rounded-lg border border-border px-3 tabular-nums">
          <div className={row}><span>{e.deposit_percent}% of their first deposit</span><span>{cents(e.deposit_percent)}</span></div>
          <div className={row}><span>{e.lost_percent}% of the $1 they lost</span><span>{cents(e.lost_percent)}</span></div>
          <div className={`${row} font-bold text-foreground`}><span>You earned</span><span>{cents(e.agent_cents)}</span></div>
        </div>
        <p>
          That makes it look as if the house keeps the other {cents(100 - Number(e.agent_cents))}. It doesn’t. The dollar one
          customer loses is what pays other customers when they win, and Paynow and mobile money take their charges on every
          deposit.
        </p>
        <p className="text-xs font-semibold uppercase tracking-wide">An example (not our actual figures)</p>
        <p>
          Say winners are paid back {cents(e.example_winnings_cents)} of every $1 staked, and the payment charge is a few cents:
        </p>
        <div className="divide-y divide-border rounded-lg border border-border px-3 tabular-nums">
          <div className={row}><span>The house keeps</span><span>{cents(e.example_kept_cents)}</span></div>
          <div className={row}><span>Paid to you under the old terms</span><span>−{cents(e.agent_cents)}</span></div>
          <div className={row}><span>Payment charges</span><span>−{cents(e.example_fee_cents)}</span></div>
          <div className={`${row} font-bold ${result < 0 ? 'text-destructive' : 'text-foreground'}`}>
            <span>{result < 0 ? 'The house loses' : 'Left for the house'}</span>
            <span>{cents(result)}</span>
          </div>
        </div>
        <p>
          On top of that come hosting, SMS and the cost of paying out withdrawals. Paying {cents(e.agent_cents)} on every
          dollar would close the site, and then nobody earns. That’s why a deposit commission now needs real play, and why
          you now earn on what your customers actually lose overall rather than on every losing ticket.
        </p>
      </div>
    </details>
  );
}
