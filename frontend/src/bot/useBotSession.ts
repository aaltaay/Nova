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
  setBotFamilyKey,
  switchBotSession,
  patchBotSession,
  resolveProposal,
} from './api';
import type { BotFamily } from './types';

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

  /** Activate (ADR 042 B). A refusal comes back in the backend's words. */
  const activate = useCallback(async () => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => armBotSession());
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot activate failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

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

  /** ADR 044: the Bot switch. A refusal (the padlock, Live) comes back in the backend's words. */
  const setSwitch = useCallback(async (on: boolean) => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => switchBotSession(on));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot switch failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  /** A family's key (2026-10-15). A refusal (Live, an unreadable file) comes back in the backend's words. */
  const setKey = useCallback(async (family: BotFamily, on: boolean) => {
    setBusy(true);
    try {
      return await runBotSessionWrite(() => setBotFamilyKey(family, on));
    } catch (err) {
      setBotSessionError(err instanceof Error ? err.message : 'bot key failed');
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
    setSwitch,
    setKey,
    resolve,
  };
}
