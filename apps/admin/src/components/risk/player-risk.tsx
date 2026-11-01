'use client';

import Link from 'next/link';
import { useState } from 'react';
import { BsDownload } from 'react-icons/bs';
import { Badge, Btn, Notice, Panel } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { downloadReport, SEVERITY_TONE, type RiskReport } from '@/lib/risk';
import { authedPost, useApi } from '@/lib/use-api';

/** Fraud state on the player page: restrictions (staff can add, a superuser
 *  lifts), open case, latest signals and linked accounts. */
export function PlayerRisk({ playerId, onChanged }: { playerId: number; onChanged?: () => void }) {
  const { accessToken, user } = useAuth();
  const { data, refetch } = useApi<RiskReport>(`/admin/risk/players/${playerId}/`);
  const [error, setError] = useState('');
  if (!data) return null;
  const { profile } = data;
  const openCase = data.cases.find((c) => c.status === 'open');

  async function toggle(key: 'withdrawals_frozen' | 'bonus_blocked', value: boolean) {
    if (!accessToken) return;
    setError('');
    const res = await authedPost(`/admin/risk/players/${playerId}/`, { [key]: value }, accessToken);
    if (res.error) setError(res.error);
    refetch(); onChanged?.();
  }

  const restriction = (key: 'withdrawals_frozen' | 'bonus_blocked', label: string) => {
    const on = profile[key];
    const locked = on && !user?.isSuperuser;
    return (
      <Btn size="sm" variant={on ? 'danger' : 'outline'} disabled={locked}
        title={locked ? 'Only a superuser can lift this' : undefined}
        onClick={() => toggle(key, !on)}>
        {on ? `${label}: on — lift` : `${label}: off — apply`}
      </Btn>
    );
  };

  return (
    <Panel title="Fraud & risk" description={`Score ${profile.score}${profile.under_review ? ' · under review' : ''}`}
      actions={<Btn size="sm" icon={BsDownload} onClick={() => downloadReport(data, `fraud-report-player-${playerId}`)}>Report</Btn>}>
      {error && <div className="mb-3"><Notice tone="red" onClose={() => setError('')}>{error}</Notice></div>}
      {openCase && (
        <p className="mb-3 text-sm">
          <Badge tone={openCase.action === 'suspended' ? 'red' : 'gold'} dot>{openCase.action_label}</Badge>{' '}
          <Link href={`/risk/${openCase.id}`} className="font-semibold text-secondary hover:underline">Open case #{openCase.id}</Link>
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {restriction('withdrawals_frozen', 'Withdrawals frozen')}
        {restriction('bonus_blocked', 'Bonuses blocked')}
      </div>
      {data.signals.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {data.signals.slice(0, 5).map((s) => (
            <li key={s.id} className="flex items-start gap-2">
              <Badge tone={SEVERITY_TONE[s.severity]}>{s.severity}</Badge>
              <span>{s.detail} <span className="text-xs text-muted-foreground">{new Date(s.created_at).toLocaleDateString()}</span></span>
            </li>
          ))}
        </ul>
      )}
      {data.linked_accounts.length > 0 && (
        <p className="mt-4 text-sm">
          <span className="text-muted-foreground">Linked: </span>
          {data.linked_accounts.map((l) => (
            <Link key={l.player_id} href={`/players/${l.player_id}`} className="mr-2 hover:underline">
              {l.username ?? `#${l.player_id}`} <span className="text-xs text-muted-foreground">({l.how.join(', ')})</span>
            </Link>
          ))}
        </p>
      )}
    </Panel>
  );
}
