'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (password !== confirm) { setError('Passwords do not match'); return; }
    setLoading(true);
    try {
      await register(username, email, password);
      router.push('/account/profile');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {[
              { id: 'username', label: 'Username', value: username, set: setUsername, type: 'text' },
              { id: 'email', label: 'Email', value: email, set: setEmail, type: 'email' },
              { id: 'password', label: 'Password', value: password, set: setPassword, type: 'password' },
              { id: 'confirm', label: 'Confirm password', value: confirm, set: setConfirm, type: 'password' },
            ].map(({ id, label, value, set, type }) => (
              <div key={id} className="flex flex-col gap-1">
                <label className="text-sm font-medium" htmlFor={id}>{label}</label>
                <input
                  id={id}
                  type={type}
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  required
                  minLength={type === 'password' ? 8 : 1}
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            ))}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link href="/login" className="text-primary underline-offset-4 hover:underline">Log in</Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
