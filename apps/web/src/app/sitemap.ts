import type { MetadataRoute } from 'next';
import { apiGetAll } from '@/lib/config';
import { SEO_SPORTS, absolute } from '@/lib/seo';
import { isPriced, type EventItem } from '@/lib/sports';

// Kept fresh: it follows the match list's own short cache (apiGet), so new
// fixtures appear and finished ones drop out within seconds of a request.
export const revalidate = 3600;

/** /sitemap.xml — the main sections, each sport, and every upcoming priced match. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const pages: MetadataRoute.Sitemap = [
    { url: absolute('/sportsbook'), lastModified: now, changeFrequency: 'hourly', priority: 1 },
    { url: absolute('/sportsbook?tab=live'), lastModified: now, changeFrequency: 'always', priority: 0.9 },
    { url: absolute('/aviator'), lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: absolute('/promotions'), lastModified: now, changeFrequency: 'weekly', priority: 0.7 },
    { url: absolute('/register'), lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    ...SEO_SPORTS.map((s) => ({
      url: absolute(`/sportsbook?sport=${s.id}`), lastModified: now, changeFrequency: 'hourly' as const, priority: 0.8,
    })),
    ...['terms', 'privacy', 'responsible-gambling', 'aml-kyc-policy', 'cookies'].map((p) => ({
      url: absolute(`/legal/${p}`), changeFrequency: 'yearly' as const, priority: 0.3,
    })),
  ];
  let matches: MetadataRoute.Sitemap = [];
  try {
    const { rows } = await apiGetAll<EventItem>('/events/?upcoming=true&page_size=200');
    matches = rows.filter(isPriced).map((ev) => ({
      url: absolute(`/sportsbook/${ev.id}`),
      lastModified: now,
      changeFrequency: 'hourly' as const,
      priority: ev.featured ? 0.8 : 0.6,
    }));
  } catch { /* the API being down must not break the sitemap */ }
  return [...pages, ...matches];
}
