import { ImageResponse } from 'next/og';
import { fetchSiteIdentity } from '@/lib/site-identity';

// The link preview for the whole site (WhatsApp, Facebook, X, Google…).
export const alt = 'BetBlits — sports betting, live odds and Aviator';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';
export const revalidate = 3600;

/** The brand bolt, drawn (an emoji would make the renderer download an emoji font). */
function Bolt({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" fill="#FFD84D" />
    </svg>
  );
}

export default async function OpengraphImage() {
  const { site_name: name, tagline } = await fetchSiteIdentity();
  return new ImageResponse(
    (
      <div style={{
        width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        padding: 72, color: 'white', fontFamily: 'sans-serif',
        background: 'linear-gradient(135deg, #110B2E 0%, #312783 55%, #4338CA 100%)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: '#6C63E8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Bolt size={44} /></div>
          <div style={{ fontSize: 56, fontWeight: 800, letterSpacing: -1 }}>{name}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.05, letterSpacing: -2 }}>Sports betting, live odds &amp; Aviator</div>
          <div style={{ fontSize: 34, color: 'rgba(255,255,255,0.75)' }}>{tagline || 'Bet smart. Brag often.'}</div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 28 }}>
          <div style={{ display: 'flex', gap: 14 }}>
            {['In-play betting', 'Cash out', 'EcoCash · OneMoney · InnBucks'].map((t) => (
              <div key={t} style={{ padding: '10px 22px', borderRadius: 999, background: 'rgba(255,255,255,0.12)' }}>{t}</div>
            ))}
          </div>
          <div style={{ padding: '10px 18px', borderRadius: 999, border: '3px solid rgba(255,255,255,0.6)', fontWeight: 800 }}>18+</div>
        </div>
      </div>
    ),
    size,
  );
}
