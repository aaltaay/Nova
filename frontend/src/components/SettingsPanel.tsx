/**
 * SettingsPanel — Alpaca credentials, data feed tier, and scanner provider toggle.
 * Extracted from App.tsx so the settings form stays modular (App.tsx owns state
 * and fetch/save logic; this component is purely presentational).
 */
import type { FormEvent } from 'react';
import { DATA_FEED_LABELS, DISCOVERY_PROVIDER_LABELS } from '../constants';

interface SettingsPanelProps {
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  apiSecret: string;
  onApiSecretChange: (value: string) => void;
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  dataFeed: string;
  onDataFeedChange: (value: string) => void;
  dataFeedOptions: string[];
  discoveryProvider: string;
  onDiscoveryProviderChange: (value: string) => void;
  discoveryProviderOptions: string[];
  onSubmit: (e: FormEvent) => void;
  onCancel: () => void;
}

export function SettingsPanel({
  apiKey,
  onApiKeyChange,
  apiSecret,
  onApiSecretChange,
  baseUrl,
  onBaseUrlChange,
  dataFeed,
  onDataFeedChange,
  dataFeedOptions,
  discoveryProvider,
  onDiscoveryProviderChange,
  discoveryProviderOptions,
  onSubmit,
  onCancel,
}: SettingsPanelProps) {
  return (
    <div className="panel settings-panel">
      <h2 className="panel-title">Settings</h2>
      <form onSubmit={onSubmit}>
        <div className="form-group">
          <label>API Key ID</label>
          <input
            type="text"
            value={apiKey}
            onChange={e => onApiKeyChange(e.target.value)}
            placeholder="APCA_API_KEY_ID"
            required
          />
        </div>
        <div className="form-group">
          <label>API Secret Key</label>
          <input
            type="text"
            value={apiSecret}
            onChange={e => onApiSecretChange(e.target.value)}
            placeholder="••••••••••••••••"
            required
          />
        </div>
        <div className="form-group">
          <label>Base URL</label>
          <input
            type="url"
            value={baseUrl}
            onChange={e => onBaseUrlChange(e.target.value)}
            required
          />
        </div>
        <div className="form-group">
          <label>Data Feed</label>
          <select
            value={dataFeed}
            onChange={e => onDataFeedChange(e.target.value)}
            className="feed-select"
          >
            {dataFeedOptions.map(f => (
              <option key={f} value={f}>{DATA_FEED_LABELS[f] || f.toUpperCase()}</option>
            ))}
          </select>
          <span className="form-hint">
            IEX is free. SIP requires a paid Alpaca data subscription.
          </span>
        </div>
        <div className="form-group">
          <label>Scanner Source</label>
          <select
            value={discoveryProvider}
            onChange={e => onDiscoveryProviderChange(e.target.value)}
            className="feed-select"
          >
            {discoveryProviderOptions.map(p => (
              <option key={p} value={p}>{DISCOVERY_PROVIDER_LABELS[p] || p.toUpperCase()}</option>
            ))}
          </select>
          <span className="form-hint">
            Gappers/gainers/losers source. IBKR uses your live Gateway connection;
            Alpaca uses the free screener. News and fundamentals stay the same either way.
          </span>
        </div>
        <div className="form-row">
          <button type="submit">Update &amp; Connect</button>
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
