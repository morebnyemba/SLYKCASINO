'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Button } from '@slyk/ui/components/button';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const { accessToken } = useAuth();

  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  // Auto-confirm if token present
  useEffect(() => {
    if (!token) return;
    setStatus('loading');
    fetch(`${config.apiUrl}/auth/verify-email/confirm/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (res.ok) {
          setStatus('success');
          setMessage('Your email has been verified! You can now log in.');
        } else {
          const data = (await res.json().catch(() => ({}))) as { detail?: string };
          setStatus('error');
          setMessage(data.detail || 'Verification failed. The link may have expired.');
        }
      })
      .catch(() => {
        setStatus('error');
        setMessage('Network error. Please try again.');
      });
  }, [token]);

  const resend = () => {
    if (!accessToken) {
      setMessage('You must be logged in to resend the verification email.');
      return;
    }
    setStatus('loading');
    fetch(`${config.apiUrl}/auth/verify-email/request/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    })
      .then(async (res) => {
        if (res.ok) {
          setStatus('success');
          setMessage('Verification email sent! Please check your inbox.');
        } else {
          setStatus('error');
          setMessage('Failed to resend verification email.');
        }
      })
      .catch(() => {
        setStatus('error');
        setMessage('Network error. Please try again.');
      });
  };

  if (token) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Email Verification</CardTitle>
          </CardHeader>
          <CardContent>
            {status === 'loading' && <p className="text-muted-foreground">Verifying your email…</p>}
            {status === 'success' && <p className="text-green-600">{message}</p>}
            {status === 'error' && <p className="text-red-500">{message}</p>}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Verify your email</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground">
            We sent a verification link to your email address. Please check your inbox (and spam folder).
          </p>
          {message && (
            <p className={status === 'error' ? 'text-red-500' : 'text-green-600'}>{message}</p>
          )}
          <Button onClick={resend} disabled={status === 'loading'}>
            {status === 'loading' ? 'Sending…' : 'Resend verification email'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailContent />
    </Suspense>
  );
}
