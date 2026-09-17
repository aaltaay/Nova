import { useCallback, useEffect, useState } from 'react';
import {
  armBotSession,
  disarmBotSession,
  fetchBotAudit,
  fetchBotProposals,
  fetchBotSession,
  patchBotSession,
  resolveProposal,
} from './api';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

export function useBotSession(pollMs = 0) {
  const [session, setSession] = useState<BotSession | null>(null);
  const [proposals, setProposals] = useState<BotProposal[]>([]);
  const [audit, setAudit] = useState<BotAuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [next, props, entries] = await Promise.all([
        fetchBotSession(),
        fetchBotProposals(),
        fetchBotAudit(),
      ]);
      setSession(next);
      setProposals(props);
      setAudit(entries);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'bot session failed');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!pollMs) return undefined;
    const id = window.setInterval(() => {
      void refresh();
    }, pollMs);
    return () => window.clearInterval(id);
  }, [pollMs, refresh]);

  const patch = useCallback(async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      const next = await patchBotSession(body);
      setSession(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'bot patch failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const activate = useCallback(async () => {
    setBusy(true);
    try {
      const next = await armBotSession({
        reenable: Boolean(session?.soft_breaker_fired),
      });
      setSession(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'bot activate failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, [session?.soft_breaker_fired]);

  const stop = useCallback(async () => {
    setBusy(true);
    try {
      const next = await disarmBotSession();
      setSession(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'bot stop failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const resolve = useCallback(async (id: string, action: 'accept' | 'reject') => {
    setBusy(true);
    try {
      await resolveProposal(id, action);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'proposal update failed');
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return { session, proposals, audit, error, busy, refresh, patch, activate, stop, resolve };
}
