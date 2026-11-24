'use client';

import { useState } from 'react';
import { Badge, Notice, Panel, Switch } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

/** Whether new accounts (website and WhatsApp) must give a valid agent code. Superusers change it. */
export function AgentCodeRule() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<{ require_agent_code: boolean; can_edit: boolean }>('/admin/affiliate-signup-rule/');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function toggle(on: boolean) {
    if (!accessToken) return;
    if (!on && !window.confirm('Let people register without an agent code (website and WhatsApp)?')) return;
    setBusy(true); setError('');
    const res = await authedRequest('PUT', '/admin/affiliate-signup-rule/', accessToken, { require_agent_code: on });
    setBusy(false);
    if (res.error) setError(res.error);
    refetch();
  }

  return (
    <Panel title="Agent code at sign-up"
      description="When on, nobody can create an account on the website or on WhatsApp without a valid, active agent code, and every new player is attached to that agent."
      actions={data && (data.require_agent_code ? <Badge tone="green" dot>Required</Badge> : <Badge tone="gold" dot>Optional</Badge>)}>
      {error && <Notice tone="red" onClose={() => setError('')}>{error}</Notice>}
      {data && (
        <div className="flex items-center gap-3 text-sm font-semibold">
          <Switch checked={data.require_agent_code} disabled={!data.can_edit || busy} onChange={toggle} label="Require an agent code" />
          Require an agent code to register
          {!data.can_edit && <span className="text-xs font-normal text-muted-foreground">(only a superuser can change this)</span>}
        </div>
      )}
    </Panel>
  );
}
