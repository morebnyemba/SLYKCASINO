import { fetchSiteIdentity } from '@/lib/site-identity';

/** Bump when the wording of the legal pages changes (shown as their effective date). */
export const LEGAL_EFFECTIVE_DATE = '14 November 2026';

export interface LegalDetails {
  siteName: string;
  /** Who players contract with. */
  operator: string;
  /** Registered address, or '' when not entered yet. */
  address: string;
  /** Support email, or '' when not entered yet. */
  email: string;
  /** How to reach us, always readable ("support@…" or the in-site channels). */
  contact: string;
  /** Licence text exactly as issued, or '' while the operator holds none. */
  licence: string;
  /** Governing law, always readable. */
  law: string;
  /** External dispute body, or '' when none is set. */
  disputeBody: string;
}

/**
 * Operator details for the legal pages, from Admin → Branding → Site identity.
 * Blank fields become neutral wording — the pages never show "[PLACEHOLDER]"
 * text and never claim a licence the operator has not entered.
 */
export async function fetchLegalDetails(): Promise<LegalDetails> {
  const id = await fetchSiteIdentity();
  const email = id.support_email.trim();
  return {
    siteName: id.site_name,
    operator: id.legal_name.trim() || `the operator of ${id.site_name}`,
    address: id.registered_address.trim(),
    email,
    contact: email || 'our support team through live chat or the WhatsApp button on the site',
    licence: id.license_text.trim(),
    law: id.governing_law.trim() || 'the country in which the operator is registered',
    disputeBody: id.dispute_body.trim(),
  };
}
