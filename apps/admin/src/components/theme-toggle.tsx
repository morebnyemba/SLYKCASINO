'use client';

import { BsMoonStarsFill, BsSunFill } from 'react-icons/bs';
import { useTheme } from '@/lib/theme-context';

/** Quick light/dark toggle, mirrors the apps/web settings-menu ThemeToggle. */
export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className={`flex items-center gap-1.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors hover:bg-white/10 ${className}`}
    >
      {theme === 'dark' ? <BsSunFill size={13} /> : <BsMoonStarsFill size={13} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  );
}
