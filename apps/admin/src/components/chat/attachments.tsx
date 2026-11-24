'use client';

import { useEffect, useRef, useState } from 'react';
import { BsPaperclip, BsXLg } from 'react-icons/bs';
import { apiFileUrl } from '@/lib/upload';

export const ACCEPT = 'image/jpeg,image/png,video/mp4,video/3gpp';
const LIMIT = { image: 5, video: 16 };

/** A photo or video only staff (or its player) may see: fetched with the token, shown from memory. */
export function AuthedMedia({ url, kind, token }: { url: string; kind: string; token: string | null }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!token) return;
    let gone = false;
    let made: string | null = null;
    fetch(apiFileUrl(url), { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => { if (!gone) { made = URL.createObjectURL(b); setSrc(made); } })
      .catch(() => { if (!gone) setFailed(true); });
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [url, token]);
  if (failed) return <p className="text-xs text-muted-foreground">[{kind === 'video' ? 'video' : 'photo'} unavailable]</p>;
  if (!src) return <div className="h-32 w-48 animate-pulse rounded-lg bg-muted" />;
  return kind === 'video'
    // eslint-disable-next-line jsx-a11y/media-has-caption
    ? <video src={src} controls className="max-h-64 max-w-full rounded-lg" />
    // eslint-disable-next-line @next/next/no-img-element
    : <a href={src} target="_blank" rel="noreferrer"><img src={src} alt="Attachment" className="max-h-64 max-w-full rounded-lg object-contain" /></a>;
}

/** Paperclip button + the chosen file as a removable chip. Checks type and size before upload. */
export function AttachPicker({ file, onChange, disabled, onError }: {
  file: File | null; onChange: (f: File | null) => void; disabled?: boolean; onError: (msg: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  function pick(f: File | undefined) {
    if (!f) return;
    const kind = f.type.startsWith('video/') ? 'video' : f.type.startsWith('image/') ? 'image' : '';
    if (!kind || !ACCEPT.split(',').includes(f.type)) { onError('Send a JPG or PNG photo, or an MP4 video.'); return; }
    if (f.size > LIMIT[kind] * 1024 * 1024) { onError(`${kind === 'video' ? 'Videos' : 'Photos'} can be at most ${LIMIT[kind]} MB.`); return; }
    onChange(f);
  }
  return (
    <>
      <input ref={input} type="file" accept={ACCEPT} className="hidden"
        onChange={(e) => { pick(e.target.files?.[0]); if (input.current) input.current.value = ''; }} />
      {file ? (
        <span className="inline-flex max-w-[220px] items-center gap-1.5 self-center rounded-full border border-border px-2.5 py-1 text-xs">
          <span className="truncate">{file.type.startsWith('video/') ? '🎬' : '📷'} {file.name}</span>
          <button type="button" aria-label="Remove attachment" onClick={() => onChange(null)} className="text-muted-foreground hover:text-foreground"><BsXLg /></button>
        </span>
      ) : (
        <button type="button" aria-label="Attach a photo or video" disabled={disabled} onClick={() => input.current?.click()}
          className="self-center rounded-lg p-2 text-lg text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50">
          <BsPaperclip />
        </button>
      )}
    </>
  );
}
