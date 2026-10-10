import type { Metadata } from 'next';
import { social } from '@/lib/seo';

const meta = {
  title: 'Aviator — play the crash game online',
  description: 'Play BetBlits Aviator: watch the plane climb, cash out before it flies away. Two bets per round, auto cash-out, '
    + 'provably fair results and instant EcoCash payouts. 18+, play responsibly.',
  alternates: { canonical: '/aviator' },
  keywords: ['Aviator', 'Aviator game', 'crash game', 'Aviator Zimbabwe', 'BetBlits Aviator'],
};

export const metadata: Metadata = { ...meta, ...social(meta.title, meta.description, meta.alternates.canonical) };

export default function AviatorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
