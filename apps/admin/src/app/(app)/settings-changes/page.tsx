'use client';

import { BsShieldCheck } from 'react-icons/bs';
import { PageHeader } from '@/components/console/ui';
import { SettingsChangesPanel } from '@/components/revenue/settings-changes';

export default function SettingsChangesPage() {
  return (
    <div className="space-y-6">
      <PageHeader icon={BsShieldCheck} eyebrow="Money" title="Revenue-share changes"
        description="No partner can change the revenue-share settings alone — shares, wallet holders, the founder or the start date. Each save waits here until every partner co-signs it, then applies exactly as it was asked." />
      <SettingsChangesPanel />
    </div>
  );
}
