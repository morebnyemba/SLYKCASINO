'use client';

import Link from 'next/link';
import { GiRollingDices, GiSpades } from 'react-icons/gi';
import { BsGrid1X2Fill } from 'react-icons/bs';
import { TbDiscFilled } from 'react-icons/tb';
import type { IconType } from 'react-icons';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Game {
  id: number;
  slug: string;
  name: string;
  provider: string;
  rtp: string;
}

interface GamesResponse {
  results?: Game[];
}

function gameIcon(name: string): IconType {
  const n = name.toLowerCase();
  if (n.includes('roulette')) return TbDiscFilled;
  if (n.includes('blackjack') || n.includes('black jack') || n.includes('poker') || n.includes('baccarat')) return GiSpades;
  if (n.includes('dice') || n.includes('craps')) return GiRollingDices;
  return BsGrid1X2Fill;
}

const DEMO_GAMES: Game[] = [
  { id: 1, slug: 'lucky-slots', name: 'Lucky Slots', provider: 'SLYK', rtp: '96.00' },
  { id: 2, slug: 'golden-wheel', name: 'Golden Wheel', provider: 'SLYK', rtp: '97.50' },
  { id: 3, slug: 'mega-dice', name: 'Mega Dice', provider: 'SLYK', rtp: '98.00' },
  { id: 4, slug: 'blackjack-classic', name: 'Blackjack Classic', provider: 'SLYK', rtp: '99.50' },
  { id: 5, slug: 'roulette-pro', name: 'Roulette Pro', provider: 'SLYK', rtp: '97.30' },
  { id: 6, slug: 'baccarat-vip', name: 'Baccarat VIP', provider: 'SLYK', rtp: '98.80' },
];

export default function CasinoPage() {
  const { data, loading } = useApi<GamesResponse>('/casino/games/');
  const apiGames = data?.results ?? [];
  const games = apiGames.length > 0 ? apiGames : DEMO_GAMES;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Casino</h1>
        <p className="text-muted-foreground">Choose a game and start playing. Bets are settled instantly.</p>
      </div>

      {loading && <p className="text-sm text-muted-foreground mb-4">Loading games…</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {games.map((game) => {
          const Icon = gameIcon(game.name);
          return (
          <Link key={game.slug} href={`/casino/${game.slug}?id=${game.id}`}>
            <Card className="cursor-pointer transition-colors hover:bg-accent">
              <CardHeader className="flex-row items-center gap-3 space-y-0 pb-2">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon size={20} />
                </span>
                <div>
                  <CardTitle className="text-base">{game.name}</CardTitle>
                  <p className="text-xs text-muted-foreground">{game.provider}</p>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">RTP {game.rtp}%</Badge>
                </div>
              </CardContent>
            </Card>
          </Link>
          );
        })}
      </div>
    </div>
  );
}
