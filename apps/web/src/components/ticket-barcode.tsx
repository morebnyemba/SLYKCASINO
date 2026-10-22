import { code39Bars } from '@/lib/barcode';

/**
 * A ticket's barcode with its code printed underneath, grouped for reading out
 * (K7PQ2 MXH9D). Always black on white with quiet zones, in either theme, so
 * scanners can read it off a screen.
 */
export function TicketBarcode({ code, className = '' }: { code: string; className?: string }) {
  const { bars, width } = code39Bars(code);
  const quiet = 10;
  const total = width + quiet * 2;
  return (
    <figure className={`rounded-xl bg-white px-3 pb-2 pt-3 text-black ${className}`}>
      <svg viewBox={`0 0 ${total} 40`} preserveAspectRatio="none" className="h-16 w-full" role="img" aria-label={`Barcode for ticket ${code}`}>
        {bars.map(([x, w], i) => <rect key={i} x={x + quiet} y={0} width={w} height={40} fill="#000" />)}
      </svg>
      <figcaption className="mt-1.5 text-center font-mono text-sm font-bold tracking-[0.3em]">
        {code.slice(0, 5)} {code.slice(5)}
      </figcaption>
    </figure>
  );
}
