'use client';

import { FaWhatsapp } from 'react-icons/fa';
import { useAuth } from '@/lib/auth-context';
import { useSiteIdentity } from '@/lib/identity-context';

/** A wa.me chat link to the support number set in Admin → Branding, or null when none is set. */
export function useWhatsAppSupport(): string | null {
  const { whatsapp_number: number, site_name: site } = useSiteIdentity();
  const { user } = useAuth();
  if (!number) return null;
  const text = user ? `Hi ${site} support, I need help with my account (${user.username}).` : `Hi ${site} support, I need help.`;
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

/** Floating WhatsApp support button, kept clear of the mobile tab bar and the bet-slip bar. */
export function WhatsAppButton() {
  const href = useWhatsAppSupport();
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label="Chat with support on WhatsApp"
      className="fixed bottom-[148px] right-3 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-[0_10px_30px_rgba(0,0,0,0.35)] transition-transform hover:scale-105 lg:bottom-24 lg:right-5">
      <FaWhatsapp size={30} />
    </a>
  );
}
