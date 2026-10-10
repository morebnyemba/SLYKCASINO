import type { Metadata } from 'next';
import { social } from '@/lib/seo';

const meta = { title: 'Sign up', description: 'Create your free BetBlits account in seconds — bet on football, basketball and more with live odds, cash out and fast EcoCash payments. 18+.', alternates: { canonical: '/register' } };

export const metadata: Metadata = { ...meta, ...social(meta.title, meta.description, meta.alternates.canonical) };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
