'use client';

import { AuthProvider } from '@/lib/auth-context';
import { BetslipProvider } from '@/lib/betslip-context';
import { SettingsProvider } from '@/lib/settings-context';
import { ShellProvider } from '@/lib/shell-context';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SettingsProvider>
      <AuthProvider>
        <BetslipProvider>
          <ShellProvider>{children}</ShellProvider>
        </BetslipProvider>
      </AuthProvider>
    </SettingsProvider>
  );
}
