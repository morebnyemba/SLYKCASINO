'use client';

import { BsStarFill, BsPlayFill } from 'react-icons/bs';
import Link from 'next/link';
import { gameHref, tileArt, onlineCount, type Game, type GameTag } from '@/lib/casino';

const TAG_STYLE: Record<'LIVE' | 'HOT' | 'NEW', string> = {
  LIVE: 'bg-live text-white',
  HOT: 'bg-gold text-gold-foreground',
  NEW: 'bg-secondary text-white',
};

/** Portrait game card: artwork with name/provider overlay; play button and RTP reveal on hover. */
export function GameTile({
  game,
  tag = null,
  isFavorite,
  onToggleFavorite,
  showRtp = true,
}: {
  game: Game;
  tag?: GameTag;
  isFavorite: boolean;
  onToggleFavorite: (slug: string) => void;
  showRtp?: boolean;
}) {
  const initial = (game.name.replace(/[^A-Za-z]/g, '').charAt(0) || 'S').toUpperCase();

  return (
    <Link
      href={gameHref(game)}
      className="group relative block aspect-[3/4] overflow-hidden rounded-xl bg-card shadow-[0_4px_16px_rgba(0,0,0,0.18)] ring-1 ring-border transition-transform duration-200 hover:-translate-y-1"
      style={!game.image_url ? { background: tileArt(game.slug) } : undefined}
    >
      {game.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={game.image_url}
          alt={game.name}
          loading="lazy"
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      ) : (
        <span className="absolute inset-0 flex items-center justify-center pb-10 text-7xl font-black text-white/15">
          {initial}
        </span>
      )}

      {tag && (
        <span className={`absolute left-2 top-2 rounded px-1.5 py-0.5 text-[9.5px] font-extrabold tracking-wider ${TAG_STYLE[tag]}`}>
          {tag}
        </span>
      )}

      <button
        onClick={(e) => {
          e.preventDefault();
          onToggleFavorite(game.slug);
        }}
        aria-label={isFavorite ? 'Remove from favourites' : 'Add to favourites'}
        aria-pressed={isFavorite}
        className={`absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-black/40 backdrop-blur-sm transition-all ${
          isFavorite ? 'text-gold' : 'text-white/80 hover:text-gold sm:opacity-0 sm:group-hover:opacity-100'
        }`}
      >
        <BsStarFill size={12} />
      </button>

      {/* Hover: dim + play button */}
      <div className="absolute inset-0 flex items-center justify-center bg-black/55 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        <span className="flex h-12 w-12 scale-90 items-center justify-center rounded-full bg-win text-win-foreground shadow-xl transition-transform duration-200 group-hover:scale-100">
          <BsPlayFill size={26} className="translate-x-px" />
        </span>
      </div>

      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-2.5 pt-8">
        <p className="truncate text-[13px] font-extrabold leading-tight text-white">{game.name}</p>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] font-semibold text-white/70">
          <span className="truncate">{game.provider}</span>
          {showRtp && <span className="ml-auto shrink-0 tabular-nums">RTP {parseFloat(game.rtp).toFixed(1)}%</span>}
        </div>
        <p className="mt-1 flex items-center gap-1 text-[10px] font-semibold text-white/60">
          <span className="h-1.5 w-1.5 rounded-full bg-win" />
          {onlineCount(game.slug).toLocaleString()} playing
        </p>
      </div>
    </Link>
  );
}
