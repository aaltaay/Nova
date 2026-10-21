/**
 * The forecaster's status for the Ahead panel (ADR 065): its exam and its report card, read from
 * `GET /api/ahead/status` at once and every `AHEAD_STATUS_POLL_MS` while `enabled` (the panel is open). `status` is
 * null until the first good answer and whenever the status cannot be read; then `problem` says why, and the panel
 * shows it (both null: the first read is still on its way).
 */
import { useEffect, useState } from 'react';
import { fetchAheadStatus } from './aheadApi';
import { AHEAD_STATUS_POLL_MS, AHEAD_WORDS } from './aheadConstants';
import type { AheadStatus } from './aheadTypes';

export interface AheadStatusRead {
  status: AheadStatus | null;
  /** Why the status could not be read (null when it was, or before the first read came back). */
  problem: string | null;
}

const NONE: AheadStatusRead = { status: null, problem: null };

export function useAheadStatus(enabled: boolean): AheadStatusRead {
  const [read, setRead] = useState<AheadStatusRead>(NONE);
  useEffect(() => {
    if (!enabled) return undefined;
    let ctrl: AbortController | null = null;
    const ask = () => {
      ctrl?.abort();
      const mine = new AbortController();
      ctrl = mine;
      fetchAheadStatus(mine.signal)
        .then((res) => {
          if (mine.signal.aborted) return;
          if (res.problem !== null) console.warn('Ahead status:', res.problem);
          setRead({ status: res.status, problem: res.status === null ? res.problem ?? AHEAD_WORDS.statusUnknown : null });
        })
        .catch((err: unknown) => {
          if (mine.signal.aborted) return;
          console.warn('Ahead status read failed', err);
          setRead({ status: null, problem: AHEAD_WORDS.readFailed });
        });
    };
    ask();
    const timer = setInterval(ask, AHEAD_STATUS_POLL_MS);
    return () => {
      clearInterval(timer);
      ctrl?.abort();
    };
  }, [enabled]);
  return enabled ? read : NONE;
}
