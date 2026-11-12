import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';

export const metadata: Metadata = { title: 'Community chat', alternates: { canonical: '/chat' }, ...noIndex };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
