'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { BsSearch } from 'react-icons/bs';
import { GameTile } from '@/components/game-tile';
import { CASINO_CATEGORIES, gameTag, loadFavorites, saveFavorites, type Game } from '@/lib/casino';

/** Lobby teaser grid: category chips + search over a slice of games, full browse lives at /casino. */
export function PopularGames({ games }: { games: Game[] }) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [favorites, setFavorites] = useState<Set<string>>(() => loadFavorites());

  const visibleCategories = useMemo(() => {
    const present = new Set(games.map((g) => g.category).filter(Boolean));
    return CASINO_CATEGORIES.filter((c) => c.value === 'all' || present.has(c.value));
  }, [games]);

  const filtered = useMemo(() => {
    let list = games.filter((g) => g.name.toLowerCase().includes(search.toLowerCase()));
    if (category !== 'all') list = list.filter((g) => g.category === category);
    return list.slice(0, 12);
  }, [games, search, category]);

  function toggleFavorite(slug: string) {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug); else next.add(slug);
      saveFavorites(next);
      return next;
    });
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Popular games</h2>
          <p className="text-sm text-muted-foreground">Slots, live tables, and instant wins.</p>
        </div>
        <Link href="/casino" className="text-sm font-medium text-secondary hover:underline">
          View all games
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {visibleCategories.map((c) => (
          <button
            key={c.value}
            onClick={() => setCategory(c.value)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              category === c.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent/10'
            }`}
          >
            {c.label}
          </button>
        ))}
        <div className="relative ml-auto min-w-[180px] flex-1 sm:flex-none">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search games…"
            className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      {filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">No games match your filters.</p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {filtered.map((game) => (
          <GameTile
            key={game.slug}
            game={game}
            tag={gameTag(game, games.map((g) => g.id))}
            isFavorite={favorites.has(game.slug)}
            onToggleFavorite={toggleFavorite}
            showRtp={false}
          />
        ))}
      </div>
    </section>
  );
}
