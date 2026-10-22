import type { Metadata } from 'next';
import { noIndex } from '@/lib/seo';
import { CheckTicket } from './check-ticket';

export const metadata: Metadata = { title: 'Check a ticket', ...noIndex };

export default function CheckTicketPage() {
  return <CheckTicket />;
}
