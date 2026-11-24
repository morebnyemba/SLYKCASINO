'use client';

import { useEffect, useState } from 'react';
import { config } from '@/lib/config';

/** A photo or video support sent: private, so it is fetched with the player's token. */
export function SupportMedia({ url, kind, token }: { url: string; kind: string; token: string | null }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!token) return;
    let gone = false;
    let made: string | null = null;
    fetch(`${config.apiUrl.replace(/\/api\/?$/, '')}${url}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => { if (!gone) { made = URL.createObjectURL(b); setSrc(made); } })
      .catch(() => { if (!gone) setFailed(true); });
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [url, token]);
  if (failed) return <p className="text-xs opacity-70">[{kind === 'video' ? 'video' : 'photo'} unavailable]</p>;
  if (!src) return <div className="h-32 w-48 animate-pulse rounded-lg bg-black/10" />;
  return kind === 'video'
    // eslint-disable-next-line jsx-a11y/media-has-caption
    ? <video src={src} controls playsInline className="max-h-72 max-w-full rounded-lg" />
    // eslint-disable-next-line @next/next/no-img-element
    : <a href={src} target="_blank" rel="noreferrer"><img src={src} alt="From support" className="max-h-72 max-w-full rounded-lg object-contain" /></a>;
}
