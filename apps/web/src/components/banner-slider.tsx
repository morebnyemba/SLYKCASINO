'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';

export interface Banner {
  id: number | string;
  title: string;
  subtitle?: string;
  /** Photo banner, uploaded by an operator in the admin app. */
  image_url?: string;
  /** Brand-style gradient background (CSS `background` value), used when no photo is set. */
  bg?: string;
  /** Large faded decorative figure shown over a gradient banner, e.g. "2.48×". */
  big?: string;
  eyebrow?: string;
  link_url?: string;
  cta_label?: string;
}

const AUTO_ADVANCE_MS = 6000;

function isExternal(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

/**
 * Full-width promotional banner slider. Shows one wide banner at a time with
 * auto-advance, dots, and hover arrows. Banners are managed by operators in the
 * admin app; `banners` is fetched server-side and passed in.
 */
export function BannerSlider({ banners }: { banners: Banner[] }) {
  const [index, setIndex] = useState(0);
  const count = banners.length;

  const go = useCallback((next: number) => {
    setIndex((prev) => (count === 0 ? 0 : (next + count) % count));
  }, [count]);

  useEffect(() => {
    if (count <= 1) return;
    const t = setInterval(() => setIndex((p) => (p + 1) % count), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [count]);

  if (count === 0) return null;

  return (
    <div className="group relative h-44 overflow-hidden rounded-2xl sm:h-56 md:h-72">
      {banners.map((b, i) => {
        const href = b.link_url || '';

        return (
          <div
            key={b.id}
            className={`absolute inset-0 transition-opacity duration-700 ${i === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
            aria-hidden={i === index ? undefined : true}
          >
            {b.image_url ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={b.image_url} alt={b.title} className="h-full w-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent" />
              </>
            ) : (
              <>
                <div className="absolute inset-0" style={{ background: b.bg }} />
                {b.big && (
                  <div
                    aria-hidden
                    className="pointer-events-none absolute -right-2 top-1/2 -translate-y-1/2 select-none font-extrabold leading-[0.8] tracking-tighter text-white/[0.08]"
                    style={{ fontSize: 'clamp(64px, 14vw, 190px)' }}
                  >
                    {b.big}
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-r from-black/[0.86] via-black/50 to-transparent" />
              </>
            )}
            <div className="absolute inset-0 flex flex-col justify-center gap-2 p-6 sm:p-10">
              {b.eyebrow && (
                <span className="w-fit rounded-md bg-white/15 px-2.5 py-1 text-[11px] font-bold tracking-wider text-white backdrop-blur-sm">
                  {b.eyebrow}
                </span>
              )}
              <p className="max-w-xl text-2xl font-extrabold leading-tight text-white drop-shadow sm:text-3xl md:text-4xl">
                {b.title}
              </p>
              {b.subtitle && (
                <p className="max-w-md text-sm text-white/85 sm:text-base">{b.subtitle}</p>
              )}
              <div className="mt-2 flex w-fit gap-3">
                {b.cta_label && href && (
                  isExternal(href) ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center rounded-lg bg-secondary px-5 py-2 text-sm font-bold uppercase tracking-wide text-white shadow-lg transition-transform hover:scale-105"
                    >
                      {b.cta_label}
                    </a>
                  ) : (
                    <Link
                      href={href}
                      className="inline-flex items-center rounded-lg bg-secondary px-5 py-2 text-sm font-bold uppercase tracking-wide text-white shadow-lg transition-transform hover:scale-105"
                    >
                      {b.cta_label}
                    </Link>
                  )
                )}
                <Link
                  href="/casino"
                  className="inline-flex items-center rounded-lg border border-white/25 bg-white/10 px-5 py-2 text-sm font-semibold text-white backdrop-blur-sm hover:bg-white/20"
                >
                  Try demo
                </Link>
              </div>
            </div>
          </div>
        );
      })}

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

          <div className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 gap-1.5">
            {banners.map((b, i) => (
              <button
                key={b.id}
                type="button"
                aria-label={`Go to banner ${i + 1}`}
                onClick={() => go(i)}
                className={`h-1.5 rounded-full transition-all ${i === index ? 'w-6 bg-white' : 'w-1.5 bg-white/50 hover:bg-white/80'}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
