'use client';

import { Card, CardContent } from '@slyk/ui/components/card';
import { useApi } from '@/lib/use-api';

interface Me {
  username?: string;
  email?: string;
  kyc_status?: string;
  balance?: string;
  currency?: string;
}

const KYC_LABEL: Record<string, string> = {
  unverified: 'Unverified',
  pending: 'Pending review',
  verified: 'Verified ✓',
};

export default function ProfilePage() {
  const { data: me, loading, error } = useApi<Me>('/players/me/');

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Card>
        <CardContent className="grid grid-cols-[120px_1fr] gap-2 pt-6 text-sm">
          <span className="text-muted-foreground">Username</span>
          <span>{me?.username || '—'}</span>
          <span className="text-muted-foreground">Email</span>
          <span>{me?.email || '—'}</span>
          <span className="text-muted-foreground">KYC status</span>
          <span>{KYC_LABEL[me?.kyc_status ?? ''] ?? me?.kyc_status ?? 'Unverified'}</span>
          <span className="text-muted-foreground">Balance</span>
          <span className="font-medium">{me?.balance ?? '0.00'} {me?.currency ?? 'USD'}</span>
        </CardContent>
      </Card>
    </div>
  );
}
