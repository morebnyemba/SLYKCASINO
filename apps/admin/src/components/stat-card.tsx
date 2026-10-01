import type { IconType } from 'react-icons';
import { Card, CardContent } from '@slyk/ui/components/card';

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon?: IconType;
}) {
  return (
    <Card className="rounded-2xl border-gold/15">
      <CardContent className="flex items-start justify-between pt-6">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="my-1 text-3xl font-bold">{value}</div>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>
        {Icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold/15 text-gold">
            <Icon size={15} />
          </span>
        )}
      </CardContent>
    </Card>
  );
}
