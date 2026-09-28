import Link from 'next/link';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import { FaShieldAlt, FaBolt, FaLock, FaHeadset } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { WinnersTicker } from '@/components/winners-ticker';
import { BannerSlider, type Banner } from '@/components/banner-slider';
import { PopularGames } from '@/components/popular-games';
import { Carousel, CarouselItem } from '@/components/carousel';
import { FeaturedMatchCard } from '@/components/event-row';
import { apiGet } from '@/lib/config';
import { DEMO_GAMES, type Game } from '@/lib/casino';
import { isLive, isPriced, sortEvents, type EventItem } from '@/lib/sports';

// Brand gradient treatment for a hue (matches the design system's `art()` generator).
function heroArt(hue: number): string {
  return `linear-gradient(150deg, hsl(${hue} 58% 30%), hsl(${hue} 64% 12%))`;
}

// Shown only when an operator has not configured any banners yet.
const FALLBACK_BANNERS: Banner[] = [
  { id: 'f1', bg: heroArt(12), big: '2.48×', eyebrow: 'FEATURED · CRASH', title: 'SLÝKBETS Aviator', subtitle: 'Watch the multiplier climb — cash out before it crashes. 99% RTP.', link_url: '/casino/crash', cta_label: 'Play now' },
  { id: 'f2', bg: heroArt(262), big: '+$1K', eyebrow: 'WELCOME OFFER', title: '200% up to $1,000', subtitle: 'Double your first three deposits, plus 50 free spins on the house.', link_url: '/promotions', cta_label: 'Claim bonus' },
  { id: 'f3', bg: heroArt(180), big: '$50K', eyebrow: 'WEEKEND TOURNAMENT', title: 'Drop & Win', subtitle: 'Climb the leaderboard for a share of a $50,000 prize pool.', link_url: '/tournaments', cta_label: 'Join race' },
];

const TRUST_BADGES: { label: string; icon: IconType }[] = [
  { label: 'Instant payouts', icon: FaBolt },
  { label: 'Secure wallet', icon: FaLock },
  { label: 'Responsible gaming', icon: FaShieldAlt },
  { label: '24/7 live support', icon: FaHeadset },
];

function ProductCard({ href, title, subtitle, icon: Icon, hue, stat }: {
  href: string; title: string; subtitle: string; icon: IconType; hue: number; stat: string;
}) {
  return (
    <Link
      href={href}
      className="group relative flex min-h-[120px] flex-1 flex-col justify-end overflow-hidden rounded-2xl p-4 text-white shadow-lg transition-transform hover:-translate-y-0.5 sm:p-5"
      style={{ background: heroArt(hue) }}
    >
      <Icon
        size={110}
        className="absolute -right-4 -top-3 text-white/10 transition-transform duration-300 group-hover:rotate-6 group-hover:scale-110"
      />
      <span className="mb-1 flex w-fit items-center gap-1.5 rounded bg-black/25 px-1.5 py-0.5 text-[10px] font-bold backdrop-blur">
        <span className="h-1.5 w-1.5 rounded-full bg-win" /> {stat}
      </span>
      <p className="text-xl font-black sm:text-2xl">{title}</p>
      <p className="text-xs font-semibold text-white/75 sm:text-sm">{subtitle}</p>
    </Link>
  );
}

export default async function LobbyPage() {
  const [featuredData, eventsData, bannersData, gamesData] = await Promise.all([
    // Featured matches are fetched on their own so one far down the kick-off
    // order is never missed; the soonest priced matches are the fallback.
    apiGet<EventItem>('/events/?upcoming=true&priced=true&featured=true&page_size=8'),
    apiGet<EventItem>('/events/?upcoming=true&priced=true&page_size=8'),
    apiGet<Banner>('/promotions/banners/'),
    apiGet<Game>('/casino/games/'),
  ]);
  const bettable = (data: typeof eventsData) =>
    ((data.results ?? []) as EventItem[]).filter((ev) => ev.is_open !== false && isPriced(ev));
  const featured = bettable(featuredData);
  const events = sortEvents(featured.length > 0 ? featured : bettable(eventsData));
  const banners = (bannersData.results ?? []) as Banner[];
  const games = (gamesData.results ?? []) as Game[];
  const liveCount = events.filter(isLive).length;

  return (
    <div className="space-y-8">
      <div className="grid gap-3 xl:grid-cols-[1fr_340px]">
        <BannerSlider banners={banners.length > 0 ? banners : FALLBACK_BANNERS} />
        <div className="flex gap-3 xl:flex-col">
          <ProductCard href="/casino" title="Casino" subtitle="Slots, live tables & crash" icon={GiRollingDices} hue={262} stat="Games live now" />
          <ProductCard
            href="/sportsbook"
            title="Sports"
            subtitle="Pre-match & in-play odds"
            icon={GiTrophy}
            hue={150}
            stat={liveCount > 0 ? `${liveCount} live now` : 'Top odds'}
          />
        </div>
      </div>

      <WinnersTicker />

      {events.length > 0 && (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <GiTrophy size={18} className="text-secondary" />
            <h2 className="text-base font-extrabold sm:text-lg">Top matches</h2>
            <Link href="/sportsbook" className="ml-auto rounded-lg px-2.5 py-1.5 text-xs font-bold text-muted-foreground hover:bg-muted hover:text-foreground">
              All sports
            </Link>
          </div>
          <Carousel>
            {events.slice(0, 8).map((ev) => (
              <CarouselItem key={ev.id}>
                <FeaturedMatchCard ev={ev} />
              </CarouselItem>
            ))}
          </Carousel>
        </section>
      )}

      <PopularGames games={games.length > 0 ? games : DEMO_GAMES} />

      <div className="grid grid-cols-2 gap-3 rounded-2xl border border-border bg-card p-4 text-xs font-semibold text-muted-foreground sm:grid-cols-4">
        {TRUST_BADGES.map((b) => {
          const Icon = b.icon;
          return (
            <span key={b.label} className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/15 text-secondary">
                <Icon size={14} />
              </span>
              {b.label}
            </span>
          );
        })}
      </div>
    </div>
  );
}
