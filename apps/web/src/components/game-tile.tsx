'use client';

import { BsStarFill } from 'react-icons/bs';
import Link from 'next/link';
import { gameHref, tileArt, onlineCount, type Game, type GameTag } from '@/lib/casino';

const TAG_STYLE: Record<'LIVE' | 'HOT' | 'NEW', string> = {
  LIVE: 'bg-live text-white',
  HOT: 'bg-gold text-gold-foreground',
  NEW: 'bg-secondary text-white',
};

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
      className="group relative block overflow-hidden rounded-2xl shadow-[0_6px_22px_rgba(0,0,0,0.15)] transition-transform duration-150 hover:-translate-y-1"
    >
      <div className="relative aspect-[3/4]" style={!game.image_url ? { background: tileArt(game.slug) } : undefined}>
        {game.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={game.image_url} alt={game.name} className="h-full w-full object-cover" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center font-black text-7xl text-white/10">
            {initial}
          </span>
        )}

        {tag && (
          <span className={`absolute left-2 top-2 rounded-md px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider ${TAG_STYLE[tag]}`}>
            {tag}
          </span>
        )}

        <button
          onClick={(e) => {
            e.preventDefault();
            onToggleFavorite(game.slug);
          }}
          aria-label="Toggle favorite"
          className={`absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-lg bg-black/30 backdrop-blur-sm transition-colors ${
            isFavorite ? 'text-gold' : 'text-white/80 hover:text-gold'
          }`}
        >
          <BsStarFill size={13} />
        </button>

        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/85 to-transparent p-2.5">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white/90">
            <span className="h-1.5 w-1.5 rounded-full bg-win" />
            {onlineCount(game.slug)}
          </span>
          <span className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-2 py-1 text-[11px] font-extrabold text-gold-foreground">
            Play
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 bg-card p-2.5">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-bold text-card-foreground">{game.name}</p>
          <p className="text-[11px] text-muted-foreground">{game.provider}</p>
        </div>
        {showRtp && (
          <span className="shrink-0 rounded-md border border-border bg-chip px-1.5 py-1 text-[10.5px] font-bold tabular-nums text-muted-foreground">
            RTP {game.rtp}%
          </span>
        )}
      </div>
    </Link>
  );
}
