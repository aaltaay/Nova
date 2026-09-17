import { useCallback, useEffect, useState } from 'react';
import { fetchBotAudit, fetchBotProposals, fetchBotSession, patchBotSession, resolveProposal } from './api';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

export function useBotSession() {
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

  const patch = useCallback(async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      const next = await patchBotSession(body);
      setSession(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'bot patch failed');
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

  return { session, proposals, audit, error, busy, refresh, patch, resolve };
}
