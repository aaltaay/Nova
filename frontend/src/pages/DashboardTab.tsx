/**
 * Dashboard tab — configuration hub.
 * Exchange filter + Settings (Alpaca news/listing aux). Scanner is IBKR-only.
 */
import { useState } from 'react';
import { ExchangeFilterDropdown } from '../components/ExchangeFilterDropdown';
import type { ExchangeFilter } from '../hooks/useExchangeFilter';
import { DATA_FEED_LABELS, DISCOVERY_PROVIDER_LABELS } from '../constants';
import type { FormEvent } from 'react';

interface SettingsProps {
  apiKey: string;
  onApiKeyChange: (v: string) => void;
  apiSecret: string;
  onApiSecretChange: (v: string) => void;
  baseUrl: string;
  onBaseUrlChange: (v: string) => void;
  dataFeed: string;
  onDataFeedChange: (v: string) => void;
  dataFeedOptions: string[];
  discoveryProvider: string;
  onSubmit: (e: FormEvent) => void;
}

interface Props extends SettingsProps {
  filter: ExchangeFilter;
}

export function DashboardTab({
  filter,
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
  onSubmit,
}: Props) {
  const [filterOpen, setFilterOpen] = useState(false);
  const scannerLabel =
    DISCOVERY_PROVIDER_LABELS[discoveryProvider] || 'Interactive Brokers (Gateway)';

  return (
    <div className="dashboard-tab dashboard-config">
      <section className="dashboard-section">
        <h3 className="dashboard-section-title">Exchange Filter</h3>
        <p className="dashboard-section-hint">
          Only rows from checked exchanges appear in Gappers, Gainers, After Hours, and
          Catalysts tabs. Selection is saved automatically.
        </p>
        <ExchangeFilterDropdown
          filter={filter}
          open={filterOpen}
          onToggle={() => setFilterOpen(o => !o)}
          onClose={() => setFilterOpen(false)}
        />
      </section>

      <section className="dashboard-section">
        <h3 className="dashboard-section-title">Settings</h3>
        <form className="dashboard-settings-form" onSubmit={onSubmit}>
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
              placeholder="APCA_API_KEY_ID"
            />
          </div>
          <div className="form-group">
            <label>Alpaca API Secret (news / listing)</label>
            <input
              type="text"
              value={apiSecret}
              onChange={e => onApiSecretChange(e.target.value)}
              placeholder="••••••••••••••••"
            />
          </div>
          <div className="form-group">
            <label>Alpaca Base URL</label>
            <input
              type="url"
              value={baseUrl}
              onChange={e => onBaseUrlChange(e.target.value)}
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
              News/listing aux only — not live scanner prices.
            </span>
          </div>
          <div className="form-row">
            <button type="submit">Update &amp; Connect</button>
          </div>
        </form>
      </section>
    </div>
  );
}
