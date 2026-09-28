'use client';

import { useCallback, useEffect, useState } from 'react';
import { loadFavorites, saveFavorites } from '@/lib/casino';

/** Favourite game slugs, persisted in localStorage. Loaded after mount to keep SSR markup stable. */
export function useFavorites() {
  const [favorites, setFavorites] = useState<Set<string>>(() => new Set());

  useEffect(() => { setFavorites(loadFavorites()); }, []);

  const toggleFavorite = useCallback((slug: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug); else next.add(slug);
      saveFavorites(next);
      return next;
    });
  }, []);

  return { favorites, toggleFavorite };
}
