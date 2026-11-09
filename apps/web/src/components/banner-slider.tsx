'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { config } from '@/lib/config';

export interface Banner {
  id: number | string;
  title: string;
  subtitle?: string;
  /** Photo banner, uploaded by an operator in the admin app. */
  image_url?: string;
  /** A design made for phones (about 16:10). Used instead of `image_url` below the `sm` breakpoint. */
  mobile_image_url?: string;
  /** A short silent loop (MP4/WebM) played over the image, which is its poster and fallback. */
  video_url?: string;
  /** Movement for a still banner: a slow zoom, or a shine sweeping across. */
  motion?: 'none' | 'zoom' | 'shine';
  /** Which side of the wide design stays in view when it is cropped for a narrow screen. */
  focus?: 'left' | 'center' | 'right';
  /** Print title, subtitle and a dark fade over the image (default). Off: the design carries its own words. */
  overlay_text?: boolean;
  /** Brand-style gradient background (CSS `background` value), used when no photo is set. */
  bg?: string;
  /** Large faded decorative figure shown over a gradient banner, e.g. "2.48×". */
  big?: string;
  eyebrow?: string;
  link_url?: string;
  cta_label?: string;
}

const AUTO_ADVANCE_MS = 6000;
/** How often open pages ask for banner changes (new, edited, removed, or reaching their start/end time). */
const REFRESH_MS = 20000;

/**
 * Banner box. On a phone its height follows the width (16:10), so the artwork
 * keeps its shape on any screen from 320px up instead of being squashed or
 * cropped by a fixed height; from `sm` up it has a fixed height. Add the
 * height classes for the surface, e.g. `sm:h-60 md:h-72`.
 */
export const BANNER_FRAME = 'group relative aspect-[16/10] w-full min-w-0 min-h-52 touch-pan-y overflow-hidden rounded-3xl bg-muted sm:aspect-auto sm:min-h-0 banner-frame';

function isExternal(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

/** Swipe left/right on a touch screen to change slide. Ignores mostly-vertical drags so the page still scrolls. */
export function useSwipe(onPrev: () => void, onNext: () => void, onHold?: (holding: boolean) => void) {
  const start = useRef<{ x: number; y: number } | null>(null);
  return {
    onTouchStart: (e: React.TouchEvent) => {
      start.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      onHold?.(true);
    },
    onTouchEnd: (e: React.TouchEvent) => {
      onHold?.(false);
      const s = start.current;
      start.current = null;
      if (!s) return;
      const dx = e.changedTouches[0].clientX - s.x;
      const dy = e.changedTouches[0].clientY - s.y;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5) (dx < 0 ? onNext : onPrev)();
    },
    onTouchCancel: () => { start.current = null; onHold?.(false); },
  };
}

/**
 * Keeps a surface's banners live: starts from what the server rendered, then
 * re-reads them every 20 seconds, when the tab comes back into view and when
 * the connection returns — so a banner an operator adds, edits, switches off
 * or schedules shows up (or goes) on open pages without a reload. A failed
 * request leaves what is on screen alone.
 */
