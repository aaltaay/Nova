/**
 * SettingsPanel — Alpaca news/listing credentials + feed tier.
 * Scanner discovery is IBKR-only (not selectable). Presentational only.
 */
import type { FormEvent } from 'react';
import { DATA_FEED_LABELS, DISCOVERY_PROVIDER_LABELS } from '../constants';

interface SettingsPanelProps {
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  apiSecret: string;
  onApiSecretChange: (value: string) => void;
  apiKeySet?: boolean;
  apiSecretSet?: boolean;
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  dataFeed: string;
  onDataFeedChange: (value: string) => void;
  dataFeedOptions: string[];
  /** Locked to ibkr — shown read-only. */
  discoveryProvider: string;
  onSubmit: (e: FormEvent) => void;
  onCancel: () => void;
}

export function SettingsPanel({
  apiKey,
  onApiKeyChange,
  apiSecret,
  onApiSecretChange,
  apiKeySet = false,
  apiSecretSet = false,
  baseUrl,
  onBaseUrlChange,
  dataFeed,
  onDataFeedChange,
  dataFeedOptions,
  discoveryProvider,
  onSubmit,
  onCancel,
}: SettingsPanelProps) {
  const scannerLabel =
    DISCOVERY_PROVIDER_LABELS[discoveryProvider] || 'Interactive Brokers (Gateway)';

  return (
    <div className="panel settings-panel">
      <h2 className="panel-title">Settings</h2>
      <form onSubmit={onSubmit}>
        <div className="form-group">
          <label>Scanner</label>
          <input type="text" value={scannerLabel} readOnly className="feed-select" />
          <span className="form-hint">
            Gappers/gainers/losers come from your IB Gateway connection only.
          </span>
        </div>
        <div className="form-group">
          <label>Alpaca API Key ID (news / listing)</label>
          <input
            type="text"
            value={apiKey}
            onChange={e => onApiKeyChange(e.target.value)}
            placeholder={apiKeySet ? 'Saved (leave blank to keep)' : 'APCA_API_KEY_ID'}
            required={!apiKeySet}
            autoComplete="off"
          />
        </div>
        <div className="form-group">
          <label>Alpaca API Secret (news / listing)</label>
          <input
            type="password"
            value={apiSecret}
            onChange={e => onApiSecretChange(e.target.value)}
            placeholder={apiSecretSet ? 'Saved (leave blank to keep)' : 'APCA_API_SECRET_KEY'}
            required={!apiSecretSet}
            autoComplete="off"
          />
        </div>
        <div className="form-group">
          <label>Alpaca Base URL</label>
          <input
            type="url"
            value={baseUrl}
            onChange={e => onBaseUrlChange(e.target.value)}
            required
          />
        </div>
        <div className="form-group">
          <label>Alpaca Data Feed (aux)</label>
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
            Used for news/listing aux only — not live scanner prices. IEX is free;
            SIP needs a paid Alpaca plan.
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
