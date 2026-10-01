'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import { Card, CardContent } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';
import { useSiteIdentity } from '@/lib/identity-context';

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

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary via-primary to-secondary/60 p-4">
      <Card className="w-full max-w-sm overflow-hidden rounded-2xl border-gold/20">
        <div className="flex flex-col items-center gap-3 bg-gradient-to-br from-primary to-primary/80 px-6 py-8">
          {identity.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={identity.logo_url} alt={identity.site_name} className="h-10 w-auto max-w-[200px] object-contain" />
          ) : (
            <span className="flex items-center gap-1 rounded-md bg-gradient-to-br from-gold to-gold/70 px-3 py-1.5 text-base font-black tracking-wide text-gold-foreground shadow-inner shadow-black/30 ring-1 ring-white/15">
              <GiPerspectiveDiceSixFacesRandom size={16} />
              {identity.site_name}
            </span>
          )}
          <p className="text-sm font-semibold text-white/90">Admin Command Center</p>
        </div>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium" htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-secondary"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-secondary"
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-4 py-2 text-sm font-bold text-gold-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
