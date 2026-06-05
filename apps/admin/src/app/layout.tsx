import type { Metadata } from 'next';
import './globals.css';
import { Sidebar } from '@/components/sidebar';

export const metadata: Metadata = {
  title: 'SLYK Casino — Admin',
  description: 'Operator command center: livechat, promotions, live betting feeds',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <div className="grid min-h-screen grid-cols-[224px_1fr]">
          <Sidebar />
          <main className="overflow-auto p-7">{children}</main>
        </div>
      </body>
    </html>
  );
}
