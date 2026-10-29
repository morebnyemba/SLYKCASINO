'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { FaHeadset, FaInfoCircle, FaTimes, FaWallet, FaWhatsapp } from 'react-icons/fa';
import { config } from '@/lib/config';
import { useWhatsAppSupport } from '@/components/whatsapp-support';

interface Announcement {
  enabled: boolean; title?: string; message?: string; tone?: 'info' | 'warning';
  show_withdraw_button?: boolean; show_support_button?: boolean; updated_at?: string | null;
}

const KEY = 'slyk:announcement-dismissed';

/** The operator's notice across the top of every page (edited in Admin → Banners).
 *  Players can close it; it comes back when the notice changes. */
export function AnnouncementBar() {
  const [a, setA] = useState<Announcement | null>(null);
  const [hidden, setHidden] = useState(true);
  const whatsapp = useWhatsAppSupport();

  useEffect(() => {
    let cancelled = false;
    fetch(`${config.apiUrl}/announcement/`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: Announcement | null) => {
        if (cancelled || !data?.enabled) return;
        setA(data);
        let dismissed: string | null = null;
        try { dismissed = localStorage.getItem(KEY); } catch { /* storage blocked */ }
        setHidden(dismissed === (data.updated_at ?? ''));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!a || hidden) return null;
  const warn = a.tone !== 'info';
  const close = () => {
    try { localStorage.setItem(KEY, a.updated_at ?? ''); } catch { /* storage blocked */ }
    setHidden(true);
  };
  return (
    <div role="status" className={`border-b px-3 py-2.5 text-sm sm:px-5 ${warn ? 'border-gold/40 bg-gold/15' : 'border-secondary/30 bg-secondary/10'}`}>
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2">
        <FaInfoCircle className={`shrink-0 ${warn ? 'text-gold' : 'text-secondary'}`} />
        <p className="min-w-0 flex-1 leading-snug">
          {a.title && <b className="mr-1.5">{a.title}:</b>}{a.message}
        </p>
        <div className="flex items-center gap-2">
          {a.show_withdraw_button && (
            <Link href="/account/wallet" className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1.5 text-xs font-bold text-secondary-foreground hover:brightness-110">
              <FaWallet size={11} /> Request withdrawal
            </Link>
          )}
          {a.show_support_button && (
            <a href={whatsapp ?? '/livechat'} {...(whatsapp && { target: '_blank', rel: 'noopener noreferrer' })}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-bold hover:bg-muted">
              {whatsapp ? <FaWhatsapp size={13} className="text-[#25D366]" /> : <FaHeadset size={12} />} Contact support
            </a>
          )}
          <button onClick={close} aria-label="Close notice" className="rounded-full p-1.5 text-muted-foreground hover:bg-black/10 hover:text-foreground">
            <FaTimes size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
