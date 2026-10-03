'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { BsCheckCircleFill, BsXCircleFill } from 'react-icons/bs';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';

type State = 'pending' | 'paid' | 'failed' | 'cancelled' | 'unknown';

/** Where Paynow's card page sends the player back: wait for the payment to settle. */
function DepositReturn() {
  const ref = useSearchParams().get('ref');
  const { accessToken } = useAuth();
  const [state, setState] = useState<State>('pending');
  const [detail, setDetail] = useState<{ amount?: string; balance?: string }>({});

  useEffect(() => {
    if (!ref || !accessToken) return;
    let cancelled = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const res = await fetch(`${config.apiUrl}/wallet/deposits/${encodeURIComponent(ref!)}/`, {
          headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
        });
        if (res.status === 404) { if (!cancelled) setState('unknown'); return; }
        if (res.ok) {
          const p = (await res.json()) as { status: State; amount: string; balance: string };
          if (cancelled) return;
          setDetail({ amount: p.amount, balance: p.balance });
          if (p.status !== 'pending') { setState(p.status); return; }
        }
      } catch { /* retry */ }
      if (++tries < 60 && !cancelled) timer = setTimeout(tick, 3000);
    }
    void tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [ref, accessToken]);

  const view = !ref || state === 'unknown'
    ? { icon: <BsXCircleFill size={44} className="text-muted-foreground" />, title: 'Deposit not found', body: 'We couldn’t find that payment on your account.' }
    : state === 'paid'
      ? { icon: <BsCheckCircleFill size={44} className="text-win" />, title: 'Deposit successful', body: `$${Number(detail.amount ?? 0).toFixed(2)} was added. New balance $${Number(detail.balance ?? 0).toFixed(2)}.` }
      : state === 'pending'
        ? { icon: <Spinner size={40} className="text-secondary" />, title: 'Confirming your payment…', body: 'This usually takes a few seconds. Your balance updates as soon as Paynow confirms.' }
        : { icon: <BsXCircleFill size={44} className="text-destructive" />, title: state === 'cancelled' ? 'Payment cancelled' : 'Payment failed', body: 'No money was taken. You can try again from the deposit screen.' };

  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-16 text-center">
      <div className="mb-4">{view.icon}</div>
      <h1 className="mb-2 text-2xl font-extrabold">{view.title}</h1>
      <p className="mb-6 text-sm text-muted-foreground">{view.body}</p>
      {!accessToken && <p className="mb-4 text-sm text-muted-foreground">Log in to see your deposit status.</p>}
      <Link href="/sportsbook" className="rounded-xl bg-secondary px-6 py-3 text-sm font-extrabold text-white hover:opacity-90">
        Go to the sportsbook
      </Link>
    </div>
  );
}

export default function DepositReturnPage() {
  return (
    <Suspense fallback={null}>
      <DepositReturn />
    </Suspense>
  );
}
