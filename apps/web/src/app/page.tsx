import Link from 'next/link';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import { FaGift, FaShieldAlt, FaBolt, FaLock } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { LiveFeed } from '@/components/live-feed';
import { WinnersTicker } from '@/components/winners-ticker';
import { Carousel, CarouselItem } from '@/components/carousel';
import { apiGet } from '@/lib/config';
import { CASINO_HERO_IMAGES } from '@/lib/game-images';

const HERO_SLIDES = [
  { image: CASINO_HERO_IMAGES[3], title: 'SLYK Aviator', subtitle: 'Cash out before the crash', href: '/casino/crash' },
  { image: CASINO_HERO_IMAGES[0], title: 'Spin the wheel', subtitle: 'Live roulette tables open now', href: '/casino' },
  { image: CASINO_HERO_IMAGES[1], title: 'Lucky Slots', subtitle: 'Daily jackpot drops', href: '/casino' },
  { image: CASINO_HERO_IMAGES[2], title: 'Tournaments', subtitle: 'Climb the leaderboard for prizes', href: '/tournaments' },
];

interface EventItem {
  id: string | number;
  name: string;
  odds: number;
}

const QUICK_LINKS: { href: string; label: string; description: string; icon: IconType }[] = [
  { href: '/sportsbook', label: 'Sportsbook', description: 'Live & upcoming markets', icon: GiTrophy },
  { href: '/casino', label: 'Casino', description: 'Slots, table games & more', icon: GiRollingDices },
  { href: '/promotions', label: 'Promotions', description: 'Bonuses & free bets', icon: FaGift },
];

const TRUST_BADGES: { label: string; icon: IconType }[] = [
  { label: 'Instant payouts', icon: FaBolt },
  { label: 'Secure wallet', icon: FaLock },
  { label: 'Responsible gaming', icon: FaShieldAlt },
];

export default async function LobbyPage() {
  const data = await apiGet<EventItem>('/events/?featured=true');
  const events = (data.results ?? []) as EventItem[];

  return (
    <div className="space-y-8">
      <Carousel>
        {HERO_SLIDES.map((slide) => (
          <CarouselItem key={slide.title} className="w-[300px] sm:w-[420px]">
            <Link href={slide.href}>
              <div className="relative h-40 overflow-hidden rounded-xl sm:h-52">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={slide.image} alt={slide.title} className="h-full w-full object-cover" />
                <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/75 to-transparent p-4">
                  <p className="text-lg font-bold text-white">{slide.title}</p>
                  <p className="text-sm text-white/80">{slide.subtitle}</p>
                </div>
              </div>
            </Link>
          </CarouselItem>
        ))}
      </Carousel>

      <WinnersTicker />

      <div className="grid gap-4 sm:grid-cols-3">
        {QUICK_LINKS.map((l) => {
          const Icon = l.icon;
          return (
            <Link key={l.href} href={l.href}>
              <Card className="h-full transition-all hover:-translate-y-0.5 hover:border-primary hover:shadow-md">
                <CardContent className="flex items-center gap-3 pt-6">
                  <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon size={22} />
                  </span>
                  <div>
                    <p className="font-semibold">{l.label}</p>
                    <p className="text-xs text-muted-foreground">{l.description}</p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <section>
          <h1 className="mb-2 text-2xl font-bold">Featured events</h1>
          <p className="mb-4 text-muted-foreground">Top live & upcoming markets. Click through to place a bet.</p>
          <div className="grid gap-3">
            {events.length === 0 && (
              <Card>
                <CardContent className="pt-6 text-muted-foreground">
                  No events yet (Django API not seeded). Browse the{' '}
                  <Link href="/sportsbook" className="text-primary underline-offset-4 hover:underline">sportsbook</Link>.
                </CardContent>
              </Card>
            )}
            {events.map((ev) => (
              <Link key={ev.id} href={`/sportsbook/${ev.id}`}>
                <Card className="transition-colors hover:bg-accent">
                  <CardHeader className="flex-row items-center justify-between space-y-0">
                    <div className="flex items-center gap-2">
                      <Badge className="bg-red-500/10 text-red-500">Live</Badge>
                      <CardTitle className="text-base">{ev.name}</CardTitle>
                    </div>
                    <Badge variant="secondary">odds {ev.odds}</Badge>
                  </CardHeader>
                </Card>
              </Link>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap gap-4 border-t border-border pt-4 text-xs text-muted-foreground">
            {TRUST_BADGES.map((b) => {
              const Icon = b.icon;
              return (
                <span key={b.label} className="flex items-center gap-1.5">
                  <Icon size={13} className="text-primary" />
                  {b.label}
                </span>
              );
            })}
          </div>
        </section>
        <LiveFeed channel="odds" title="Live Odds" />
      </div>
    </div>
  );
}
