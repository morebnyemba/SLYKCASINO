'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import type { IconType } from 'react-icons';
import { BsXLg } from 'react-icons/bs';
import { Spinner } from '@slyk/ui/components/spinner';

/** Join class names, skipping falsy ones. */
export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ');
}

/** Page title block: icon, title, one-line description and the page's main actions. */
export function PageHeader({ icon: Icon, eyebrow, title, description, actions }: {
  icon?: IconType;
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 items-start gap-3.5">
        {Icon && (
          <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-secondary to-primary text-white shadow-lg shadow-secondary/25 ring-1 ring-white/10">
            <Icon size={18} />
          </span>
        )}
        <div className="min-w-0">
          {eyebrow && <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-secondary">{eyebrow}</p>}
          <h1 className="truncate text-[26px] font-extrabold leading-tight tracking-tight">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A card section with an optional header row. */
export function Panel({ title, description, actions, children, className, bodyClassName, padded = true }: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx('overflow-hidden rounded-2xl border border-border/70 bg-card shadow-sm shadow-black/5', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-bold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx(padded && 'p-5', bodyClassName)}>{children}</div>
    </section>
  );
}

const TONES = {
  indigo: 'from-secondary/25 to-secondary/5 text-secondary',
  green: 'from-win/25 to-win/5 text-win',
  red: 'from-live/25 to-live/5 text-live',
  gold: 'from-gold/25 to-gold/5 text-gold',
  slate: 'from-muted to-muted/40 text-muted-foreground',
} as const;
export type Tone = keyof typeof TONES;

/** KPI tile. Clickable when `href` is given. */
export function StatTile({ label, value, hint, icon: Icon, tone = 'indigo', href, loading }: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: IconType;
  tone?: Tone;
  href?: string;
  loading?: boolean;
}) {
  const body = (
    <div className="group relative h-full overflow-hidden rounded-2xl border border-border/70 bg-card p-4 shadow-sm shadow-black/5 transition-colors hover:border-secondary/50">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11.5px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon && (
          <span className={cx('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br', TONES[tone])}>
            <Icon size={15} />
          </span>
        )}
      </div>
      <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight tabular-nums">
        {loading ? <span className="inline-block h-7 w-16 animate-pulse rounded-md bg-muted" /> : value}
      </p>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

const BADGE_TONES: Record<string, string> = {
  green: 'bg-win/15 text-win ring-win/25',
  red: 'bg-live/15 text-live ring-live/25',
  gold: 'bg-gold/15 text-gold ring-gold/30',
  indigo: 'bg-secondary/15 text-secondary ring-secondary/25',
  slate: 'bg-muted text-muted-foreground ring-border',
};

export function Badge({ tone = 'slate', children, dot, className }: {
  tone?: keyof typeof BADGE_TONES; children: React.ReactNode; dot?: boolean; className?: string;
}) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset', BADGE_TONES[tone], className)}>
      {dot && <span className={cx('h-1.5 w-1.5 rounded-full bg-current', tone === 'red' && 'animate-pulse')} />}
      {children}
    </span>
  );
}

/** Accessible on/off switch. */
export function Switch({ checked, onChange, disabled, label }: {
  checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        'relative inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors disabled:opacity-50',
        checked ? 'bg-secondary' : 'bg-muted ring-1 ring-inset ring-border',
      )}
    >
      <span className={cx('inline-block h-[18px] w-[18px] rounded-full bg-white shadow transition-transform', checked ? 'translate-x-[19px]' : 'translate-x-[3px]')} />
    </button>
  );
}

