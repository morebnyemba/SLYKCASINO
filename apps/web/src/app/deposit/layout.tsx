import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';

export const metadata: Metadata = { title: 'Deposit', alternates: { canonical: '/deposit' }, ...noIndex };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
