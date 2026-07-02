import { config } from '@/lib/config';

export interface SiteIdentity {
  site_name: string;
  tagline: string;
  logo_url: string;
  license_text: string;
}

export const DEFAULT_IDENTITY: SiteIdentity = {
  site_name: 'SLÝKBETS',
  tagline: 'Bet smart. Brag often.',
  logo_url: '',
  license_text: 'Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. Licence No. LGB/SLYKBETS/2026 (demo).',
};

/**
 * Fetches the operator-configured site name/logo/license text. Fails silently
 * to the defaults above so a backend hiccup never blocks the dashboard.
 */
export async function fetchSiteIdentity(): Promise<SiteIdentity> {
  try {
    const res = await fetch(`${config.apiUrl}/branding/identity/`, { cache: 'no-store' });
    if (!res.ok) return DEFAULT_IDENTITY;
    const data = (await res.json()) as Partial<SiteIdentity>;
    return {
      site_name: data.site_name || DEFAULT_IDENTITY.site_name,
      tagline: data.tagline ?? DEFAULT_IDENTITY.tagline,
      logo_url: data.logo_url ?? '',
      license_text: data.license_text || DEFAULT_IDENTITY.license_text,
    };
  } catch {
    return DEFAULT_IDENTITY;
  }
}
