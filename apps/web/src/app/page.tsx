import Link from 'next/link';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import { FaGift, FaShieldAlt, FaBolt, FaLock } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { LiveFeed } from '@/components/live-feed';
import { WinnersTicker } from '@/components/winners-ticker';
import { BannerSlider, type Banner } from '@/components/banner-slider';
import { apiGet } from '@/lib/config';
import { CASINO_HERO_IMAGES } from '@/lib/game-images';

// Shown only when an operator has not configured any banners yet.
const FALLBACK_BANNERS: Banner[] = [
  { id: 'f1', image_url: CASINO_HERO_IMAGES[3], title: 'SLÝKBETS Aviator', subtitle: 'Cash out before the crash', link_url: '/casino/crash', cta_label: 'Play now' },
  { id: 'f2', image_url: CASINO_HERO_IMAGES[1], title: 'Welcome Bonus', subtitle: 'Claim your deposit match and start playing', link_url: '/promotions', cta_label: 'Claim bonus' },
  { id: 'f3', image_url: CASINO_HERO_IMAGES[2], title: 'Tournaments', subtitle: 'Climb the leaderboard for prizes', link_url: '/tournaments', cta_label: 'View races' },
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
  const [eventsData, bannersData] = await Promise.all([
    apiGet<EventItem>('/events/?featured=true'),
    apiGet<Banner>('/promotions/banners/'),
  ]);
  const events = (eventsData.results ?? []) as EventItem[];
  const banners = (bannersData.results ?? []) as Banner[];

  return (
    <div className="space-y-8">
      <BannerSlider banners={banners.length > 0 ? banners : FALLBACK_BANNERS} />

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
                <Card className="transition-colors hover:bg-accent/10">
                  <CardHeader className="flex-row items-center justify-between space-y-0">
                    <div className="flex items-center gap-2">
                      <Badge className="bg-live/10 text-live">Live</Badge>
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
