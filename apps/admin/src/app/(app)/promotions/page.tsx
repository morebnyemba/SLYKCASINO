'use client';

import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Promo {
  id: string | number;
  name: string;
  kind: string;
  active: boolean;
  ends_at?: string;
  bonus_amount?: string;
  wagering_multiplier?: number;
}

interface PromosResponse {
  results?: Promo[];
}

export default function PromotionsPage() {
  const { data, loading, error } = useApi<PromosResponse>('/promotions/');
  const promos = data?.results ?? [];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Promotions</h1>
      </div>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Bonus</TableHead>
              <TableHead>Wagering</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ends</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && (
              <TableRow><TableCell colSpan={6} className="text-muted-foreground">Loading…</TableCell></TableRow>
            )}
            {!loading && promos.length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-muted-foreground">No promotions yet. Create them in Django Admin.</TableCell></TableRow>
            )}
            {promos.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell>{p.kind}</TableCell>
                <TableCell>{p.bonus_amount ?? '—'}</TableCell>
                <TableCell>{p.wagering_multiplier != null ? `${p.wagering_multiplier}×` : '—'}</TableCell>
                <TableCell>
                  {p.active
                    ? <Badge variant="default">Active</Badge>
                    : <Badge variant="secondary">Off</Badge>}
                </TableCell>
                <TableCell className="text-muted-foreground">{p.ends_at ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
