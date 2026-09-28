'use client';

import { GiRocketFlight, GiPokerHand } from 'react-icons/gi';
import { FaFire } from 'react-icons/fa';
import { GameRow } from '@/components/game-row';
import { useFavorites } from '@/lib/use-favorites';
import type { Game } from '@/lib/casino';

/** Lobby teaser shelves; the full browse lives at /casino. */
export function PopularGames({ games }: { games: Game[] }) {
  const { favorites, toggleFavorite } = useFavorites();
  const allIds = games.map((g) => g.id);
  const shared = { allIds, favorites, onToggleFavorite: toggleFavorite };
  const instant = games.filter((g) => g.category === 'crash' || g.category === 'instant');
  const live = games.filter((g) => g.category === 'live' || g.category === 'table');

  return (
    <div className="space-y-8">
      <GameRow title="Popular games" icon={FaFire} games={games.slice(0, 16)} seeAllHref="/casino" {...shared} />
      <GameRow title="Crash & instant" icon={GiRocketFlight} games={instant} seeAllHref="/casino?category=crash" {...shared} />
      <GameRow title="Live & table games" icon={GiPokerHand} games={live} seeAllHref="/casino?category=live" {...shared} />
    </div>
  );
}
