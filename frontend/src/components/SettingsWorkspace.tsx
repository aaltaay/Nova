/**
 * Settings overlay sections: General, Alerts, Hotkeys.
 * Keeps App/Dashboard free of settings orchestration logic.
 */

import { useState, type FormEvent } from 'react';
import { AlertChannelsSettings } from './AlertChannelsSettings';
import { SettingsPanel } from './SettingsPanel';
import { HotkeyManager } from '../hotkeys/HotkeyManager';

export type SettingsSection = 'general' | 'alerts' | 'hotkeys';

interface SettingsWorkspaceProps {
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

const SECTIONS: { id: SettingsSection; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'hotkeys', label: 'Hotkeys' },
];

export function SettingsWorkspace(props: SettingsWorkspaceProps) {
  const [section, setSection] = useState<SettingsSection>('general');

  return (
    <div className="settings-workspace">
      <nav className="settings-workspace-nav" aria-label="Settings sections">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`settings-workspace-tab${section === s.id ? ' active' : ''}`}
            onClick={() => setSection(s.id)}
          >
            {s.label}
          </button>
        ))}
      </nav>
      {section === 'general' && (
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
      )}
      {section === 'alerts' && <AlertChannelsSettings />}
      {section === 'hotkeys' && <HotkeyManager />}
    </div>
  );
}