/** Pill tabs with optional counts. */
export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { id: T; label: string; count?: number; tone?: 'red' }[];
}) {
  return (
    <div className="no-scrollbar flex gap-1 overflow-x-auto rounded-xl border border-border/70 bg-card p-1" role="tablist">
      {items.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors',
            value === t.id ? 'bg-secondary text-white shadow' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
          )}
        >
          {t.tone === 'red' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-live" />}
          {t.label}
          {t.count != null && (
            <span className={cx('rounded-full px-1.5 text-[10.5px] tabular-nums', value === t.id ? 'bg-white/20' : 'bg-muted')}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children, className }: {
  label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <label className={cx('block space-y-1.5', className)}>
      <span className="text-[12.5px] font-semibold text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[11.5px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

export const inputClass =
  'h-10 w-full rounded-xl border border-border bg-input/60 px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-secondary focus:ring-2 focus:ring-secondary/30 disabled:opacity-60';

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputClass, props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputClass, 'pr-8', props.className)} />;
}

const BUTTON_VARIANTS = {
  primary: 'bg-gradient-to-br from-secondary to-primary text-white shadow-md shadow-secondary/25 hover:brightness-110',
  outline: 'border border-border bg-card text-foreground hover:border-secondary/60 hover:bg-muted/60',
  ghost: 'text-muted-foreground hover:bg-muted hover:text-foreground',
  danger: 'border border-live/40 bg-live/10 text-live hover:bg-live/20',
  success: 'bg-win text-white shadow-md shadow-win/25 hover:brightness-110',
};

export function Btn({ variant = 'outline', size = 'md', busy, icon: Icon, children, className, ...props }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: keyof typeof BUTTON_VARIANTS; size?: 'sm' | 'md'; busy?: boolean; icon?: IconType;
  }) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={cx(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl font-semibold transition-all disabled:pointer-events-none disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm',
        BUTTON_VARIANTS[variant], className,
      )}
    >
      {busy ? <Spinner size={13} /> : Icon && <Icon size={size === 'sm' ? 12 : 14} />}
      {children}
    </button>
  );
}

export function EmptyState({ icon: Icon, title, children, action }: {
  icon?: IconType; title: string; children?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {Icon && (
        <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <Icon size={22} />
        </span>
      )}
      <p className="font-bold">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Inline result line for an action ("Saved", or an error). */
export function Notice({ tone = 'green', children, onClose }: {
  tone?: 'green' | 'red' | 'indigo'; children: React.ReactNode; onClose?: () => void;
}) {
  const tones = {
    green: 'border-win/30 bg-win/10 text-win',
    red: 'border-live/30 bg-live/10 text-live',
    indigo: 'border-secondary/30 bg-secondary/10 text-secondary',
  };
  return (
    <div className={cx('flex items-start gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium', tones[tone])} role="status">
      <span className="min-w-0 flex-1">{children}</span>
      {onClose && <button onClick={onClose} aria-label="Dismiss" className="opacity-70 hover:opacity-100"><BsXLg size={12} /></button>}
    </div>
  );
}

/** Right-hand slide-over for create/edit forms. */
export function Drawer({ open, onClose, title, description, children, footer }: {
  open: boolean; onClose: () => void; title: string; description?: string;
  children: React.ReactNode; footer?: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-lg flex-col border-l border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-start gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-extrabold">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground">
            <BsXLg size={14} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}

/** Shared table styles: `<table className={tableClass}>` with th/td helpers. */
export const tableClass = 'w-full text-sm';
export const thClass = 'whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-wide text-muted-foreground';
export const tdClass = 'px-4 py-3 align-middle';
export const trClass = 'border-t border-border/60 transition-colors hover:bg-muted/40';

export function Pager({ page, count, pageSize, onPage }: {
  page: number; count: number; pageSize: number; onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-border/60 px-4 py-3 text-xs text-muted-foreground">
      <span>{count.toLocaleString()} total · page {page} of {pages}</span>
      <div className="flex gap-2">
        <Btn size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Btn>
        <Btn size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Btn>
      </div>
    </div>
  );
}

/** Money with thousands separators and two decimals. */
export function money(v: string | number | null | undefined, currency = '$') {
  const n = Number(v ?? 0);
  return `${n < 0 ? '−' : ''}${currency}${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
