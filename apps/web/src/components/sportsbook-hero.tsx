'use client';

import { useCallback, useEffect, useState } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { BANNER_FRAME, PromoSlide, SlideDots, useLiveBanners, usePrefersReducedMotion, useSwipe, type Banner } from '@/components/banner-slider';

const AUTO_ADVANCE_MS = 7000;

/**
 * Sportsbook hero: the operator's sportsbook promos. Auto-advances, pausing
 * while the pointer is over it.
 */
export function SportsbookHero({ banners: initial }: { banners: Banner[] }) {
  const banners = useLiveBanners('sportsbook', initial);
  const slides = banners.map((b) => ({ key: `b${b.id}`, banner: b }));
  const count = slides.length;
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = usePrefersReducedMotion();

  const go = useCallback((next: number) => {
    setIndex(() => (count === 0 ? 0 : (next + count) % count));
  }, [count]);

  useEffect(() => {
    if (count <= 1 || paused || reduced) return;
    const t = setInterval(() => setIndex((p) => (p + 1) % count), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [count, paused, reduced]);

  const swipe = useSwipe(() => go(index - 1), () => go(index + 1), setPaused);

  useEffect(() => { if (index >= count) setIndex(0); }, [index, count]);

  if (count === 0) return null;

  return (
    // The margin lives here so the hero's gap appears and goes with the banners.
    <div className="mb-5">
    <div
      className={`${BANNER_FRAME} sm:h-60 md:h-64`}
      {...swipe}
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
          <PromoSlide b={s.banner} priority={i === 0} active={i === index} />
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
          <SlideDots count={count} index={index} onGo={go} label="Show banner" className="bottom-0.5 sm:bottom-1" />
        </>
      )}
    </div>
    </div>
  );
}