export function useLiveBanners(placement: string, initial: Banner[]): Banner[] {
  const [banners, setBanners] = useState(initial);
  const last = useRef(JSON.stringify(initial));

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      if (document.hidden) return;
      try {
        const res = await fetch(`${config.apiUrl}/promotions/banners/?placement=${placement}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const rows = ((Array.isArray(data) ? data : data.results) ?? []) as (Banner & { placement?: string })[];
        const next = rows.filter((b) => !b.placement || b.placement === placement);
        const key = JSON.stringify(next);
        if (key !== last.current) { last.current = key; setBanners(next); }
      } catch { /* offline or restarting: keep what is showing */ }
    }
    const timer = window.setInterval(refresh, REFRESH_MS);
    window.addEventListener('focus', refresh);
    window.addEventListener('online', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('online', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [placement]);

  return banners;
}

/** True when the visitor asked their device for less motion: no auto-advance then. */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(query.matches);
    const onChange = () => setReduced(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/** Whether banner videos may play: not for visitors who prefer less motion, nor on a data saver connection. */
function useVideoAllowed() {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const saver = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
    const update = () => setAllowed(!query.matches && !saver);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return allowed;
}

/**
 * The banner's video loop, laid over its image. It only exists on the slide on
 * screen, plays only while it is scrolled into view and the tab is open (so it
 * costs no battery or data otherwise), fades in once it can play, and quietly
 * disappears, leaving the image, if it fails.
 */
function BannerVideo({ src, poster, position }: { src: string; poster?: string; position: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const play = () => { if (!document.hidden) void video.play().catch(() => { /* blocked: the image stays */ }); };
    const observer = new IntersectionObserver(([entry]) => (entry?.isIntersecting ? play() : video.pause()), { threshold: 0.25 });
    observer.observe(video);
    const onVisibility = () => (document.hidden ? video.pause() : play());
    document.addEventListener('visibilitychange', onVisibility);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', onVisibility); };
  }, []);

  if (failed) return null;
  return (
    <video
      ref={ref} src={src} poster={poster} muted loop playsInline preload="metadata" aria-hidden
      onCanPlay={() => setReady(true)} onError={() => setFailed(true)}
      className={`absolute inset-0 h-full w-full rounded-[inherit] object-cover transition-opacity duration-500 ${ready ? 'opacity-100' : 'opacity-0'}`}
      style={{ objectPosition: position }}
    />
  );
}

/** Slide dots with a finger-sized tap area around each one. */
export function SlideDots({ count, index, onGo, label, className = '' }: {
  count: number; index: number; onGo: (i: number) => void; label: string; className?: string;
}) {
  return (
    <div className={`absolute left-1/2 z-10 flex -translate-x-1/2 items-center ${className}`}>
      {Array.from({ length: count }, (_, i) => (
        <button key={i} type="button" aria-label={`${label} ${i + 1}`} aria-current={i === index} onClick={() => onGo(i)}
          className="flex h-6 w-4 items-center justify-center sm:w-3.5">
          <span className={`h-1.5 rounded-full transition-all ${i === index ? 'w-6 bg-white' : 'w-1.5 bg-white/55'}`} />
        </button>
      ))}
    </div>
  );
}

/**
 * Full-width promotional banner slider. Shows one wide banner at a time with
 * auto-advance, dots, swipe on phones and hover arrows on desktop. Banners are
 * managed by operators in the admin app; `banners` is fetched server-side and
 * passed in.
 */
export function BannerSlider({ banners: initial, placement = 'home_hero' }: { banners: Banner[]; placement?: string }) {
  const banners = useLiveBanners(placement, initial);
  const [index, setIndex] = useState(0);
  const [holding, setHolding] = useState(false);
  const reduced = usePrefersReducedMotion();
  const count = banners.length;
  // A banner removed while the visitor is on the last one: show the first again.
  useEffect(() => { if (index >= count) setIndex(0); }, [index, count]);

  const go = useCallback((next: number) => {
    setIndex(() => (count === 0 ? 0 : (next + count) % count));
  }, [count]);

  useEffect(() => {
    if (count <= 1 || holding || reduced) return;
    const t = setInterval(() => setIndex((p) => (p + 1) % count), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [count, holding, reduced]);

  const swipe = useSwipe(() => go(index - 1), () => go(index + 1), setHolding);

  if (count === 0) return null;

  return (
    <div className={`${BANNER_FRAME} sm:h-60 md:h-72`} {...swipe}>
      {banners.map((b, i) => (
        <div
          key={b.id}
          className={`absolute inset-0 overflow-hidden rounded-[inherit] transition-opacity duration-700 ${i === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
          aria-hidden={i === index ? undefined : true}
        >
          <PromoSlide b={b} priority={i === 0} active={i === index} secondary={{ href: '/sportsbook?tab=live', label: 'Live betting' }} />
        </div>
      ))}

      {count > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous banner"
            onClick={() => go(index - 1)}
            className="absolute left-2 top-1/2 z-10 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur transition-opacity hover:bg-black/60 group-hover:opacity-100 sm:flex"
          >
            <FaChevronLeft size={13} />
          </button>
          <button
            type="button"
            aria-label="Next banner"
            onClick={() => go(index + 1)}
            className="absolute right-2 top-1/2 z-10 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur transition-opacity hover:bg-black/60 group-hover:opacity-100 sm:flex"
          >
            <FaChevronRight size={13} />
          </button>
          <SlideDots count={count} index={index} onGo={go} label="Go to banner" className="bottom-0.5 sm:bottom-1.5" />
        </>
      )}
    </div>
  );
}

/** Uploaded designs are stored as site-relative API paths ("/api/promotions/banner-images/7/"). */
function imageSrc(url: string) {
  return url.startsWith('/api/') ? `${config.apiUrl.replace(/\/api\/?$/, '')}${url}` : url;
}

const FOCUS: Record<NonNullable<Banner['focus']>, string> = { left: '15% 50%', center: '50% 50%', right: '85% 50%' };

const CTA = 'inline-flex min-h-10 items-center rounded-lg bg-win px-4 py-2 text-xs font-extrabold uppercase tracking-wide text-win-foreground shadow-lg transition-transform hover:scale-105 active:scale-95 sm:px-5 sm:text-sm';

/** One promo banner's content (photo or gradient art, copy and buttons), filling
 * its parent. Shared by the homepage slider and the sportsbook hero. `priority`
 * loads the image straight away (the first slide); the rest load lazily. */
