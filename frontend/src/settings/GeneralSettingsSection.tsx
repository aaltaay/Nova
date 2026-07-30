/**
 * Settings > General — exchange filter + Alpaca/scanner panel.
 */
import { useState, type FormEvent } from 'react';
import { ExchangeFilterDropdown } from '../components/ExchangeFilterDropdown';
import { SettingsPanel } from '../components/SettingsPanel';
import type { ExchangeFilter } from '../hooks/useExchangeFilter';
import {
  SETTINGS_GENERAL_API_TITLE,
  SETTINGS_GENERAL_EXCHANGE_HINT,
  SETTINGS_GENERAL_EXCHANGE_TITLE,
} from '../constantGroups/trade_defaults';

export interface GeneralSettingsSectionProps {
  filter: ExchangeFilter;
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
  discoveryProvider: string;
  onSubmit: (e: FormEvent) => void;
  onCancel: () => void;
}

export function GeneralSettingsSection(props: GeneralSettingsSectionProps) {
  const [filterOpen, setFilterOpen] = useState(false);

  return (
    <div className="settings-general">
      <section className="settings-block">
        <h3 className="settings-block-title">{SETTINGS_GENERAL_EXCHANGE_TITLE}</h3>
        <p className="settings-block-hint">{SETTINGS_GENERAL_EXCHANGE_HINT}</p>
        <ExchangeFilterDropdown
          filter={props.filter}
          open={filterOpen}
          onToggle={() => setFilterOpen((o) => !o)}
          onClose={() => setFilterOpen(false)}
        />
      </section>

      <section className="settings-block">
        <h3 className="settings-block-title">{SETTINGS_GENERAL_API_TITLE}</h3>
        <SettingsPanel
          apiKey={props.apiKey}
          onApiKeyChange={props.onApiKeyChange}
          apiSecret={props.apiSecret}
          onApiSecretChange={props.onApiSecretChange}
          apiKeySet={props.apiKeySet}
          apiSecretSet={props.apiSecretSet}
          baseUrl={props.baseUrl}
          onBaseUrlChange={props.onBaseUrlChange}
          dataFeed={props.dataFeed}
          onDataFeedChange={props.onDataFeedChange}
          dataFeedOptions={props.dataFeedOptions}
          discoveryProvider={props.discoveryProvider}
          onSubmit={props.onSubmit}
          onCancel={props.onCancel}
        />
      </section>
    </div>
  );
}
