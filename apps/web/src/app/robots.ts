import type { MetadataRoute } from 'next';
import { PRIVATE_PATHS, SITE_URL, absolute } from '@/lib/seo';

/** /robots.txt — crawl the public site, keep private and transactional pages out. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: '*', allow: '/', disallow: PRIVATE_PATHS }],
    sitemap: absolute('/sitemap.xml'),
    host: SITE_URL,
  };
}
