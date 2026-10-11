'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Card, CardContent } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';
import { useSiteIdentity } from '@/lib/identity-context';
import { Spinner } from '@slyk/ui/components/spinner';

export default function AdminLoginPage() {
  const { login } = useAuth();
  const identity = useSiteIdentity();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  const field = 'h-11 w-full rounded-xl border border-border bg-input/60 px-3.5 text-sm outline-none transition-colors focus:border-secondary focus:ring-2 focus:ring-secondary/30';
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[radial-gradient(120%_80%_at_0%_0%,#2a2178_0%,#15104a_45%,#0b0826_100%)] p-4">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-[#6C63E8]/25 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-24 h-96 w-96 rounded-full bg-[#312783]/50 blur-3xl" />
      <div className="relative w-full max-w-[400px]">
        <div className="mb-6 flex flex-col items-center gap-3 text-center text-white">
          {identity.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={identity.logo_url} alt={identity.site_name} className="h-11 w-auto max-w-[220px] object-contain" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src="/admin-portal/brand/wordmark.webp" alt={identity.site_name} width={602} height={180}
              className="h-16 w-auto drop-shadow-[0_6px_20px_rgba(47,209,47,0.3)]" />
          )}
          <div>
            <p className="text-2xl font-extrabold tracking-tight">{identity.site_name}</p>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/50">Operations console</p>
          </div>
        </div>
        <Card className="overflow-hidden rounded-3xl border-white/10 shadow-2xl shadow-black/40">
          <CardContent className="p-7">
            <p className="mb-1 text-lg font-extrabold">Sign in</p>
            <p className="mb-6 text-sm text-muted-foreground">Staff accounts only.</p>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-[12.5px] font-semibold text-muted-foreground" htmlFor="username">Username or email</label>
                <input id="username" type="text" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus autoComplete="username" className={field} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[12.5px] font-semibold text-muted-foreground" htmlFor="password">Password</label>
                <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" className={field} />
              </div>
              {error && <p className="rounded-xl border border-live/30 bg-live/10 px-3 py-2 text-sm font-medium text-live">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="mt-1 h-11 rounded-xl bg-gradient-to-br from-secondary to-primary text-sm font-bold text-white shadow-lg shadow-secondary/30 transition-all hover:brightness-110 disabled:opacity-50"
              >
                {loading ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Signing in…</span> : 'Sign in'}
              </button>
            </form>
          </CardContent>
        </Card>
        <p className="mt-4 text-center text-[11px] leading-relaxed text-muted-foreground">
          This turnkey solution was developed by Slyker Tech Web Services for BETBLITS.<br />
          Any request, order or action should be directed to BetBlits.
        </p>
      </div>
    </div>
  );
}
