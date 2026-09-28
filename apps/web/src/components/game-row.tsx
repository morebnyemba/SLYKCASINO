'use client';

import { useRef } from 'react';
import Link from 'next/link';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { GameTile } from '@/components/game-tile';
import { gameTag, type Game } from '@/lib/casino';

/**
 * A titled horizontal shelf of game tiles with "See all" and scroll arrows —
 * the standard lobby layout on casino sites.
 */
export function GameRow({
  title, icon: Icon, games, allIds, favorites, onToggleFavorite, seeAllHref, onSeeAll,
}: {
  title: string;
  icon?: IconType;
  games: Game[];
  /** Ids across the whole catalogue, for the NEW badge. */
  allIds: number[];
  favorites: Set<string>;
  onToggleFavorite: (slug: string) => void;
  seeAllHref?: string;
  onSeeAll?: () => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);

  function scrollBy(dir: 1 | -1) {
    const track = trackRef.current;
    if (track) track.scrollBy({ left: dir * track.clientWidth * 0.85, behavior: 'smooth' });
  }

  if (games.length === 0) return null;

  const seeAllClass = 'rounded-lg px-2.5 py-1.5 text-xs font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground';

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        {Icon && <Icon size={18} className="text-secondary" />}
        <h2 className="text-base font-extrabold sm:text-lg">{title}</h2>
        <span className="text-xs font-semibold text-muted-foreground">{games.length}</span>
        <div className="ml-auto flex items-center gap-1">
          {seeAllHref ? (
            <Link href={seeAllHref} className={seeAllClass}>See all</Link>
          ) : onSeeAll ? (
            <button onClick={onSeeAll} className={seeAllClass}>See all</button>
          ) : null}
          <button
            onClick={() => scrollBy(-1)}
            aria-label={`Scroll ${title} left`}
            className="hidden h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground sm:flex"
          >
            <FaChevronLeft size={11} />
          </button>
          <button
            onClick={() => scrollBy(1)}
            aria-label={`Scroll ${title} right`}
            className="hidden h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground sm:flex"
          >
            <FaChevronRight size={11} />
          </button>
        </div>
      </div>
      <div
        ref={trackRef}
        className="no-scrollbar -mx-3 flex snap-x gap-3 overflow-x-auto scroll-smooth px-3 pb-1 sm:mx-0 sm:px-0"
      >
        {games.map((game) => (
          <div key={game.slug} className="w-[128px] shrink-0 snap-start sm:w-[150px] xl:w-[164px]">
            <GameTile
              game={game}
              tag={gameTag(game, allIds)}
              isFavorite={favorites.has(game.slug)}
              onToggleFavorite={onToggleFavorite}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
