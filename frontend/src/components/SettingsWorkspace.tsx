/**
 * Webull-style Settings overlay: left rail + right content.
 * Mounted by SettingsHost at AppShell (Scanner + Trader).
 */
import { useEffect, useState, type FormEvent } from 'react';
import { AlertChannelsSettings } from './AlertChannelsSettings';
import { HotkeyManager } from '../hotkeys/HotkeyManager';
import {
  SETTINGS_CLOSE_LABEL,
  SETTINGS_OVERLAY_TITLE,
} from '../constantGroups/trade_defaults';
import type { ExchangeFilter } from '../hooks/useExchangeFilter';
import { AccountSettingsSection } from '../settings/AccountSettingsSection';
import { GeneralSettingsSection } from '../settings/GeneralSettingsSection';
import {
  DEFAULT_SETTINGS_SECTION,
  SETTINGS_NAV,
  type SettingsSectionId,
} from '../settings/settingsNav';
import { TradeSettingsSection } from '../settings/TradeSettingsSection';
import { SensorBoard } from '../sensors/SensorBoard';

export type SettingsSection = SettingsSectionId;

interface SettingsWorkspaceProps {
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
  initialSection?: SettingsSectionId;
}

export function SettingsWorkspace(props: SettingsWorkspaceProps) {
  const [section, setSection] = useState<SettingsSectionId>(
    props.initialSection ?? DEFAULT_SETTINGS_SECTION,
  );

  const onCancel = props.onCancel;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCancel();
      }
    };
    document.addEventListener('keydown', onKey, true);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.body.style.overflow = prev;
    };
  }, [onCancel]);

  return (
    <div
      className="settings-overlay"
      data-testid="settings-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={SETTINGS_OVERLAY_TITLE}
    >
      <button
        type="button"
        className="settings-overlay-backdrop"
        aria-label={SETTINGS_CLOSE_LABEL}
        onClick={props.onCancel}
      />
      <div className="settings-overlay-panel">
        <header className="settings-overlay-header">
          <h2 className="settings-overlay-title">{SETTINGS_OVERLAY_TITLE}</h2>
          <button
            type="button"
            className="settings-overlay-close"
            onClick={props.onCancel}
          >
            {SETTINGS_CLOSE_LABEL}
          </button>
        </header>
        <div className="settings-overlay-body">
          <nav className="settings-rail" aria-label="Settings categories">
            {SETTINGS_NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`settings-rail-item${section === item.id ? ' active' : ''}`}
                onClick={() => setSection(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="settings-overlay-content">
            {section === 'general' && (
              <GeneralSettingsSection
                filter={props.filter}
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
            )}
            {section === 'hotkeys' && <HotkeyManager />}
            {section === 'trade' && <TradeSettingsSection />}
            {section === 'alerts' && <AlertChannelsSettings />}
            {section === 'account' && (
              <AccountSettingsSection onClose={props.onCancel} />
            )}
            {section === 'sensors' && <SensorBoard />}
          </div>
        </div>
      </div>
    </div>
  );
}
