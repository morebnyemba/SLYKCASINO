'use client';

import { useRef } from 'react';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';

interface CarouselProps {
  children: React.ReactNode;
  className?: string;
}

export function Carousel({ children, className = '' }: CarouselProps) {
  const trackRef = useRef<HTMLDivElement>(null);

  function scrollBy(dir: 1 | -1) {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({ left: dir * track.clientWidth * 0.8, behavior: 'smooth' });
  }

  return (
    <div className={`group relative ${className}`}>
      <div
        ref={trackRef}
        className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </div>
      <button
        type="button"
        aria-label="Scroll left"
        onClick={() => scrollBy(-1)}
        className="absolute left-1 top-1/2 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-foreground/80 text-white opacity-0 shadow-md transition-opacity group-hover:opacity-100 sm:flex"
      >
        <FaChevronLeft size={13} />
      </button>
      <button
        type="button"
        aria-label="Scroll right"
        onClick={() => scrollBy(1)}
        className="absolute right-1 top-1/2 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-foreground/80 text-white opacity-0 shadow-md transition-opacity group-hover:opacity-100 sm:flex"
      >
        <FaChevronRight size={13} />
      </button>
    </div>
  );
}

export function CarouselItem({ children, className = '' }: CarouselProps) {
  return <div className={`shrink-0 snap-start ${className}`}>{children}</div>;
}