export function PromoSlide({ b, secondary, priority = false, active = true }: {
  b: Banner; secondary?: { href: string; label: string } | null; priority?: boolean;
  /** This slide is the one on screen: its video plays and its movement and text entrance run. */
  active?: boolean;
}) {
  const videoAllowed = useVideoAllowed();
  const position = FOCUS[b.focus ?? 'center'];
  const href = b.link_url || '';
  const overlay = b.overlay_text !== false;
  const cta = b.cta_label && href ? (
    isExternal(href) ? (
      <a href={href} target="_blank" rel="noopener noreferrer" className={CTA}>{b.cta_label}</a>
    ) : (
      <Link href={href} className={CTA}>{b.cta_label}</Link>
    )
  ) : null;

  return (
    <>
      {b.image_url ? (
        <picture>
          {b.mobile_image_url && <source media="(max-width: 639px)" srcSet={imageSrc(b.mobile_image_url)} />}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageSrc(b.image_url)} alt={overlay ? '' : b.title}
            loading={priority ? 'eager' : 'lazy'} decoding="async" {...(priority ? { fetchPriority: 'high' as const } : {})}
            key={active ? 'on' : 'off'}
            className={`h-full w-full rounded-[inherit] object-cover ${active && b.motion === 'zoom' ? 'banner-zoom' : ''}`} style={{ objectPosition: position }}
          />
        </picture>
      ) : (
        <>
          <div className="absolute inset-0 rounded-[inherit]" style={{ background: b.bg }} />
          {b.big && (
            <div
              aria-hidden
              className="pointer-events-none absolute -right-2 top-1/2 -translate-y-1/2 select-none font-extrabold leading-[0.8] tracking-tighter text-white/[0.08]"
              style={{ fontSize: 'clamp(64px, 14vw, 190px)' }}
            >
              {b.big}
            </div>
          )}
        </>
      )}

      {b.video_url && active && videoAllowed && (
        <BannerVideo src={imageSrc(b.video_url)} poster={b.image_url ? imageSrc(b.image_url) : undefined} position={position} />
      )}
      {b.motion === 'shine' && <div aria-hidden className="banner-shine pointer-events-none absolute inset-0" />}

      {overlay ? (
        <>
          {/* Phones: the words sit at the bottom over a fade from below, so the top of the artwork stays clear. */}
          <div className="absolute inset-0 rounded-[inherit] bg-gradient-to-t from-black/85 via-black/40 to-transparent sm:bg-gradient-to-r sm:from-black/[0.86] sm:via-black/50 sm:to-transparent" />
          {/* Keyed on `active` so the words rise into place each time the slide comes round. */}
          <div key={active ? 'on' : 'off'} className="absolute inset-0 flex flex-col justify-end gap-1 p-4 pb-9 sm:justify-center sm:gap-2 sm:p-10 sm:pb-10">
            {b.eyebrow && (
              <span className="banner-rise w-fit shrink-0 rounded-md bg-white/15 px-2 py-0.5 text-[10px] font-bold tracking-wider text-white backdrop-blur-sm sm:px-2.5 sm:py-1 sm:text-[11px]">
                {b.eyebrow}
              </span>
            )}
            <p style={{ '--d': '80ms' } as React.CSSProperties} className="banner-rise line-clamp-2 max-w-xl shrink-0 text-lg font-extrabold leading-snug text-white drop-shadow sm:line-clamp-none sm:text-3xl sm:leading-tight md:text-4xl">
              {b.title}
            </p>
            {b.subtitle && (
              // Dropped on the narrowest phones, where the title and button need the room.
              <p style={{ '--d': '160ms' } as React.CSSProperties} className="banner-rise hidden shrink-0 line-clamp-1 max-w-md text-xs text-white/85 min-[380px]:block sm:line-clamp-2 sm:text-base">{b.subtitle}</p>
            )}
            {(cta || secondary) && (
              <div style={{ '--d': '240ms' } as React.CSSProperties} className="banner-rise mt-1 flex w-fit shrink-0 flex-wrap gap-2 sm:mt-2 sm:gap-3">
                {cta}
                {secondary && (
                  <Link
                    href={secondary.href}
                    className="hidden min-h-10 items-center rounded-lg border border-white/25 bg-white/10 px-4 py-2 text-xs font-semibold text-white backdrop-blur-sm hover:bg-white/20 min-[380px]:inline-flex sm:px-5 sm:text-sm"
                  >
                    {secondary.label}
                  </Link>
                )}
              </div>
            )}
          </div>
        </>
      ) : (
        // The design carries its own words: only the button goes on top.
        cta && <div className="absolute bottom-6 left-3 sm:bottom-6 sm:left-6">{cta}</div>
      )}
    </>
  );
}
