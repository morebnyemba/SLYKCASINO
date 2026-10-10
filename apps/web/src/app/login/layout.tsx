import type { Metadata } from 'next';
import { social } from '@/lib/seo';

const meta = { title: 'Log in', description: 'Log in to BetBlits to bet on football and more with live odds, cash out and Aviator.', alternates: { canonical: '/login' } };

export const metadata: Metadata = { ...meta, ...social(meta.title, meta.description, meta.alternates.canonical) };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
