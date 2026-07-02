'use client';

import { useEffect, useState } from 'react';
import { FaTrophy } from 'react-icons/fa';
import { config } from '@/lib/config';

interface RecentWin {
  id: number;
  game_name: string;
  stake: string;
  win: string;
  created_at: string;
}

// Shown only until the casino win feed has real rounds to report.
const FALLBACK_WINS: RecentWin[] = [
  { id: -1, game_name: 'SLÝKBETS Aviator', stake: '5.00', win: '24.80', created_at: '' },
  { id: -2, game_name: 'Golden Wheel', stake: '2.00', win: '7.40', created_at: '' },
  { id: -3, game_name: 'Lucky Slots', stake: '10.00', win: '18.60', created_at: '' },
  { id: -4, game_name: 'Blackjack Classic', stake: '15.00', win: '30.00', created_at: '' },
  { id: -5, game_name: 'Live Baccarat', stake: '8.00', win: '14.40', created_at: '' },
  { id: -6, game_name: 'Mega Dice', stake: '3.00', win: '21.00', created_at: '' },
  { id: -7, game_name: 'Roulette Pro', stake: '6.00', win: '12.00', created_at: '' },
  { id: -8, game_name: 'Virtual League', stake: '4.00', win: '9.20', created_at: '' },
];

/**
 * Live "recent winners" ticker — public social proof, polled from the casino
 * win feed. Pauses on hover so a player can read an entry.
 */
export function WinnersTicker() {
  const [wins, setWins] = useState<RecentWin[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${config.apiUrl}/casino/rounds/recent-wins/`, { cache: 'no-store' });
        if (res.ok && !cancelled) setWins((await res.json()) as RecentWin[]);
      } catch { /* ignore */ }
    }
    void load();
    const interval = setInterval(load, 8000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  // Duplicate the list so the marquee scrolls seamlessly.
  const items = wins.length > 0 ? [...wins, ...wins] : [...FALLBACK_WINS, ...FALLBACK_WINS];

  return (
    <div className="flex items-center gap-3 overflow-hidden rounded-lg border border-border bg-card py-2">
      <span className="flex shrink-0 items-center gap-1.5 pl-3 text-xs font-semibold uppercase tracking-wide text-secondary">
        <FaTrophy size={12} /> Live wins
      </span>
      <div className="overflow-hidden">
        <div className="flex w-max animate-marquee gap-2">
          {items.map((w, i) => {
            const mult = parseFloat(w.win) / Math.max(parseFloat(w.stake), 0.01);
            return (
              <span
                key={`${w.id}-${i}`}
                className="flex shrink-0 items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs"
              >
                <span className="font-medium text-foreground">{w.game_name}</span>
                <span className="font-mono font-semibold text-green-500">+{parseFloat(w.win).toFixed(2)}</span>
                {mult >= 2 && <span className="font-mono text-yellow-400">{mult.toFixed(1)}×</span>}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
