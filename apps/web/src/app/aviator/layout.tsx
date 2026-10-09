import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'Aviator — BetBlits' };

export default function AviatorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
