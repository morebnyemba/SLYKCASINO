'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { AuthShell, authButtonClass, authInputClass } from '@/components/auth-shell';
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
    <AuthShell title="Create your account" subtitle="Join in seconds and claim your welcome bonus.">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {[
          { id: 'username', label: 'Username', value: username, set: setUsername, type: 'text' },
          { id: 'email', label: 'Email', value: email, set: setEmail, type: 'email' },
          { id: 'password', label: 'Password', value: password, set: setPassword, type: 'password' },
          { id: 'confirm', label: 'Confirm password', value: confirm, set: setConfirm, type: 'password' },
        ].map(({ id, label, value, set, type }) => (
          <div key={id} className="flex flex-col gap-1">
            <label className="text-xs font-bold text-muted-foreground" htmlFor={id}>{label}</label>
            <input
              id={id}
              type={type}
              value={value}
              onChange={(e) => set(e.target.value)}
              required
              minLength={type === 'password' ? 8 : 1}
              className={authInputClass}
            />
          </div>
        ))}
        {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm font-semibold text-destructive">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className={authButtonClass}
        >
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link href="/login" className="font-bold text-secondary underline-offset-4 hover:underline">Log in</Link>
      </p>
    </AuthShell>
  );
}
