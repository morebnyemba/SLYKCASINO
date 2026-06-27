import { AuthGuard } from '@/components/auth-guard';
import { Sidebar } from '@/components/sidebar';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="grid min-h-screen grid-cols-[224px_1fr] bg-background">
        <Sidebar />
        <main className="overflow-auto p-7">{children}</main>
      </div>
    </AuthGuard>
  );
}
