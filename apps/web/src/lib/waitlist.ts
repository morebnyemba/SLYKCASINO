'use client';

import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useAuth } from '@/lib/auth-context';
import { authedDelete, authedGet, authedPost } from '@/lib/use-api';

/** Which coming-soon games this player asked to hear about: one shared store for every tile. */
let waiting = new Set<number>();
let loadedFor: string | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
const snapshot = () => waiting;
const EMPTY = new Set<number>();

export function useWaitlist() {
  const { accessToken, user } = useAuth();
  const ids = useSyncExternalStore(subscribe, snapshot, () => EMPTY);

  useEffect(() => {
    if (!accessToken || !user || loadedFor === user.username) return;
    loadedFor = user.username;
    void authedGet<{ games: number[] }>('/casino/waitlist/', accessToken).then((res) => {
      if (res.data) { waiting = new Set(res.data.games); emit(); }
    });
  }, [accessToken, user]);

  const set = useCallback(async (gameId: number, on: boolean): Promise<string | null> => {
    if (!accessToken) return 'login';
    const res = on
      ? await authedPost<{ waiting: boolean }>(`/casino/games/${gameId}/notify/`, {}, accessToken)
      : await authedDelete<{ waiting: boolean }>(`/casino/games/${gameId}/notify/`, accessToken);
    if (res.error) return res.error;
    waiting = new Set(waiting);
    if (on) waiting.add(gameId); else waiting.delete(gameId);
    emit();
    return null;
  }, [accessToken]);

  return { ids, set, signedIn: !!accessToken };
}
