'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';

export interface Banner {
  id: number | string;
  title: string;
  subtitle?: string;
  image_url: string;
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
        const content = (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={b.image_url} alt={b.title} className="h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/45 to-transparent" />
            <div className="absolute inset-0 flex flex-col justify-center gap-2 p-6 sm:p-10">
              <p className="max-w-xl text-2xl font-extrabold leading-tight text-white drop-shadow sm:text-3xl md:text-4xl">
                {b.title}
              </p>
              {b.subtitle && (
                <p className="max-w-md text-sm text-white/85 sm:text-base">{b.subtitle}</p>
              )}
              {b.cta_label && (
                <span className="mt-2 inline-flex w-fit items-center rounded-lg bg-secondary px-5 py-2 text-sm font-bold uppercase tracking-wide text-white shadow-lg transition-transform group-hover:scale-105">
                  {b.cta_label}
                </span>
              )}
            </div>
          </>
        );

        return (
          <div
            key={b.id}
            className={`absolute inset-0 transition-opacity duration-700 ${i === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
            aria-hidden={i === index ? undefined : true}
          >
            {href ? (
              isExternal(href) ? (
                <a href={href} className="block h-full w-full" target="_blank" rel="noopener noreferrer">{content}</a>
              ) : (
                <Link href={href} className="block h-full w-full">{content}</Link>
              )
            ) : (
              <div className="h-full w-full">{content}</div>
            )}
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
