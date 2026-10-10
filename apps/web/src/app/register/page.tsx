'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { FaEye, FaEyeSlash } from 'react-icons/fa';
import { AuthShell, authButtonClass, authInputClass, useWelcomeOffer } from '@/components/auth-shell';
import { RegisterError } from '@/lib/auth';
import { AccountCreatedError, useAuth } from '@/lib/auth-context';
import { getReferral, setReferral } from '@/lib/referral';
import { Spinner } from '@slyk/ui/components/spinner';
import { useApi } from '@/lib/use-api';

/** Mirrors the backend's normalize_username: lowercase, a-z0-9_ only. */
function normalizeUsername(raw: string) {
  return raw.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
}

/** Rough strength for the meter only; the server enforces the real rules. */
function passwordStrength(pw: string): { score: number; label: string } {
  if (!pw) return { score: 0, label: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (/^\d+$/.test(pw) || pw.length < 8) score = Math.min(score, 1);
  const level = Math.min(4, Math.max(1, score));
  return { score: level, label: ['', 'Weak', 'Fair', 'Good', 'Strong'][level] };
}

const STRENGTH_COLOR = ['', 'bg-destructive', 'bg-gold', 'bg-secondary', 'bg-win'];

type Field = 'username' | 'email' | 'password' | 'confirm' | 'terms';

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return <p id={`${id}-error`} className="text-xs font-semibold text-destructive">{message}</p>;
}

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [terms, setTerms] = useState(false);
  const [refCode, setRefCode] = useState('');
  const [refOpen, setRefOpen] = useState(false);
  const offer = useWelcomeOffer();
  const { data: welcome } = useApi<{ programme?: { welcome_bonus_percent: string; welcome_bonus_cap: string } }>('/affiliates/terms/', { public: true });
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [formError, setFormError] = useState('');
  const [accountCreated, setAccountCreated] = useState(false);
  const [loading, setLoading] = useState(false);

  // Prefill the code from an affiliate link the visitor arrived through.
  useEffect(() => {
    const ref = getReferral()?.ref ?? '';
    setRefCode(ref);
    if (ref) setRefOpen(true);
  }, []);

  const normalized = normalizeUsername(username);
  const strength = passwordStrength(password);

  function clearError(field: Field) {
    setErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));
  }

  function validate(): Partial<Record<Field, string>> {
    const e: Partial<Record<Field, string>> = {};
    if (normalized.length < 3) e.username = 'Use at least 3 letters, numbers or underscores.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) e.email = 'Enter a valid email address.';
    if (password.length < 8) e.password = 'Use at least 8 characters.';
    else if (/^\d+$/.test(password)) e.password = 'Your password can’t be only numbers.';
    if (confirm !== password) e.confirm = 'Passwords do not match.';
    if (!terms) e.terms = 'Please confirm you are 18 or older and accept the terms.';
    return e;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError('');
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length) return;
    setLoading(true);
    if (refCode) setReferral(refCode);
    try {
      await register(username, email.trim(), password, terms);
      router.push('/account/profile');
    } catch (err) {
      if (err instanceof AccountCreatedError) {
        setAccountCreated(true);
      } else if (err instanceof RegisterError) {
        const { username: u, email: em, password: pw, accept_terms: tm, ...rest } = err.fields;
        setErrors({ username: u, email: em, password: pw, terms: tm });
        setFormError(err.message || Object.values(rest).join(' '));
      } else {
        setFormError('Could not reach the server. Check your connection and try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  if (accountCreated) {
    return (
      <AuthShell title="Account created" subtitle="You’re in. One more step.">
        <p className="mb-5 text-sm text-muted-foreground">
          Your account was created, but we couldn’t sign you in automatically. Log in with your email and password.
          We’ve also sent a link to <b className="text-foreground">{email}</b> to verify your address.
        </p>
        <Link href="/login" className={`${authButtonClass} block text-center`}>Log in</Link>
      </AuthShell>
    );
  }

  const describedBy = (id: Field, hint?: boolean) =>
    [errors[id] ? `${id}-error` : '', hint ? `${id}-hint` : ''].filter(Boolean).join(' ') || undefined;
  const inputClass = (id: Field) => `${authInputClass} ${errors[id] ? 'border-destructive focus:ring-destructive/40' : ''}`;

  return (
    <AuthShell
      title="Create your account"
      subtitle={offer ? `Join in seconds — get a ${offer} with a friend’s referral code.` : 'Join in seconds.'}
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-bold text-muted-foreground" htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(e) => { setUsername(e.target.value); clearError('username'); }}
            maxLength={30}
            required
            aria-invalid={!!errors.username}
            aria-describedby={describedBy('username', true)}
            className={inputClass('username')}
          />
          <FieldError id="username" message={errors.username} />
          {!errors.username && username && normalized !== username && normalized.length >= 3 && (
            <p id="username-hint" className="text-xs text-muted-foreground">
              You’ll appear as <b className="text-foreground">{normalized}</b>
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-bold text-muted-foreground" htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(e) => { setEmail(e.target.value); clearError('email'); }}
            required
            aria-invalid={!!errors.email}
            aria-describedby={describedBy('email')}
            className={inputClass('email')}
          />
          <FieldError id="email" message={errors.email} />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-bold text-muted-foreground" htmlFor="password">Password</label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); clearError('password'); }}
              required
              minLength={8}
              aria-invalid={!!errors.password}
              aria-describedby={describedBy('password', true)}
              className={`${inputClass('password')} pr-11`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              {showPassword ? <FaEyeSlash size={15} /> : <FaEye size={15} />}
            </button>
          </div>
          {password && (
            <div id="password-hint" className="flex items-center gap-2">
              <div className="flex flex-1 gap-1" aria-hidden>
                {[1, 2, 3, 4].map((i) => (
                  <span key={i} className={`h-1 flex-1 rounded-full ${i <= strength.score ? STRENGTH_COLOR[strength.score] : 'bg-muted'}`} />
                ))}
              </div>
              <span className="w-12 text-right text-[11px] font-semibold text-muted-foreground">{strength.label}</span>
            </div>
          )}
          <FieldError id="password" message={errors.password} />
          {!password && !errors.password && (
            <p id="password-hint" className="text-xs text-muted-foreground">At least 8 characters, not only numbers.</p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-bold text-muted-foreground" htmlFor="confirm">Confirm password</label>
          <input
            id="confirm"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => { setConfirm(e.target.value); clearError('confirm'); }}
            required
            aria-invalid={!!errors.confirm}
            aria-describedby={describedBy('confirm')}
            className={inputClass('confirm')}
          />
          <FieldError id="confirm" message={errors.confirm} />
        </div>

        {refCode && Number(welcome?.programme?.welcome_bonus_percent ?? 0) > 0 && (
          <p className="rounded-lg bg-win/10 px-3 py-2 text-xs font-semibold text-win">
            🎁 Joining with code {refCode} gets you a {Number(welcome!.programme!.welcome_bonus_percent)}% bonus on your first deposit
            {Number(welcome!.programme!.welcome_bonus_cap) > 0 ? ` (up to $${Number(welcome!.programme!.welcome_bonus_cap)})` : ''}.
          </p>
        )}
        {refOpen ? (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-bold text-muted-foreground" htmlFor="ref">
              Referral code <span className="font-normal">(optional)</span>
            </label>
            <input
              id="ref"
              value={refCode}
              onChange={(e) => setRefCode(e.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 24))}
              className={authInputClass}
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setRefOpen(true)}
            className="self-start text-xs font-bold text-secondary underline-offset-4 hover:underline"
          >
            Have a referral code?
          </button>
        )}

        <div className="flex flex-col gap-1">
          <label className="flex items-start gap-2.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={terms}
              onChange={(e) => { setTerms(e.target.checked); clearError('terms'); }}
              aria-invalid={!!errors.terms}
              aria-describedby={describedBy('terms')}
              className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--win)]"
            />
            <span>
              I am 18 or older and accept the{' '}
              <Link href="/legal/terms" className="font-bold text-secondary hover:underline">Terms</Link> and{' '}
              <Link href="/legal/privacy" className="font-bold text-secondary hover:underline">Privacy Policy</Link>.
            </span>
          </label>
          <FieldError id="terms" message={errors.terms} />
        </div>

        {formError && (
          <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm font-semibold text-destructive">{formError}</p>
        )}
        <button type="submit" disabled={loading} className={authButtonClass}>
          {loading ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Creating account…</span> : 'Create account'}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link href="/login" className="font-bold text-secondary underline-offset-4 hover:underline">Log in</Link>
      </p>
    </AuthShell>
  );
}
