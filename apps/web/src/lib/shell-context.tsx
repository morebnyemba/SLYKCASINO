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
  /** Global search overlay. */
  searchOpen: boolean;
  setSearchOpen: (open: boolean) => void;
  /**
   * Desktop right rail (bet slip) — the player's explicit choice, or null to use
   * the page default (open on sports pages or when the slip has picks).
   */
  railPref: boolean | null;
  setRailPref: (open: boolean | null) => void;
}

const ShellContext = createContext<ShellContextValue | null>(null);

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [railPref, setRailPref] = useState<boolean | null>(null);

  // "/" or Ctrl/Cmd+K opens search from anywhere (except while typing in a field).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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
    <ShellContext.Provider value={{
      collapsed, toggleCollapsed, menuOpen, setMenuOpen, searchOpen, setSearchOpen, railPref, setRailPref,
    }}>
      {children}
    </ShellContext.Provider>
  );
}

export function useShell() {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error('useShell must be used within a ShellProvider');
  return ctx;
}
