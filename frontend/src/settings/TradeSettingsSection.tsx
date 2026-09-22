/**
 * Settings > Trade — Stocks defaults + Order Preferences + Practice Account sub-tabs.
 */
import { useState } from 'react';
import {
  TRADE_SETTINGS_SUB_TABS,
  type TradeSettingsSubTab,
} from './settingsNav';
import {
  readTradeDefaultsPrefs,
  type TradeDefaultsPrefs,
} from './tradeDefaultsPrefs';
import { PracticeAccountSettings } from './PracticeAccountSettings';
import { TradeOrderPreferencesForm } from './TradeOrderPreferencesForm';
import { TradeStocksDefaultsForm } from './TradeStocksDefaultsForm';

export function TradeSettingsSection() {
  const [subTab, setSubTab] = useState<TradeSettingsSubTab>('stocks');
  const [prefs, setPrefs] = useState<TradeDefaultsPrefs>(readTradeDefaultsPrefs);

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
        <TradeStocksDefaultsForm prefs={prefs} onChange={setPrefs} />
      )}
      {subTab === 'order_preferences' && <TradeOrderPreferencesForm />}
      {subTab === 'practice' && <PracticeAccountSettings />}
    </div>
  );
}
