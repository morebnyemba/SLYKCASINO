'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { BsSearch, BsStarFill, BsXCircleFill } from 'react-icons/bs';
import {
  GiCastle, GiRocketFlight, GiCherry, GiPokerHand, GiCardAceSpades, GiSoccerKick, GiLightningFrequency,
} from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { Carousel, CarouselItem } from '@/components/carousel';
import { GameTile } from '@/components/game-tile';
import { GameRow } from '@/components/game-row';
import { useApi } from '@/lib/use-api';
import { useFavorites } from '@/lib/use-favorites';
import { CASINO_HERO_IMAGES } from '@/lib/game-images';
import { CASINO_CATEGORIES as CATEGORIES, DEMO_GAMES, type Game, gameHref, gameTag, tileArt } from '@/lib/casino';

interface GamesResponse {
  results?: Game[];
  next?: string | null;
}

const CATEGORY_ICONS: Record<string, IconType> = {
  all: GiCastle,
  crash: GiRocketFlight,
  slots: GiCherry,
  live: GiPokerHand,
  table: GiCardAceSpades,
  virtual: GiSoccerKick,
  instant: GiLightningFrequency,
};

function CasinoLobby() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data, loading } = useApi<GamesResponse>('/casino/games/');
  const [extraGames, setExtraGames] = useState<Game[]>([]);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const apiGames = data?.results ?? [];
  const games = useMemo(() => (apiGames.length > 0 ? [...apiGames, ...extraGames] : DEMO_GAMES), [apiGames, extraGames]);
  const allIds = useMemo(() => games.map((g) => g.id), [games]);

  useEffect(() => {
    setNextPage(data?.next ?? null);
  }, [data]);

  async function loadMore() {
    if (!nextPage || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await fetch(nextPage);
      const json = (await res.json()) as GamesResponse;
      setExtraGames((prev) => [...prev, ...(json.results ?? [])]);
      setNextPage(json.next ?? null);
    } catch {
      setNextPage(null);
    }
    setLoadingMore(false);
  }

  // Category lives in the URL so sidebar links (/casino?category=slots) land on the right tab.
  const categoryParam = params.get('category') ?? 'all';
  const onlyFavorites = categoryParam === 'favorites';
  const category = onlyFavorites ? 'all' : categoryParam;

  function setCategory(value: string) {
    const q = new URLSearchParams(params.toString());
    if (value === 'all') q.delete('category'); else q.set('category', value);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  const [search, setSearch] = useState('');
  const [provider, setProvider] = useState('all');
  const [sort, setSort] = useState<'popular' | 'name' | 'rtp'>('popular');
  const { favorites, toggleFavorite } = useFavorites();

  const providers = useMemo(() => Array.from(new Set(games.map((g) => g.provider))).sort(), [games]);
  const visibleCategories = useMemo(() => {
    const present = new Set(games.map((g) => g.category).filter(Boolean));
    return CATEGORIES.filter((c) => c.value === 'all' || present.has(c.value));
  }, [games]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = games.filter((g) => !q || g.name.toLowerCase().includes(q) || g.provider.toLowerCase().includes(q));
    if (category !== 'all') list = list.filter((g) => g.category === category);
    if (provider !== 'all') list = list.filter((g) => g.provider === provider);
    if (onlyFavorites) list = list.filter((g) => favorites.has(g.slug));
    if (sort !== 'popular') {
      list = [...list].sort((a, b) => (
        sort === 'rtp' ? parseFloat(b.rtp) - parseFloat(a.rtp) : a.name.localeCompare(b.name)
      ));
    }
    return list;
  }, [games, search, category, provider, onlyFavorites, favorites, sort]);

  // Lobby view = shelves per category; any filter switches to a flat grid.
  const lobbyView = category === 'all' && !onlyFavorites && !search.trim() && provider === 'all' && sort === 'popular';
  const favoriteGames = games.filter((g) => favorites.has(g.slug));
  const topRtp = [...games].sort((a, b) => parseFloat(b.rtp) - parseFloat(a.rtp)).slice(0, 12);
  const heroGames = games.slice(0, CASINO_HERO_IMAGES.length);

  const tabClass = (active: boolean) =>
    `flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-[13px] font-bold transition-colors ${
      active ? 'bg-secondary text-white shadow' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
    }`;

  return (
    <div className="space-y-6">
      {heroGames.length > 0 && (
        <Carousel>
          {heroGames.map((g, i) => (
            <CarouselItem key={g.slug} className="w-[280px] sm:w-[380px]">
              <Link
                href={gameHref(g)}
                className="group relative block h-36 overflow-hidden rounded-2xl sm:h-44"
                style={{ background: tileArt(g.slug) }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={CASINO_HERO_IMAGES[i]}
                  alt=""
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                  className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
                <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/85 via-black/30 to-transparent p-4">
                  <span className="mb-1 w-fit rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white backdrop-blur">
                    Featured
                  </span>
                  <p className="text-lg font-extrabold text-white">{g.name}</p>
                  <p className="text-xs font-semibold text-white/70">{g.provider}</p>
                </div>
              </Link>
            </CarouselItem>
          ))}
        </Carousel>
      )}

      {/* Category tabs + search/filters */}
      <div className="sticky top-16 z-20 -mx-3 space-y-2 bg-background/95 px-3 py-2 backdrop-blur sm:mx-0 sm:px-0">
        <div className="no-scrollbar flex gap-1 overflow-x-auto rounded-2xl border border-border bg-card p-1">
          {visibleCategories.map((c) => {
            const Icon = CATEGORY_ICONS[c.value] ?? GiCastle;
            return (
              <button key={c.value} onClick={() => setCategory(c.value)} className={tabClass(!onlyFavorites && category === c.value)}>
                <Icon size={16} />
                {c.label}
              </button>
            );
          })}
          <button onClick={() => setCategory('favorites')} className={tabClass(onlyFavorites)}>
            <BsStarFill size={13} />
            Favourites
            {favorites.size > 0 && (
              <span className={`rounded-full px-1.5 text-[10px] ${onlyFavorites ? 'bg-white/20' : 'bg-muted'}`}>{favorites.size}</span>
            )}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search games or providers"
              aria-label="Search games"
              className="w-full rounded-xl border border-border bg-card py-2.5 pl-9 pr-9 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <BsXCircleFill size={13} />
              </button>
            )}
          </div>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            aria-label="Provider"
            className="rounded-xl border border-border bg-card px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="all">All providers</option>
            {providers.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as 'popular' | 'name' | 'rtp')}
            aria-label="Sort"
            className="rounded-xl border border-border bg-card px-3 py-2.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="popular">Popular</option>
            <option value="name">A–Z</option>
            <option value="rtp">Highest RTP</option>
          </select>
        </div>
      </div>

      {loading && (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-7">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="aspect-[3/4] animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      )}

      {!loading && lobbyView && (
        <div className="space-y-8">
          {favoriteGames.length > 0 && (
            <GameRow
              title="Your favourites" icon={BsStarFill} games={favoriteGames} allIds={allIds}
              favorites={favorites} onToggleFavorite={toggleFavorite} onSeeAll={() => setCategory('favorites')}
            />
          )}
          <GameRow
            title="Top RTP" icon={GiLightningFrequency} games={topRtp} allIds={allIds}
            favorites={favorites} onToggleFavorite={toggleFavorite} onSeeAll={() => setSort('rtp')}
          />
          {visibleCategories.filter((c) => c.value !== 'all').map((c) => (
            <GameRow
              key={c.value}
              title={c.label}
              icon={CATEGORY_ICONS[c.value]}
              games={games.filter((g) => g.category === c.value)}
              allIds={allIds}
              favorites={favorites}
              onToggleFavorite={toggleFavorite}
              onSeeAll={() => setCategory(c.value)}
            />
          ))}
        </div>
      )}

      {!loading && !lobbyView && (
        <>
          <p className="text-sm font-semibold text-muted-foreground">
            {filtered.length} game{filtered.length === 1 ? '' : 's'}
          </p>
          {filtered.length === 0 ? (
            <div className="rounded-2xl border border-border bg-card p-12 text-center">
              <p className="mb-1 font-bold">{onlyFavorites ? 'No favourites yet' : 'No games found'}</p>
              <p className="text-sm text-muted-foreground">
                {onlyFavorites ? 'Tap the star on any game to save it here.' : 'Try a different search or filter.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-7">
              {filtered.map((game) => (
                <GameTile
                  key={game.slug}
                  game={game}
                  tag={gameTag(game, allIds)}
                  isFavorite={favorites.has(game.slug)}
                  onToggleFavorite={toggleFavorite}
                />
              ))}
            </div>
          )}
        </>
      )}

      {nextPage && (
        <div className="flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-xl border border-border bg-card px-5 py-2.5 text-sm font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {loadingMore ? 'Loading…' : 'Load more games'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function CasinoPage() {
  // useSearchParams (category from the URL) needs a Suspense boundary.
  return (
    <Suspense>
      <CasinoLobby />
    </Suspense>
  );
}
