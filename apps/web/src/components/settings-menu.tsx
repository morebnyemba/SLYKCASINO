'use client';

import { useState } from 'react';
import { BsMoonStarsFill, BsSunFill, BsGearFill, BsCheck } from 'react-icons/bs';
import { ACCENT_OPTIONS, useSettings, type OddsFormat } from '@/lib/settings-context';

const ODDS_FORMATS: { id: OddsFormat; label: string }[] = [
  { id: 'decimal', label: 'Decimal' },
  { id: 'fractional', label: 'Fractional' },
  { id: 'american', label: 'American' },
];

/** Quick light/dark toggle — always visible in the header, on every screen. */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggleTheme } = useSettings();
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className={`flex h-9 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white ${className}`}
    >
      {theme === 'dark' ? <BsSunFill size={14} /> : <BsMoonStarsFill size={14} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  );
}

/** Gear-icon dropdown: odds format, accent colour, live-feed toggle. */
export function SettingsMenu() {
  const { oddsFormat, setOddsFormat, accent, setAccent, showLiveFeed, setShowLiveFeed } = useSettings();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Preferences"
        title="Preferences"
        className="flex h-9 w-9 items-center justify-center rounded-md text-white/80 transition-colors hover:bg-white/10 hover:text-white"
      >
        <BsGearFill size={15} />
      </button>

      {open && (
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}>
          <div
            className="absolute right-4 top-14 z-50 w-64 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Preferences</p>

            <div className="mb-4">
              <p className="mb-1.5 text-xs text-muted-foreground">Odds format</p>
              <div className="flex gap-1 rounded-md bg-muted p-1">
                {ODDS_FORMATS.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setOddsFormat(f.id)}
                    className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                      oddsFormat === f.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <p className="mb-1.5 text-xs text-muted-foreground">Accent colour</p>
              <div className="flex gap-2">
                {ACCENT_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    onClick={() => setAccent(opt.hex)}
                    aria-label={opt.label}
                    title={opt.label}
                    className="flex h-7 w-7 items-center justify-center rounded-full transition-transform hover:scale-110"
                    style={{
                      backgroundColor: opt.hex,
                      boxShadow: accent === opt.hex ? `0 0 0 2px var(--card), 0 0 0 4px ${opt.hex}` : 'none',
                    }}
                  >
                    {accent === opt.hex && <BsCheck size={16} className="text-white drop-shadow" />}
                  </button>
                ))}
              </div>
            </div>

            <label className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
              Show live odds feed
              <button
                onClick={() => setShowLiveFeed(!showLiveFeed)}
                role="switch"
                aria-checked={showLiveFeed}
                className={`relative h-5 w-9 rounded-full transition-colors ${showLiveFeed ? 'bg-primary' : 'bg-muted'}`}
              >
                <span
                  className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    showLiveFeed ? 'translate-x-[18px]' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
