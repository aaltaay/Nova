import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import {
  getBotSessionSnapshot,
  refreshBotSessionNow,
  runBotSessionWrite,
  setBotSessionError,
  subscribeBotSession,
  voteBotPollInterval,
} from './botSessionPoller';
import {
  armBotSession,
  disarmBotSession,
  patchBotSession,
  resolveProposal,
} from './api';

const EMPTY = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};

export function useBotSession(pollMs = 0) {
  const snap = useSyncExternalStore(
    subscribeBotSession,
    getBotSessionSnapshot,
    () => EMPTY,
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => voteBotPollInterval(pollMs), [pollMs]);

  const refresh = useCallback(async () => {
    refreshBotSessionNow();
  }, []);

  const patch = useCallback(async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => patchBotSession(body));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot patch failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const activate = useCallback(async () => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => armBotSession({
        reenable: Boolean(snap.session?.soft_breaker_fired),
      }));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot activate failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, [snap.session?.soft_breaker_fired]);

  const stop = useCallback(async () => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => disarmBotSession());
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot stop failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const resolve = useCallback(async (id: string, action: 'accept' | 'reject') => {
    setBusy(true);
    try {
      await resolveProposal(id, action);
      refreshBotSessionNow();
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'proposal update failed');
    } finally {
      setBusy(false);
    }
  }, []);

  return {
    session: snap.session,
    proposals: snap.proposals,
    audit: snap.audit,
    error: snap.error,
    busy,
    refresh,
    patch,
    activate,
    stop,
    resolve,
  };
}
