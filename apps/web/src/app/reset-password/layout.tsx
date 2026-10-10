import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';

export const metadata: Metadata = { title: 'Reset password', alternates: { canonical: '/reset-password' }, ...noIndex };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
