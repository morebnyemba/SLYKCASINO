'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { BsArrowLeft, BsCheck2, BsLink45Deg, BsShare, BsUpcScan } from 'react-icons/bs';
import { BetTicket, isSettled, ticketFromRow, type ApiBet, type ApiSlip } from '@/components/bet-ticket';
import { useCashoutOffers } from '@/components/cashout';
import { TicketBarcode } from '@/components/ticket-barcode';
import { useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

type Row = (ApiBet | ApiSlip) & { kind: 'single' | 'multiple'; ticket: string; mine: boolean };

/** One ticket by its code: barcode, selections with live scores, result. Refreshes while it's running. */
export function TicketView({ code }: { code: string }) {
  const { data, error, loading, refetch } = useApi<Row>(`/tickets/${encodeURIComponent(code)}/`, { public: true });
  const ticket = useMemo(() => (data ? ticketFromRow(data) : null), [data]);
  // Stable list: the cash-out hook re-reads its offers whenever this changes.
  const mineList = useMemo(() => (ticket && data?.mine ? [ticket] : []), [ticket, data?.mine]);
  const offers = useCashoutOffers(mineList);
  const [copied, setCopied] = useState(false);
  // Known only in the browser (not while rendering on the server).
  const [canShare, setCanShare] = useState(false);
  useEffect(() => { setCanShare('share' in navigator); }, []);

  const running = !!ticket && !isSettled(ticket.status);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') refetch(); }, 15_000);
    return () => window.clearInterval(t);
  }, [running, refetch]);

  async function share() {
    const url = window.location.href;
    try {
      if (canShare) { await navigator.share({ title: `Ticket ${ticket?.code ?? code}`, url }); return; }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { /* cancelled */ }
  }

  if (loading && !data) return <LoadingState />;
  if (!ticket || !data) {
    const notFound = !!error && /404/.test(error);
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-border bg-card px-6 py-10 text-center">
        <p className="font-bold">{notFound ? 'Ticket not found' : 'Couldn’t load this ticket'}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {notFound ? `No ticket has the code ${code.toUpperCase()}. Check it against the code under the barcode.` : 'Please try again in a moment.'}
        </p>
        <Link href="/check-ticket" className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-secondary px-4 py-2 text-sm font-bold text-white">
          <BsUpcScan size={13} /> Check another ticket
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Link href={data.mine ? '/account/bets' : '/check-ticket'} className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground">
          <BsArrowLeft size={13} /> {data.mine ? 'My bets' : 'Check a ticket'}
        </Link>
        <button onClick={() => void share()} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-bold hover:bg-muted">
          {copied ? <BsCheck2 size={13} /> : canShare ? <BsShare size={12} /> : <BsLink45Deg size={14} />}
          {copied ? 'Link copied' : 'Share'}
        </button>
      </div>

      {ticket.code && <TicketBarcode code={ticket.code} />}

      <BetTicket ticket={ticket} offer={data.mine ? offers[ticket.key] : undefined} onChanged={refetch} isPublic={!data.mine} />

      {running && <p className="text-center text-xs text-muted-foreground">Scores and results update here on their own.</p>}
      {!data.mine && (
        <p className="text-center text-xs text-muted-foreground">
          Anyone with this ticket’s code can see it here. It never shows who placed it.
        </p>
      )}
    </div>
  );
}
