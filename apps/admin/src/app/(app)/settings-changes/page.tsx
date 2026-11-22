'use client';

import { BsShieldCheck } from 'react-icons/bs';
import { PageHeader } from '@/components/console/ui';
import { SettingsChangesPanel } from '@/components/revenue/settings-changes';
import { RevenueLockGate } from '@/components/revenue/revenue-lock';

export default function SettingsChangesPage() {
  return (
    <div className="space-y-6">
      <PageHeader icon={BsShieldCheck} eyebrow="Money" title="Revenue-share changes"
        description="Revenue-share settings now change at once, with no co-signing. This page keeps the history of changes that were sent for co-signing before." />
      <RevenueLockGate>
        <SettingsChangesPanel />
      </RevenueLockGate>
    </div>
  );
}
