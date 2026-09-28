'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

const COLLAPSED_KEY = 'slyk:sidebar-collapsed';

interface ShellContextValue {
  /** Desktop left rail shows icons only. */
  collapsed: boolean;
  toggleCollapsed: () => void;
  /** Mobile navigation drawer. */
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
}

const ShellContext = createContext<ShellContextValue | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSED_KEY) === '1');
    } catch {
      /* storage may be unavailable */
    }
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      try {
        window.localStorage.setItem(COLLAPSED_KEY, prev ? '0' : '1');
      } catch {
        /* storage may be unavailable */
      }
      return !prev;
    });
  }, []);

  return (
    <ShellContext.Provider value={{ collapsed, toggleCollapsed, menuOpen, setMenuOpen }}>
      {children}
    </ShellContext.Provider>
  );
}

export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error('useShell must be used within a ShellProvider');
  return ctx;
}
