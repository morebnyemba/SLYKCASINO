import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';
import { TicketView } from './ticket-view';

// A ticket is private to whoever holds its code: never indexed.
export const metadata: Metadata = { title: 'Ticket', ...noIndex };

type PageProps = { params: Promise<{ code: string }> };

export default async function TicketPage({ params }: PageProps) {
  const { code } = await params;
  return <TicketView code={code} />;
}
