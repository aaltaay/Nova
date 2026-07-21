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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
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
      setBusy(false);
    }
  };

  const handleTest = async (channelId?: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await testChannel(channelId);
      setMessage(result.ok ? 'Test sent.' : 'Test failed — see API status.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    setBusy(true);
    try {
      await updateChannel(id, { enabled });
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setBusy(false);
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
    setBusy(true);
    try {
      await deleteChannel(id);
      setMessage('Channel deleted.');
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel settings-panel alert-channels-panel">
      <h2 className="panel-title">Alert channels</h2>
      <p className="panel-subtitle">
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
          <button type="submit" className="btn-primary" disabled={busy || loading}>
            Add channel
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || loading || channels.length === 0}
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
                onClick={() => handleToggle(ch.id, !ch.enabled)}
              >
                {ch.enabled ? 'Disable' : 'Enable'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={busy || !ch.enabled}
                onClick={() => handleTest(ch.id)}
              >
                Test
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={busy}
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
