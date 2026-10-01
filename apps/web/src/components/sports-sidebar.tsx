'use client';

import {
  GiSoccerBall, GiBasketballBall, GiTennisRacket, GiBoxingGlove,
  GiBaseballBat, GiRunningShoe, GiPunchBlast, GiCardJoker,
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
