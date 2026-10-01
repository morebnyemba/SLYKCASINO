import * as React from 'react';
import { cn } from '../lib/utils';

/**
 * A ring spinner in the current text colour. Size in px; `label` is announced to
 * screen readers (the spinner itself is decorative).
 */
export function Spinner({
  size = 16, className, label = 'Loading',
}: { size?: number; className?: string; label?: string }) {
  return (
    <span role="status" aria-label={label} className={cn('inline-flex shrink-0', className)}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
        className="animate-spin"
      >
        <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="3" opacity="0.2" />
        <path d="M21.5 12a9.5 9.5 0 0 0-9.5-9.5" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </span>
  );
}

/** A centred spinner with an optional caption, for sections or pages that are loading. */
export function LoadingState({
  label, className, size = 28,
}: { label?: string; className?: string; size?: number }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-10 text-muted-foreground', className)}>
      <Spinner size={size} className="text-secondary" label={label ?? 'Loading'} />
      {label && <p className="text-sm font-medium">{label}</p>}
    </div>
  );
}
