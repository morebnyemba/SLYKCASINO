import type { Metadata } from 'next';
import { social } from '@/lib/seo';

const meta = { title: 'Promotions & bonuses', description: 'Current BetBlits promotions: multi-bet bonuses, welcome offers and more. 18+, terms apply.', alternates: { canonical: '/promotions' } };

export const metadata: Metadata = { ...meta, ...social(meta.title, meta.description, meta.alternates.canonical) };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
