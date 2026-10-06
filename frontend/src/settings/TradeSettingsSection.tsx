/**
 * Settings > Trade — Stocks defaults + Order Preferences + Practice Account sub-tabs.
 */
import { useState } from 'react';
import {
  TRADE_SETTINGS_SUB_TABS,
  type TradeSettingsSubTab,
} from './settingsNav';
import { useConfirmedDeskVenue } from '../ibkr';
import { useTradeDefaultsPrefs } from './useTradeDefaultsPrefs';
import { PracticeAccountSettings } from './PracticeAccountSettings';
import { TradeOrderPreferencesForm } from './TradeOrderPreferencesForm';
import { TradeStocksDefaultsForm } from './TradeStocksDefaultsForm';

export function TradeSettingsSection() {
  const [subTab, setSubTab] = useState<TradeSettingsSubTab>('stocks');
  const venue = useConfirmedDeskVenue();
  const prefs = useTradeDefaultsPrefs(venue);

  return (
    <div className="settings-trade" data-testid="settings-trade">
      <nav className="settings-subnav" aria-label="Trade settings">
        {TRADE_SETTINGS_SUB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`settings-subnav-tab${subTab === t.id ? ' active' : ''}`}
            onClick={() => setSubTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {subTab === 'stocks' && (
        <TradeStocksDefaultsForm key={venue ?? 'unknown'} venue={venue} prefs={prefs} />
      )}
      {subTab === 'order_preferences' && <TradeOrderPreferencesForm />}
      {subTab === 'practice' && <PracticeAccountSettings />}
    </div>
  );
}
