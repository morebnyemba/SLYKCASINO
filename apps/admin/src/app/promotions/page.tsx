import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Button } from '@slyk/ui/components/button';
import { Badge } from '@slyk/ui/components/badge';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Promotions — SLYK Admin' };

interface Promo {
  id: string | number;
  name: string;
  kind: string;
  active: boolean;
  ends_at?: string;
}

export default async function PromotionsPage() {
  const data = await apiGet<Promo>('/promotions/');
  const promos = (data.results ?? []) as Promo[];
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Promotions</h1>
        <Button>+ New Promotion</Button>
      </div>
      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Active</TableHead>
              <TableHead>Ends</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {promos.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground">No promotions yet.</TableCell></TableRow>
            )}
            {promos.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.kind}</TableCell>
                <TableCell>{p.active ? <Badge variant="success">active</Badge> : <Badge variant="secondary">off</Badge>}</TableCell>
                <TableCell>{p.ends_at || '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
