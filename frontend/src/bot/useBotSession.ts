/**
 * The bot session, read-only (ADR 072 retired the bots): the poller's snapshot of `GET /api/bot/session` and the
 * audit, for the day-cover alarms. A caller votes how often it wants the poll; nothing here writes.
 */
import { useCallback, useEffect, useSyncExternalStore } from 'react';
import {
  getBotSessionSnapshot,
  refreshBotSessionNow,
  subscribeBotSession,
  voteBotPollInterval,
} from './botSessionPoller';

const EMPTY = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};

export function useBotSession(pollMs = 0) {
  const snap = useSyncExternalStore(subscribeBotSession, getBotSessionSnapshot, () => EMPTY);
  useEffect(() => voteBotPollInterval(pollMs), [pollMs]);
  const refresh = useCallback(async () => {
    refreshBotSessionNow();
  }, []);
  return { session: snap.session, audit: snap.audit, error: snap.error, refresh };
}
