/**
 * Alert channel settings — Discord, Telegram, generic webhook CRUD + test fire.
 */
import { useState } from 'react';
import {
  ALERTS_CHANNEL_TYPE_LABELS,
  ALERTS_CHANNEL_TYPES,
  APP_DIALOG_DELETE_LABEL,
  type AlertChannelType,
} from '../constants';
import { useAlertChannels } from '../hooks/useAlertChannels';
import { confirmApp } from '../ux';

const EMPTY_FORM = {
  type: 'discord' as AlertChannelType,
  name: '',
  enabled: true,
  webhook_url: '',
  bot_token: '',
  chat_id: '',
};

/** The one channel request in flight; every button waits on it. */
type BusyWork = 'create' | 'test' | 'toggle' | 'delete';
/** Why a channel button is locked (ux/whyTip.ts). */
const WHY_BUSY: Record<BusyWork, string> = {
  create: 'Adding the channel -- wait for it to finish',
  test: 'Sending the test -- wait for it to finish',
  toggle: 'Saving the channel -- wait for it to finish',
  delete: 'Deleting the channel -- wait for it to finish',
};
const WHY_LOADING = 'Loading the channel list -- wait for it';
const WHY_LIST_FAILED = 'The channel list did not load -- see the error above';
const WHY_NO_CHANNELS = 'No channels yet -- add one first';
const WHY_CHANNEL_OFF = 'This channel is disabled -- Enable it to test it';

export function AlertChannelsSettings() {
  const {
    channels,
    loading,
    error,
    statusErrors,
    createChannel,
    updateChannel,
    deleteChannel,
    testChannel,
  } = useAlertChannels(true);

  const [form, setForm] = useState(EMPTY_FORM);
  const [busyWork, setBusyWork] = useState<BusyWork | null>(null);
  const busy = busyWork !== null;
  const [message, setMessage] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusyWork('create');
    setMessage(null);
    try {
      await createChannel({
        type: form.type,
        name: form.name || ALERTS_CHANNEL_TYPE_LABELS[form.type],
        enabled: form.enabled,
        webhook_url: form.webhook_url || undefined,
        bot_token: form.bot_token || undefined,
        chat_id: form.chat_id || undefined,
      });
      setForm(EMPTY_FORM);
      setMessage('Channel created.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Create failed');
    } finally {
      setBusyWork(null);
    }
  };

  const handleTest = async (channelId?: string) => {
    setBusyWork('test');
    setMessage(null);
    try {
      const result = await testChannel(channelId);
      setMessage(result.ok ? 'Test sent.' : 'Test failed — see API status.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setBusyWork(null);
    }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    setBusyWork('toggle');
    try {
      await updateChannel(id, { enabled });
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setBusyWork(null);
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await confirmApp({
      title: 'Delete alert channel?',
      message: 'This removes the channel permanently. You can add it again later.',
      confirmLabel: APP_DIALOG_DELETE_LABEL,
      tone: 'danger',
    });
    if (!ok) return;
    setBusyWork('delete');
    try {
      await deleteChannel(id);
      setMessage('Channel deleted.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusyWork(null);
    }
  };

  // Why each button is locked (ux/whyTip.ts): the request in flight, then the list itself.
  const busyWhy = busyWork ? WHY_BUSY[busyWork] : undefined;
  const addWhy = busyWhy ?? (loading ? WHY_LOADING : undefined);
  const testAllWhy = addWhy ?? (channels.length > 0 ? undefined : error ? WHY_LIST_FAILED : WHY_NO_CHANNELS);

  return (
    <div className="settings-alerts" data-testid="settings-alerts">
      <h3 className="settings-block-title">Alert channels</h3>
      <p className="settings-block-hint">
        Outbound HOD Momo + Nova OS notifications. Secrets are stored locally and masked in the API.
      </p>

      {statusErrors > 0 && (
        <p className="alert-status-warning" role="status">
          {statusErrors} recent dispatch error(s) — check channel URLs/tokens.
        </p>
      )}
      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-hint">{message}</p>}

      <form onSubmit={handleCreate} className="alert-channel-form">
        <div className="form-row">
          <div className="form-group">
            <label>Type</label>
            <select
              value={form.type}
              onChange={e => setForm(f => ({ ...f, type: e.target.value as AlertChannelType }))}
            >
              {ALERTS_CHANNEL_TYPES.map(t => (
                <option key={t} value={t}>
                  {ALERTS_CHANNEL_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Name</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="My Discord alerts"
            />
          </div>
        </div>

        {(form.type === 'discord' || form.type === 'webhook') && (
          <div className="form-group">
            <label>Webhook URL</label>
            <input
              type="url"
              value={form.webhook_url}
              onChange={e => setForm(f => ({ ...f, webhook_url: e.target.value }))}
              placeholder="https://..."
              required
            />
          </div>
        )}

        {form.type === 'telegram' && (
          <>
            <div className="form-group">
              <label>Bot token</label>
              <input
                type="password"
                value={form.bot_token}
                onChange={e => setForm(f => ({ ...f, bot_token: e.target.value }))}
                placeholder="••••••••"
                required
              />
            </div>
            <div className="form-group">
              <label>Chat ID</label>
              <input
                type="text"
                value={form.chat_id}
                onChange={e => setForm(f => ({ ...f, chat_id: e.target.value }))}
                placeholder="-1001234567890"
                required
              />
            </div>
          </>
        )}

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={e => setForm(f => ({ ...f, enabled: e.target.checked }))}
          />
          Enabled
        </label>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={busy || loading} data-why={addWhy}>
            Add channel
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || loading || channels.length === 0}
            data-why={testAllWhy}
            onClick={() => handleTest()}
          >
            Test all enabled
          </button>
        </div>
      </form>

      {loading && <p>Loading channels…</p>}

      <ul className="alert-channel-list">
        {channels.map(ch => (
          <li key={ch.id} className="alert-channel-item">
            <div className="alert-channel-meta">
              <strong>{ch.name}</strong>
              <span className="badge">{ALERTS_CHANNEL_TYPE_LABELS[ch.type]}</span>
              {ch.enabled ? (
                <span className="badge badge-ok">enabled</span>
              ) : (
                <span className="badge badge-muted">disabled</span>
              )}
            </div>
            <div className="alert-channel-secrets">
              {ch.webhook_url_set && <span>URL: {ch.webhook_url_masked}</span>}
              {ch.bot_token_set && <span>Token: {ch.bot_token_masked}</span>}
              {ch.chat_id_set && <span>Chat: {ch.chat_id_masked}</span>}
            </div>
            <div className="form-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                data-why={busyWhy}
                onClick={() => handleToggle(ch.id, !ch.enabled)}
              >
                {ch.enabled ? 'Disable' : 'Enable'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={busy || !ch.enabled}
                data-why={busyWhy ?? (ch.enabled ? undefined : WHY_CHANNEL_OFF)}
                onClick={() => handleTest(ch.id)}
              >
                Test
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={busy}
                data-why={busyWhy}
                onClick={() => handleDelete(ch.id)}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
