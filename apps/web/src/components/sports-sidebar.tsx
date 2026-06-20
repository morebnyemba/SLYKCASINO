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
      <button
        onClick={() => onSelect(null)}
        className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors ${
          activeId === null ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-accent/10'
        }`}
      >
        <span className="flex items-center gap-2"><GiTrophyCup size={16} /> All sports</span>
      </button>
      {SPORT_CATEGORIES.map((cat) => {
        const Icon = cat.icon;
        const count = counts[cat.id] ?? 0;
        return (
          <button
            key={cat.id}
            onClick={() => onSelect(cat.id)}
            className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeId === cat.id ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-accent/10'
            }`}
          >
            <span className="flex items-center gap-2"><Icon size={16} /> {cat.label}</span>
            <span className={`text-xs ${activeId === cat.id ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
              {count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
