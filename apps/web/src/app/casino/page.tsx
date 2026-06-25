'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { BsSearch, BsStarFill } from 'react-icons/bs';
import { Carousel, CarouselItem } from '@/components/carousel';
import { GameTile } from '@/components/game-tile';
import { useApi } from '@/lib/use-api';
import { CASINO_HERO_IMAGES } from '@/lib/game-images';
import {
  CASINO_CATEGORIES as CATEGORIES,
  DEMO_GAMES,
  type Game,
  gameTag,
  loadFavorites,
  saveFavorites,
} from '@/lib/casino';

interface GamesResponse {
  results?: Game[];
  next?: string | null;
}

export default function CasinoPage() {
  const { data, loading } = useApi<GamesResponse>('/casino/games/');
  const [extraGames, setExtraGames] = useState<Game[]>([]);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const apiGames = data?.results ?? [];
  const games = apiGames.length > 0 ? [...apiGames, ...extraGames] : DEMO_GAMES;

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

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [provider, setProvider] = useState('all');
  const [sort, setSort] = useState<'name' | 'rtp'>('name');
  const [favorites, setFavorites] = useState<Set<string>>(() => loadFavorites());
  const [onlyFavorites, setOnlyFavorites] = useState(false);

  const providers = useMemo(() => Array.from(new Set(games.map((g) => g.provider))).sort(), [games]);
  const visibleCategories = useMemo(() => {
    const present = new Set(games.map((g) => g.category).filter(Boolean));
    return CATEGORIES.filter((c) => c.value === 'all' || present.has(c.value));
  }, [games]);

  function toggleFavorite(slug: string) {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug); else next.add(slug);
      saveFavorites(next);
      return next;
    });
  }

  const filtered = useMemo(() => {
    let list = games.filter((g) => g.name.toLowerCase().includes(search.toLowerCase()));
    if (category !== 'all') list = list.filter((g) => g.category === category);
    if (provider !== 'all') list = list.filter((g) => g.provider === provider);
    if (onlyFavorites) list = list.filter((g) => favorites.has(g.slug));
    list = [...list].sort((a, b) => (
      sort === 'rtp' ? parseFloat(b.rtp) - parseFloat(a.rtp) : a.name.localeCompare(b.name)
    ));
    return list;
  }, [games, search, category, provider, onlyFavorites, favorites, sort]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Casino</h1>
        <p className="text-muted-foreground">Choose a game and start playing. Bets are settled instantly.</p>
      </div>

      <Carousel className="mb-6">
        {CASINO_HERO_IMAGES.map((src, i) => (
          <CarouselItem key={src} className="w-[280px] sm:w-[360px]">
            <Link href={`/casino/${games[i % games.length]?.slug ?? ''}?id=${games[i % games.length]?.id ?? ''}`}>
              <div className="relative h-36 overflow-hidden rounded-xl sm:h-44">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt="Casino highlight" className="h-full w-full object-cover" />
                <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/70 to-transparent p-3">
                  <p className="font-semibold text-white">{games[i % games.length]?.name ?? 'Featured game'}</p>
                </div>
              </div>
            </Link>
          </CarouselItem>
        ))}
      </Carousel>

      <div className="mb-4 flex flex-wrap gap-2">
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
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search games…"
            className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="all">All providers</option>
          {providers.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as 'name' | 'rtp')}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="name">Sort: A–Z</option>
          <option value="rtp">Sort: Highest RTP</option>
        </select>
        <button
          onClick={() => setOnlyFavorites((v) => !v)}
          className={`flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
            onlyFavorites ? 'border-gold bg-gold/10 text-gold' : 'border-border text-muted-foreground hover:bg-accent/10'
          }`}
        >
          <BsStarFill size={13} />
          Favorites
        </button>
      </div>

      {loading && <p className="text-sm text-muted-foreground mb-4">Loading games…</p>}
      {!loading && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">No games match your filters.</p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {filtered.map((game) => (
          <GameTile
            key={game.slug}
            game={game}
            tag={gameTag(game, games.map((g) => g.id))}
            isFavorite={favorites.has(game.slug)}
            onToggleFavorite={toggleFavorite}
          />
        ))}
      </div>

      {nextPage && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent/10 disabled:opacity-50"
          >
            {loadingMore ? 'Loading…' : 'Load more games'}
          </button>
        </div>
      )}
    </div>
  );
}
