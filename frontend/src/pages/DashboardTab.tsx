/**
 * Dashboard tab — configuration hub.
 * Houses the exchange filter (applied to all scanner tabs) + the Settings form
 * so users can tune API credentials and discovery provider without opening the
 * header Settings popover.
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
  onDiscoveryProviderChange: (v: string) => void;
  discoveryProviderOptions: string[];
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
  onDiscoveryProviderChange,
  discoveryProviderOptions,
  onSubmit,
}: Props) {
  const [filterOpen, setFilterOpen] = useState(false);

  return (
    <div className="dashboard-tab dashboard-config">
      {/* ── Exchange filter ───────────────────────────────────────────────── */}
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

      {/* ── Settings ─────────────────────────────────────────────────────── */}
      <section className="dashboard-section">
        <h3 className="dashboard-section-title">Settings</h3>
        <form className="dashboard-settings-form" onSubmit={onSubmit}>
          <div className="form-group">
            <label>API Key ID</label>
            <input
              type="text"
              value={apiKey}
              onChange={e => onApiKeyChange(e.target.value)}
              placeholder="APCA_API_KEY_ID"
            />
          </div>
          <div className="form-group">
            <label>API Secret Key</label>
            <input
              type="text"
              value={apiSecret}
              onChange={e => onApiSecretChange(e.target.value)}
              placeholder="••••••••••••••••"
            />
          </div>
          <div className="form-group">
            <label>Base URL</label>
            <input
              type="url"
              value={baseUrl}
              onChange={e => onBaseUrlChange(e.target.value)}
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
              IBKR uses your live Gateway connection; Alpaca uses the free screener.
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
