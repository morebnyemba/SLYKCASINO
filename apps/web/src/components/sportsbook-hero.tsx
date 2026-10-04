'use client';

import { useCallback, useEffect, useState } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { PromoSlide, type Banner } from '@/components/banner-slider';

const AUTO_ADVANCE_MS = 7000;

/**
 * Sportsbook hero: the operator's sportsbook promos. Auto-advances, pausing
 * while the pointer is over it.
 */
export function SportsbookHero({ banners }: { banners: Banner[] }) {
  const slides = banners.map((b) => ({ key: `b${b.id}`, banner: b }));
  const count = slides.length;
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  const go = useCallback((next: number) => {
    setIndex(() => (count === 0 ? 0 : (next + count) % count));
  }, [count]);

  useEffect(() => {
    if (count <= 1 || paused) return;
    const t = setInterval(() => setIndex((p) => (p + 1) % count), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [count, paused]);

  useEffect(() => { if (index >= count) setIndex(0); }, [index, count]);

  if (count === 0) return null;

  return (
    <div
      className="group relative h-56 overflow-hidden rounded-2xl sm:h-60 md:h-64"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      {slides.map((s, i) => (
        <div
          key={s.key}
          className={`absolute inset-0 transition-opacity duration-700 ${i === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
          aria-hidden={i === index ? undefined : true}
        >
          <PromoSlide b={s.banner} />
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
          <div className="absolute bottom-2.5 left-1/2 z-10 flex -translate-x-1/2 gap-1.5">
            {slides.map((s, i) => (
              <button
                key={s.key}
                type="button"
                aria-label={`Show banner ${i + 1}`}
                onClick={() => go(i)}
                className={`h-1.5 rounded-full transition-all ${i === index ? 'w-5 bg-white' : 'w-1.5 bg-white/40 hover:bg-white/70'}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
