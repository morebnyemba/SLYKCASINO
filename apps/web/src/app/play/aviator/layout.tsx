import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';

// The bare game shown inside the /aviator frame — /aviator is the page to index.
export const metadata: Metadata = { title: 'Aviator', ...noIndex };

export default function AviatorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
