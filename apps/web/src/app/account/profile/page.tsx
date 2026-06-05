import type { Metadata } from 'next';
import { Card, CardContent } from '@slyk/ui/components/card';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Profile — SLYK' };

interface Me {
  username?: string;
  email?: string;
  kyc_status?: string;
}

export default async function ProfilePage() {
  const me = (await apiGet<Me>('/players/me/')) as Me;
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Profile</h1>
      <Card>
        <CardContent className="grid grid-cols-[120px_1fr] gap-2 pt-6 text-sm">
          <span className="text-muted-foreground">Username</span><span>{me.username || '—'}</span>
          <span className="text-muted-foreground">Email</span><span>{me.email || '—'}</span>
          <span className="text-muted-foreground">KYC status</span><span>{me.kyc_status || 'unverified'}</span>
        </CardContent>
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">Served by the Django REST API (<code>/api/players/me/</code>).</p>
    </div>
  );
}
