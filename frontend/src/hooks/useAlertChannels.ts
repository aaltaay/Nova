/**
 * Alert channel CRUD + test fire against /api/alerts.
 */
import { useCallback, useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { ALERTS_API } from '../constants';

export interface AlertChannel {
  id: string;
  type: 'discord' | 'telegram' | 'webhook';
  enabled: boolean;
  name: string;
  webhook_url_masked?: string;
  webhook_url_set?: boolean;
  bot_token_masked?: string;
  bot_token_set?: boolean;
  chat_id_masked?: string;
  chat_id_set?: boolean;
}

export interface AlertChannelInput {
  type: AlertChannel['type'];
  name: string;
  enabled: boolean;
  webhook_url?: string;
  bot_token?: string;
  chat_id?: string;
}

export function useAlertChannels(enabled = true) {
  const [channels, setChannels] = useState<AlertChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusErrors, setStatusErrors] = useState<number>(0);

  const fetchChannels = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const [chRes, stRes] = await Promise.all([
        fetch(`${ALERTS_API}/channels`),
        fetch(`${ALERTS_API}/status`),
      ]);
      if (!chRes.ok) throw new Error(`channels HTTP ${chRes.status}`);
      const chData = await chRes.json();
      setChannels(chData.channels ?? []);
      if (stRes.ok) {
        const stData = await stRes.json();
        setStatusErrors(stData.error_count ?? 0);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load alert channels');
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  const createChannel = useCallback(async (input: AlertChannelInput) => {
    const res = await novaFetch(`${ALERTS_API}/channels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `create failed HTTP ${res.status}`);
    }
    await fetchChannels();
  }, [fetchChannels]);

  const updateChannel = useCallback(async (id: string, patch: Partial<AlertChannelInput>) => {
    const res = await novaFetch(`${ALERTS_API}/channels/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `update failed HTTP ${res.status}`);
    }
    await fetchChannels();
  }, [fetchChannels]);

  const deleteChannel = useCallback(async (id: string) => {
    const res = await novaFetch(`${ALERTS_API}/channels/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`delete failed HTTP ${res.status}`);
    await fetchChannels();
  }, [fetchChannels]);

  const testChannel = useCallback(async (channelId?: string, message?: string) => {
    const res = await novaFetch(`${ALERTS_API}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ channel_id: channelId ?? null, message: message ?? null }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `test failed HTTP ${res.status}`);
    await fetchChannels();
    return body;
  }, [fetchChannels]);

  return {
    channels,
    loading,
    error,
    statusErrors,
    fetchChannels,
    createChannel,
    updateChannel,
    deleteChannel,
    testChannel,
  };
}
