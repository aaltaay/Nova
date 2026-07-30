/** Left-rail categories for the Settings overlay. */

export type SettingsSectionId =
  | 'general'
  | 'hotkeys'
  | 'trade'
  | 'alerts'
  | 'account';

export type TradeSettingsSubTab = 'stocks' | 'order_preferences';

export interface SettingsNavItem {
  id: SettingsSectionId;
  label: string;
}

export const SETTINGS_NAV: readonly SettingsNavItem[] = [
  { id: 'general', label: 'General' },
  { id: 'hotkeys', label: 'Hot Keys' },
  { id: 'trade', label: 'Trade' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'account', label: 'Account' },
] as const;

export const TRADE_SETTINGS_SUB_TABS: readonly {
  id: TradeSettingsSubTab;
  label: string;
}[] = [
  { id: 'stocks', label: 'Stocks' },
  { id: 'order_preferences', label: 'Order Preferences' },
] as const;

export const DEFAULT_SETTINGS_SECTION: SettingsSectionId = 'general';
