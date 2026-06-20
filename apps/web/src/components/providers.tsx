'use client';

import { AuthProvider } from '@/lib/auth-context';
import { BetslipProvider } from '@/lib/betslip-context';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <BetslipProvider>{children}</BetslipProvider>
    </AuthProvider>
  );
}
