'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type ThemeMode = 'dark' | 'light';
export type OddsFormat = 'decimal' | 'fractional' | 'american';

export interface AccentOption {
  id: string;
  label: string;
  hex: string;
}

// Mirrors the accent swatches offered in the Sportsbook design prototype.
export const ACCENT_OPTIONS: AccentOption[] = [
  { id: 'indigo', label: 'Indigo', hex: '#6C63E8' },
  { id: 'royal', label: 'Royal blue', hex: '#4338CA' },
  { id: 'gold', label: 'Gold', hex: '#E6B84C' },
  { id: 'emerald', label: 'Emerald', hex: '#36D399' },
  { id: 'coral', label: 'Coral', hex: '#FF5260' },
];

interface Settings {
  theme: ThemeMode;
  oddsFormat: OddsFormat;
  accent: string;
  showLiveFeed: boolean;
}

const DEFAULT_SETTINGS: Settings = {
  theme: 'dark',
  oddsFormat: 'decimal',
  accent: ACCENT_OPTIONS[0].hex,
  showLiveFeed: true,
};

const STORAGE_KEY = 'slyk:settings';

interface SettingsContextValue extends Settings {
  setTheme: (t: ThemeMode) => void;
  toggleTheme: () => void;
  setOddsFormat: (f: OddsFormat) => void;
  setAccent: (hex: string) => void;
  setShowLiveFeed: (v: boolean) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

function loadStored(): Settings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setSettings(loadStored());
    setHydrated(true);
  }, []);

  // Reflect theme + accent onto <html> so CSS custom properties cascade everywhere.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = settings.theme;
    root.style.setProperty('--secondary', settings.accent);
    root.style.setProperty('--ring', settings.accent);
  }, [settings.theme, settings.accent]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* storage may be unavailable */
    }
  }, [settings, hydrated]);

  const setTheme = useCallback((theme: ThemeMode) => setSettings((s) => ({ ...s, theme })), []);
  const toggleTheme = useCallback(
    () => setSettings((s) => ({ ...s, theme: s.theme === 'dark' ? 'light' : 'dark' })),
    [],
  );
  const setOddsFormat = useCallback((oddsFormat: OddsFormat) => setSettings((s) => ({ ...s, oddsFormat })), []);
  const setAccent = useCallback((accent: string) => setSettings((s) => ({ ...s, accent })), []);
  const setShowLiveFeed = useCallback((showLiveFeed: boolean) => setSettings((s) => ({ ...s, showLiveFeed })), []);

  return (
    <SettingsContext.Provider
      value={{ ...settings, setTheme, toggleTheme, setOddsFormat, setAccent, setShowLiveFeed }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used within a SettingsProvider');
  return ctx;
}

// --- Odds formatting -------------------------------------------------------

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b);
}

/** Decimal odds -> reduced fraction string, e.g. 2.5 -> "3/2". */
function toFractional(decimal: number): string {
  const value = decimal - 1;
  if (value <= 0) return '0/1';
  const denominator = 1000;
  let numerator = Math.round(value * denominator);
  let den = denominator;
  const divisor = gcd(numerator, den) || 1;
  numerator /= divisor;
  den /= divisor;
  return `${numerator}/${den}`;
}

/** Decimal odds -> American moneyline, e.g. 2.5 -> "+150", 1.5 -> "-200". */
function toAmerican(decimal: number): string {
  if (decimal >= 2) return `+${Math.round((decimal - 1) * 100)}`;
  return `${Math.round(-100 / (decimal - 1))}`;
}

export function formatOdds(decimal: number, format: OddsFormat): string {
  if (!Number.isFinite(decimal) || decimal <= 1) return decimal.toFixed(2);
  switch (format) {
    case 'fractional':
      return toFractional(decimal);
    case 'american':
      return toAmerican(decimal);
    default:
      return decimal.toFixed(2);
  }
}
