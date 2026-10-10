import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';
import { AccountShell } from './account-shell';

// Private: a player's own account pages never appear in search results.
export const metadata: Metadata = { title: { default: 'My account', template: '%s | My account' }, ...noIndex };

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <AccountShell>{children}</AccountShell>;
}
