import { ImageResponse } from 'next/og';
import { apiGet } from '@/lib/config';
import type { EventItem } from '@/lib/sports';

// A match's link preview: teams, competition, kick-off and the 1X2 prices.
export const alt = 'Match odds on BetBlits';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';
export const revalidate = 600;

/** The brand bolt, drawn (an emoji would make the renderer download an emoji font). */
function Bolt({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" fill="#FFD84D" />
    </svg>
  );
}

/** A team crest as a data URL, or null if it can't be fetched quickly (never fail the card over a logo). */
async function crestData(url?: string | null): Promise<string | null> {
  if (!url) return null;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(2500), next: { revalidate: 86400 } });
    const type = res.headers.get('content-type') ?? '';
    if (!res.ok || !type.startsWith('image/') || type.includes('svg')) return null;
    return `data:${type};base64,${Buffer.from(await res.arrayBuffer()).toString('base64')}`;
  } catch {
    return null;
  }
}

export default async function MatchImage({ params }: { params: Promise<{ event: string }> }) {
  const { event } = await params;
  const ev = (await apiGet<EventItem>(`/events/${event}/`)) as Partial<EventItem> & { error?: string };
  const home = ev.home_team?.name ?? ev.name?.split(/\s+vs\.?\s+/i)[0] ?? 'Match';
  const away = ev.away_team?.name ?? ev.name?.split(/\s+vs\.?\s+/i)[1] ?? '';
  const when = ev.starts_at
    ? new Date(ev.starts_at).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Harare' }) + ' CAT'
    : '';
  const odds = [['1', ev.odds], ['X', ev.odds_draw], ['2', ev.odds_away]].filter(([, o]) => o != null && Number(o) > 0) as [string, string | number][];
  const [homeCrest, awayCrest] = await Promise.all([crestData(ev.home_team?.logo_url), crestData(ev.away_team?.logo_url)]);
  const crest = (url?: string | null) => (url
    ? <img src={url} width={150} height={150} style={{ objectFit: 'contain' }} />
    : <div style={{ width: 150, height: 150, borderRadius: 999, background: 'rgba(255,255,255,0.12)' }} />);

  return new ImageResponse(
    (
      <div style={{
        width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-between',
        padding: '56px 72px', color: 'white', fontFamily: 'sans-serif',
        background: 'linear-gradient(135deg, #110B2E 0%, #312783 60%, #4338CA 100%)',
      }}>
        <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', fontSize: 30, color: 'rgba(255,255,255,0.8)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontWeight: 800, color: 'white' }}><Bolt size={34} />BetBlits</div>
          <div>{ev.league?.name ?? 'Sportsbook'}</div>
        </div>
        <div style={{ display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, width: 380 }}>
            {crest(homeCrest)}
            <div style={{ fontSize: 44, fontWeight: 800, textAlign: 'center' }}>{home}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <div style={{ fontSize: 60, fontWeight: 800, color: 'rgba(255,255,255,0.7)' }}>VS</div>
            {when && <div style={{ fontSize: 26, color: 'rgba(255,255,255,0.75)' }}>{when}</div>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, width: 380 }}>
            {crest(awayCrest)}
            <div style={{ fontSize: 44, fontWeight: 800, textAlign: 'center' }}>{away}</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 18 }}>
          {odds.map(([label, o]) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 30px', borderRadius: 18, background: 'rgba(255,255,255,0.12)', fontSize: 34 }}>
              <span style={{ color: 'rgba(255,255,255,0.65)' }}>{label}</span>
              <span style={{ fontWeight: 800, color: '#FFD84D' }}>{Number(o).toFixed(2)}</span>
            </div>
          ))}
          {odds.length === 0 && <div style={{ fontSize: 30, color: 'rgba(255,255,255,0.75)' }}>Odds coming soon</div>}
        </div>
      </div>
    ),
    size,
  );
}
