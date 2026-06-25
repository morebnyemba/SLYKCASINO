'use client';

import {
  GiSoccerBall, GiBasketballBall, GiTennisRacket, GiBoxingGlove,
  GiBaseballBat, GiRunningShoe, GiPunchBlast, GiCardJoker, GiTrophyCup,
} from 'react-icons/gi';
import type { IconType } from 'react-icons';

export interface SportCategory {
  id: string;
  label: string;
  icon: IconType;
}

// ids match the backend `Event.Sport` choices exactly, so filtering is a direct equality check.
export const SPORT_CATEGORIES: SportCategory[] = [
  { id: 'football', label: 'Football', icon: GiSoccerBall },
  { id: 'basketball', label: 'Basketball', icon: GiBasketballBall },
  { id: 'tennis', label: 'Tennis', icon: GiTennisRacket },
  { id: 'mma', label: 'MMA', icon: GiPunchBlast },
  { id: 'boxing', label: 'Boxing', icon: GiBoxingGlove },
  { id: 'baseball', label: 'Baseball', icon: GiBaseballBat },
  { id: 'athletics', label: 'Athletics', icon: GiRunningShoe },
  { id: 'esports', label: 'Esports', icon: GiCardJoker },
];

interface SportsSidebarProps {
  activeId: string | null;
  onSelect: (id: string | null) => void;
  counts: Record<string, number>;
  className?: string;
}

export function SportsSidebar({ activeId, onSelect, counts, className = '' }: SportsSidebarProps) {
  return (
    <nav className={`space-y-1 ${className}`}>
      <p className="mb-1.5 px-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-muted-foreground">Sports</p>
      <button
        onClick={() => onSelect(null)}
        className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13.5px] font-semibold transition-colors ${
          activeId === null ? 'bg-secondary text-white' : 'bg-card text-foreground hover:bg-accent/10'
        }`}
      >
        <span className="flex w-5 justify-center"><GiTrophyCup size={16} /></span>
        <span>All sports</span>
      </button>
      {SPORT_CATEGORIES.map((cat) => {
        const Icon = cat.icon;
        const count = counts[cat.id] ?? 0;
        const active = activeId === cat.id;
        return (
          <button
            key={cat.id}
            onClick={() => onSelect(cat.id)}
            className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13.5px] font-semibold transition-colors ${
              active ? 'bg-secondary text-white' : 'bg-card text-foreground hover:bg-accent/10'
            }`}
          >
            <span className="flex w-5 justify-center"><Icon size={16} /></span>
            <span>{cat.label}</span>
            <span className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-bold ${
              active ? 'bg-white/20 text-white' : 'bg-chip text-muted-foreground'
            }`}>
              {count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
