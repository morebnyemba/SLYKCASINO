import { config } from '@/lib/config';

export interface SiteIdentity {
  site_name: string;
  tagline: string;
  logo_url: string;
  license_text: string;
  /** Digits only, with country code; blank hides the WhatsApp support button. */
  whatsapp_number: string;
  /** Operator details for the legal pages; blank → neutral wording. */
  legal_name: string;
  registered_address: string;
  support_email: string;
  governing_law: string;
  dispute_body: string;
}

export const DEFAULT_IDENTITY: SiteIdentity = {
  site_name: 'BetBlits',
  tagline: 'Bet smart. Brag often.',
  logo_url: '',
  license_text: '',
  whatsapp_number: '',
  legal_name: '',
  registered_address: '',
  support_email: '',
  governing_law: '',
  dispute_body: '',
};

/**
 * Fetches the operator-configured site name/logo/license text. Fails silently
 * to the defaults above so a backend hiccup never blocks the page.
 */
export async function fetchSiteIdentity(): Promise<SiteIdentity> {
  try {
    const res = await fetch(`${config.apiUrl}/branding/identity/`, { next: { revalidate: 10 } });
    if (!res.ok) return DEFAULT_IDENTITY;
    const data = (await res.json()) as Partial<SiteIdentity>;
    return {
      site_name: data.site_name || DEFAULT_IDENTITY.site_name,
      tagline: data.tagline ?? DEFAULT_IDENTITY.tagline,
      logo_url: data.logo_url ?? '',
      // Blank on purpose until the operator enters a licence they actually hold.
      license_text: data.license_text ?? '',
      whatsapp_number: data.whatsapp_number ?? '',
      legal_name: data.legal_name ?? '',
      registered_address: data.registered_address ?? '',
      support_email: data.support_email ?? '',
      governing_law: data.governing_law ?? '',
      dispute_body: data.dispute_body ?? '',
    };
  } catch {
    return DEFAULT_IDENTITY;
  }
}
