'use client';

import { useEffect, useState } from 'react';
import { BsBellFill, BsCheckCircleFill, BsStarFill, BsPlayFill, BsXLg } from 'react-icons/bs';
import Link from 'next/link';
import { gameHref, tileArt, onlineCount, type Game, type GameTag } from '@/lib/casino';
import { useWaitlist } from '@/lib/waitlist';

const TAG_STYLE: Record<'LIVE' | 'HOT' | 'NEW', string> = {
  LIVE: 'bg-live text-white',
  HOT: 'bg-gold text-gold-foreground',
  NEW: 'bg-secondary text-secondary-foreground',
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
  if (game.coming_soon) return <ComingSoonTile game={game} initial={initial} />;

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
        <p className="truncate text-xs font-extrabold leading-tight text-white sm:text-[13px]">{game.name}</p>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] font-semibold text-white/70">
          <span className="truncate">{game.provider}</span>
          {showRtp && <span className="ml-auto hidden shrink-0 tabular-nums sm:inline">RTP {parseFloat(game.rtp).toFixed(1)}%</span>}
        </div>
        <p className="mt-1 flex items-center gap-1 text-[10px] font-semibold text-white/60">
          <span className="h-1.5 w-1.5 rounded-full bg-win" />
          {onlineCount(game.slug).toLocaleString()} playing
        </p>
      </div>
    </Link>
  );
}


/** A game that isn't playable yet: tapping it says so and offers to tell the player when it is. */
function ComingSoonTile({ game, initial }: { game: Game; initial: string }) {
  const [open, setOpen] = useState(false);
  const { ids } = useWaitlist();
  const waiting = ids.has(game.id);
  const studio = game.provider && game.provider !== 'TBA' ? game.provider : 'Coming soon';
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group relative block aspect-[3/4] w-full overflow-hidden rounded-xl bg-card text-left shadow-[0_4px_16px_rgba(0,0,0,0.18)] ring-1 ring-border transition-transform duration-200 hover:-translate-y-1"
        style={!game.image_url ? { background: tileArt(game.slug) } : undefined}
        aria-label={`${game.name}: coming soon`}
      >
        {game.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={game.image_url} alt="" loading="lazy" className="h-full w-full object-cover opacity-80" />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center pb-10 text-7xl font-black text-white/15">{initial}</span>
        )}
        <span className="absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[9.5px] font-extrabold tracking-wider text-white backdrop-blur">
          SOON
        </span>
        {waiting && (
          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-win text-win-foreground" title="We’ll notify you">
            <BsBellFill size={12} />
          </span>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/55 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          <span className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-bold text-white backdrop-blur">Coming soon</span>
        </div>
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-2.5 pt-8">
          <p className="truncate text-xs font-extrabold leading-tight text-white sm:text-[13px]">{game.name}</p>
          <p className="mt-0.5 truncate text-[10.5px] font-semibold text-white/70">{studio}</p>
        </div>
      </button>
      {open && <ComingSoonDialog game={game} onClose={() => setOpen(false)} />}
    </>
  );
}

function ComingSoonDialog({ game, onClose }: { game: Game; onClose: () => void }) {
  const { ids, set, signedIn } = useWaitlist();
  const waiting = ids.has(game.id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function toggle() {
    setBusy(true); setError('');
    const err = await set(game.id, !waiting);
    setBusy(false);
    if (err && err !== 'login') setError(err);
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/60 p-3 backdrop-blur-sm sm:items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`${game.name} is coming soon`} onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm overflow-hidden rounded-2xl border border-border bg-background shadow-2xl">
        <div className="relative h-28" style={{ background: tileArt(game.slug) }}>
          <button onClick={onClose} aria-label="Close" className="absolute right-2 top-2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60">
            <BsXLg size={12} />
          </button>
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-4">
            <p className="text-lg font-extrabold text-white">{game.name}</p>
            {game.provider && game.provider !== 'TBA' && <p className="text-xs font-semibold text-white/70">{game.provider}</p>}
          </div>
        </div>
        <div className="space-y-4 p-5">
          <div>
            <p className="font-extrabold">Coming soon</p>
            <p className="mt-1 text-sm text-muted-foreground">
              We’re getting {game.name} ready. {waiting ? 'We’ll notify you the moment it’s live.' : 'Tap Notify me and we’ll tell you as soon as it’s live.'}
            </p>
          </div>
          {error && <p className="text-sm text-live">{error}</p>}
          {!signedIn ? (
            <Link href="/login?next=/casino" className="flex w-full items-center justify-center gap-2 rounded-xl bg-secondary py-3 text-sm font-bold text-secondary-foreground">
              <BsBellFill size={13} /> Log in to get notified
            </Link>
          ) : waiting ? (
            <button onClick={toggle} disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-win/40 bg-win/10 py-3 text-sm font-bold text-win disabled:opacity-60">
              <BsCheckCircleFill size={14} /> We’ll notify you · tap to cancel
            </button>
          ) : (
            <button onClick={toggle} disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-secondary py-3 text-sm font-bold text-secondary-foreground disabled:opacity-60">
              <BsBellFill size={13} /> Notify me
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
