'use client';

import { useEffect, useRef, useState } from 'react';
import { BsChevronLeft, BsShieldLockFill, BsXLg } from 'react-icons/bs';
import { GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';

interface Wallet {
  balance?: string;
  currency?: string;
}

interface Promotion {
  id: number;
  name: string;
  kind: string;
  active: boolean;
  bonus_amount: string;
  wagering_multiplier: string;
}

type FieldType = 'phone' | 'card' | 'crypto';
type MethodId = 'ecocash' | 'onemoney' | 'innbucks' | 'card' | 'usdt';
type Step = 'method' | 'amount' | 'confirm' | 'success';

interface MethodDef {
  id: MethodId;
  name: string;
  meta: string;
  speed: string;
  field: FieldType;
  logo: string;
  logoClass: string;
}

const METHODS: MethodDef[] = [
  { id: 'ecocash', name: 'EcoCash', meta: 'Mobile money · min $1', speed: 'Instant', field: 'phone', logo: 'EC', logoClass: 'bg-gradient-to-br from-[#E2231A] to-[#9c0f0a]' },
  { id: 'onemoney', name: 'OneMoney', meta: 'Mobile money · min $1', speed: 'Instant', field: 'phone', logo: 'OM', logoClass: 'bg-gradient-to-br from-[#0AA14B] to-[#066b32]' },
  { id: 'innbucks', name: 'InnBucks', meta: 'Wallet · min $1', speed: 'Instant', field: 'phone', logo: 'IB', logoClass: 'bg-gradient-to-br from-secondary to-primary' },
  { id: 'card', name: 'Visa / Mastercard', meta: 'Debit or credit card', speed: '1–2 min', field: 'card', logo: '••', logoClass: 'bg-gradient-to-br from-[#1A1F71] to-[#0d1145]' },
  { id: 'usdt', name: 'USDT (TRC-20)', meta: 'Crypto · no fees', speed: '~1 min', field: 'crypto', logo: '₮', logoClass: 'bg-gradient-to-br from-[#26A17B] to-[#15604a]' },
];

const PRESET_AMOUNTS = [10, 25, 50, 100, 250, 500];

const STEP_HEADINGS: Record<Step, string> = {
  method: 'Deposit funds',
  amount: 'Enter amount',
  confirm: 'Confirm deposit',
  success: 'All done',
};

function CheckIcon() {
  return (
    <span className="mb-4 flex h-[78px] w-[78px] items-center justify-center rounded-full bg-win/15">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" className="text-win">
        <path d="M4 12l5 5L20 6" className="animate-slyk-check" />
      </svg>
    </span>
  );
}

export function DepositModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { accessToken } = useAuth();
  const { data: wallet, refetch: refetchWallet } = useApi<Wallet>(open ? '/wallet/' : null);
  const { data: promotions } = useApi<Promotion[]>(open ? '/promotions/' : null);
  const depositPromo = (Array.isArray(promotions) ? promotions : []).find((p) => p.kind === 'deposit' && p.active) ?? null;

  const [step, setStep] = useState<Step>('method');
  const [method, setMethod] = useState<MethodId | null>(null);
  const [amount, setAmount] = useState('50');
  const [phone, setPhone] = useState('');
  const [card, setCard] = useState('');
  const [applyBonus, setApplyBonus] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bonusWarning, setBonusWarning] = useState<string | null>(null);
  const [result, setResult] = useState<{ amount: number; bonus: number; balance: number } | null>(null);
  const idempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  function resetAndClose() {
    setStep('method');
    setMethod(null);
    setAmount('50');
    setPhone('');
    setCard('');
    setApplyBonus(true);
    setError(null);
    setBonusWarning(null);
    setResult(null);
    idempotencyKeyRef.current = null;
    onClose();
  }

  if (!open) return null;

  const selected = METHODS.find((m) => m.id === method) ?? METHODS[0];
  const numAmount = parseFloat(amount) || 0;
  const bonusAmount = applyBonus && depositPromo ? Number(depositPromo.bonus_amount) : 0;
  const totalCredited = numAmount + bonusAmount;
  const balance = Number(wallet?.balance ?? 0);
  const currency = wallet?.currency ?? 'USD';

  const fieldValid =
    selected.field === 'phone' ? phone.trim().length >= 7 :
    selected.field === 'card' ? card.replace(/\s/g, '').length >= 12 :
    true;
  const canContinueAmount = numAmount > 0 && fieldValid;

  async function handleConfirm() {
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    setBonusWarning(null);
    if (!idempotencyKeyRef.current) idempotencyKeyRef.current = `deposit:req:${crypto.randomUUID()}`;

    const { data, error: depErr } = await authedPost<{ balance: string }>(
      '/wallet/deposit/',
      { amount: numAmount, idempotency_key: idempotencyKeyRef.current },
      accessToken,
    );
    if (depErr || !data) {
      setError(depErr ?? 'Deposit failed. Please try again.');
      setSubmitting(false);
      return;
    }

    let creditedBonus = 0;
    if (applyBonus && depositPromo) {
      const { error: claimErr } = await authedPost(`/promotions/${depositPromo.id}/claim/`, {}, accessToken);
      if (claimErr) {
        setBonusWarning(`Deposit succeeded, but the bonus couldn't be applied: ${claimErr}`);
      } else {
        creditedBonus = Number(depositPromo.bonus_amount);
      }
    }

    setResult({ amount: numAmount, bonus: creditedBonus, balance: Number(data.balance) + creditedBonus });
    refetchWallet();
    setStep('success');
    setSubmitting(false);
  }

  const summaryRows = [
    { k: 'Method', v: selected.name },
    { k: 'Deposit amount', v: `$${numAmount.toFixed(2)}` },
    {
      k: 'Bonus',
      v: bonusAmount > 0 ? `+$${bonusAmount.toFixed(2)} (${depositPromo!.name})` : 'None',
      accent: bonusAmount > 0,
    },
    { k: 'Fee', v: 'Free', win: true },
  ];

  let primaryLabel = 'Continue';
  let primaryDisabled = false;
  let onPrimary = () => {};
  if (step === 'method') {
    primaryDisabled = !method;
    onPrimary = () => method && setStep('amount');
  } else if (step === 'amount') {
    primaryLabel = 'Review deposit';
    primaryDisabled = !canContinueAmount;
    onPrimary = () => canContinueAmount && setStep('confirm');
  } else if (step === 'confirm') {
    primaryLabel = submitting ? 'Confirming…' : `Confirm deposit · $${numAmount.toFixed(2)}`;
    primaryDisabled = submitting;
    onPrimary = handleConfirm;
  } else {
    primaryLabel = 'Start playing';
    onPrimary = resetAndClose;
  }

  function onBack() {
    setError(null);
    setStep(step === 'confirm' ? 'amount' : 'method');
  }

  // -- shared step bodies (responsive classes cover both desktop modal & mobile sheet) --

  const methodList = (
    <div className="flex flex-col gap-2.5">
      {METHODS.map((m) => (
        <button
          key={m.id}
          onClick={() => { setMethod(m.id); setStep('amount'); }}
          className={`flex items-center gap-3 rounded-2xl border bg-card px-3.5 py-3 text-left transition-colors hover:border-secondary ${
            method === m.id ? 'border-secondary' : 'border-border'
          }`}
        >
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-[13px] font-extrabold text-white ${m.logoClass}`}>
            {m.logo}
          </span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm font-bold">{m.name}</span>
            <span className="text-[11.5px] text-muted-foreground">{m.meta}</span>
          </span>
          <span className="ml-auto flex items-center gap-2.5">
            <span className="rounded-md bg-win/15 px-2 py-1 text-[10.5px] font-bold text-win">{m.speed}</span>
            <span className="text-lg text-muted-foreground">›</span>
          </span>
        </button>
      ))}
      <p className="mt-1 text-center text-[11px] text-muted-foreground">
        Demo environment — every method credits instantly through our test payment processor.
      </p>
    </div>
  );

  const amountBody = (
    <div>
      <div className="mb-4 flex items-center gap-2.5 rounded-xl border border-border bg-card px-3.5 py-2.5">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[11px] font-extrabold text-white ${selected.logoClass}`}>
          {selected.logo}
        </span>
        <span className="text-[13.5px] font-bold">{selected.name}</span>
        <button onClick={() => setStep('method')} className="ml-auto text-[12.5px] font-bold text-secondary">
          Change
        </button>
      </div>

      <p className="mb-1.5 text-[12.5px] font-bold text-muted-foreground">Enter amount ({currency})</p>
      <div className="flex items-center justify-center gap-1 rounded-2xl border-2 border-secondary bg-muted/30 px-4 py-3.5 sm:justify-start">
        <span className="font-mono text-[34px] font-extrabold text-muted-foreground">$</span>
        <input
          value={amount}
          onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))}
          inputMode="decimal"
          placeholder="0"
          className="w-[140px] min-w-0 border-none bg-transparent text-center font-mono text-[38px] font-extrabold text-foreground outline-none sm:flex-1 sm:text-left"
        />
      </div>
      <div className="mt-2.5 grid grid-cols-3 gap-2 sm:flex sm:flex-wrap">
        {PRESET_AMOUNTS.map((v) => (
          <button
            key={v}
            onClick={() => setAmount(String(v))}
            className={`rounded-lg px-3 py-2 text-[13px] font-bold ${
              numAmount === v ? 'bg-secondary text-white' : 'border border-border bg-chip text-muted-foreground'
            }`}
          >
            ${v}
          </button>
        ))}
      </div>

      {selected.field === 'phone' && (
        <div className="mt-4">
          <p className="mb-1.5 text-[12.5px] font-bold text-muted-foreground">{selected.name} number</p>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="07X XXX XXXX"
            className="w-full rounded-xl border border-border bg-card px-3.5 py-3 text-[15px] outline-none focus:ring-2 focus:ring-secondary"
          />
        </div>
      )}
      {selected.field === 'card' && (
        <div className="mt-4">
          <p className="mb-1.5 text-[12.5px] font-bold text-muted-foreground">Card number</p>
          <input
            value={card}
            onChange={(e) => setCard(e.target.value)}
            placeholder="1234 5678 9012 3456"
            className="w-full rounded-xl border border-border bg-card px-3.5 py-3 text-[15px] tabular-nums outline-none focus:ring-2 focus:ring-secondary"
          />
        </div>
      )}
      {selected.field === 'crypto' && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-dashed border-border bg-card p-3.5">
          <span className="flex h-[54px] w-[54px] shrink-0 items-center justify-center rounded-lg bg-white text-[9px] font-extrabold text-black">QR</span>
          <div className="min-w-0">
            <p className="mb-0.5 text-[11.5px] text-muted-foreground">Send USDT (TRC-20) to:</p>
            <p className="break-all font-mono text-[12px]">TKx…8fQ2aL9pWmZ4vR</p>
          </div>
        </div>
      )}

      {depositPromo && (
        <button
          onClick={() => setApplyBonus((v) => !v)}
          className={`mt-4 flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left ${
            applyBonus ? 'border-secondary bg-secondary/10' : 'border-border bg-card'
          }`}
        >
          <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${applyBonus ? 'bg-gold' : 'bg-chip'}`}>
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${applyBonus ? 'left-[18px]' : 'left-0.5'}`}
            />
          </span>
          <span className="min-w-0">
            <span className="block text-[13.5px] font-bold">Apply {depositPromo.name}</span>
            <span className="block text-[11.5px] text-muted-foreground">
              +${Number(depositPromo.bonus_amount).toFixed(2)} bonus · wagering {Number(depositPromo.wagering_multiplier)}×
            </span>
          </span>
          <span className="ml-auto text-[11px] font-extrabold text-gold">
            {applyBonus ? `+$${Number(depositPromo.bonus_amount).toFixed(2)}` : ''}
          </span>
        </button>
      )}
    </div>
  );

  const confirmBody = (
    <div>
      <p className="mb-3.5 text-[13px] text-muted-foreground">Review your deposit before confirming.</p>
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        {summaryRows.map((row) => (
          <div key={row.k} className="flex items-center justify-between border-b border-border px-4 py-3 last:border-0">
            <span className="text-[13px] text-muted-foreground">{row.k}</span>
            <span className={`text-[13.5px] font-bold ${row.accent ? 'text-gold' : row.win ? 'text-win' : ''}`}>
              {row.v}
            </span>
          </div>
        ))}
        <div className="flex items-center justify-between bg-muted/40 px-4 py-3.5">
          <span className="text-sm font-bold">Total credited</span>
          <span className="font-mono text-xl font-extrabold text-win">${totalCredited.toFixed(2)}</span>
        </div>
      </div>
      {error && <p className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-[12.5px] text-destructive">{error}</p>}
      <p className="mt-3.5 text-[11px] leading-relaxed text-muted-foreground">
        By confirming you agree to the deposit terms.
        {depositPromo && ' Bonus funds carry wagering requirements.'} Gambling can be addictive — 18+ only.
      </p>
    </div>
  );

  const successBody = (
    <div className="flex flex-col items-center px-0 py-3 text-center">
      <CheckIcon />
      <h2 className="mb-2 text-2xl font-extrabold">Deposit successful</h2>
      <p className="mb-1 max-w-[340px] text-sm text-muted-foreground">
        ${result ? (result.amount + result.bonus).toFixed(2) : totalCredited.toFixed(2)} has been credited to your wallet via {selected.name}.
      </p>
      {bonusWarning && <p className="mb-1 max-w-[340px] text-xs text-gold">{bonusWarning}</p>}
      <p className="text-[13px] text-muted-foreground">
        New balance <b className="text-foreground">${(result?.balance ?? balance).toFixed(2)} {currency}</b>
      </p>
    </div>
  );

  const body = step === 'method' ? methodList : step === 'amount' ? amountBody : step === 'confirm' ? confirmBody : successBody;

  const showBack = step === 'amount' || step === 'confirm';
  const showSecure = step !== 'success';

  return (
    <>
      {/* Desktop: centered modal */}
      <div className="fixed inset-0 z-[60] hidden items-center justify-center bg-black/60 p-5 backdrop-blur-sm lg:flex" onClick={resetAndClose}>
        <div
          className="w-[560px] max-w-full overflow-hidden rounded-[22px] border border-border bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-3 bg-gradient-to-r from-primary to-secondary px-5.5 py-5">
            <span className="flex items-center rounded-md bg-gradient-to-br from-gold to-gold/70 px-1.5 py-1 text-xs font-extrabold text-gold-foreground">
              <GiPerspectiveDiceSixFacesRandom size={12} className="mr-0.5" />
              SLÝK
            </span>
            <div className="flex flex-col leading-tight">
              <span className="text-base font-extrabold text-white">Deposit funds</span>
              <span className="text-xs text-white/60">Balance ${balance.toFixed(2)} {currency}</span>
            </div>
            <button onClick={resetAndClose} aria-label="Close" className="ml-auto flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-white/15 text-white">
              <BsXLg size={15} />
            </button>
          </div>

          <StepDots step={step} />

          <div className="min-h-[300px] px-5.5 pb-6 pt-4.5">{body}</div>

          <div className="flex items-center gap-3 border-t border-border px-5.5 py-4">
            {showBack && (
              <button onClick={onBack} className="rounded-xl border border-border bg-card px-5 py-3 text-sm font-bold">
                Back
              </button>
            )}
            <div className="ml-auto flex items-center gap-3">
              {showSecure && (
                <span className="hidden items-center gap-1.5 text-[11.5px] text-muted-foreground sm:flex">
                  <BsShieldLockFill size={12} /> SSL secured
                </span>
              )}
              <button
                onClick={onPrimary}
                disabled={primaryDisabled}
                className="rounded-xl bg-gradient-to-br from-gold to-gold/70 px-7 py-3 text-[14.5px] font-extrabold text-gold-foreground shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
              >
                {primaryLabel}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile: bottom sheet */}
      <div className="fixed inset-0 z-[60] flex items-end bg-black/60 lg:hidden" onClick={resetAndClose}>
        <div
          className="animate-slyk-sheet flex max-h-[88vh] w-full flex-col rounded-t-3xl border-t border-border bg-background"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex justify-center pb-1 pt-2.5">
            <span className="h-[5px] w-10 rounded-full bg-border" />
          </div>
          <div className="flex items-center gap-3 px-4.5 pb-3.5 pt-2">
            {showBack && (
              <button onClick={onBack} aria-label="Back" className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-border bg-card">
                <BsChevronLeft size={15} />
              </button>
            )}
            <div className="flex flex-col leading-tight">
              <span className="text-[17px] font-extrabold">{STEP_HEADINGS[step]}</span>
              <span className="text-xs text-muted-foreground">Balance ${balance.toFixed(2)} {currency}</span>
            </div>
            <button onClick={resetAndClose} aria-label="Close" className="ml-auto flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-border bg-card">
              <BsXLg size={14} />
            </button>
          </div>

          <div className="flex items-center gap-1.5 px-4.5 pb-3">
            {(['method', 'amount', 'confirm'] as const).map((s, i) => {
              const order = ['method', 'amount', 'confirm'];
              const stepIdx = step === 'success' ? 3 : order.indexOf(step);
              return <span key={s} className={`h-1 flex-1 rounded-full ${i <= stepIdx ? 'bg-gold' : 'bg-border'}`} />;
            })}
          </div>

          <div className="flex-1 overflow-y-auto px-4.5">{body}</div>

          <div className="border-t border-border px-4.5 py-3.5 pb-6">
            <button
              onClick={onPrimary}
              disabled={primaryDisabled}
              className="w-full rounded-2xl bg-gradient-to-br from-gold to-gold/70 py-3.5 text-[15px] font-extrabold text-gold-foreground shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
            >
              {primaryLabel}
            </button>
            {showSecure && (
              <p className="mt-2.5 flex items-center justify-center gap-1.5 text-center text-[11px] text-muted-foreground">
                <BsShieldLockFill size={11} /> Secured with 256-bit SSL encryption
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function StepDots({ step }: { step: Step }) {
  const order = ['method', 'amount', 'confirm'];
  const stepIdx = step === 'success' ? 3 : order.indexOf(step);
  const labels = ['Method', 'Amount', 'Confirm'];
  return (
    <div className="flex items-center gap-1.5 px-5.5 pb-1 pt-4">
      {labels.map((label, i) => {
        const done = i < stepIdx;
        const active = i === stepIdx;
        return (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-extrabold ${
                active ? 'bg-gold text-gold-foreground' : done ? 'bg-secondary text-white' : 'bg-chip text-muted-foreground'
              }`}
            >
              {done ? '✓' : i + 1}
            </span>
            <span className={`text-[12.5px] font-bold ${active || done ? 'text-foreground' : 'text-muted-foreground'}`}>{label}</span>
            {i < 2 && <span className={`mx-1 h-0.5 w-[26px] rounded-full ${done ? 'bg-secondary' : 'bg-border'}`} />}
          </div>
        );
      })}
    </div>
  );
}
