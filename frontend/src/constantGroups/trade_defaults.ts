/**
 * Trade > Stocks default order values (Settings).
 * ManualOrderTicket reads these via tradeDefaultsPrefs localStorage.
 */

export const TRADE_DEFAULTS_STORAGE_KEY = 'nova.trade.defaults.v1';

export type TradeDefaultOrderType = 'MKT' | 'LMT' | 'STP';
export type TradeDefaultTradingHours = 'rth' | 'extended';
export type TradeDefaultTif = 'DAY';
export type TradeDefaultLimitSource = 'ask_bid' | 'last' | 'mid';

export const TRADE_DEFAULT_ORDER_TYPE: TradeDefaultOrderType = 'MKT';
export const TRADE_DEFAULT_QUANTITY = 100;
export const TRADE_DEFAULT_TRADING_HOURS: TradeDefaultTradingHours = 'rth';
export const TRADE_DEFAULT_TIF: TradeDefaultTif = 'DAY';
export const TRADE_DEFAULT_LIMIT_SOURCE: TradeDefaultLimitSource = 'ask_bid';
export const TRADE_DEFAULT_STOP_OFFSET_PCT = 1;

export const TRADE_DEFAULTS_SECTION_TITLE = 'Default Order Values';
export const TRADE_DEFAULTS_ORDER_TYPE_LABEL = 'Order Type';
export const TRADE_DEFAULTS_QUANTITY_LABEL = 'Quantity';
export const TRADE_DEFAULTS_HOURS_LABEL = 'Trading Hours';
export const TRADE_DEFAULTS_TIF_LABEL = 'Time-in-Force';
export const TRADE_DEFAULTS_LIMIT_SOURCE_LABEL = 'Limit Price';
export const TRADE_DEFAULTS_STOP_OFFSET_LABEL = 'Stop Offset (%)';
export const TRADE_DEFAULTS_EH_HINT =
  'Extended hours requires Limit orders (IBKR).';
export const TRADE_DEFAULTS_TIF_HINT = 'DAY only for now — GTC coming later.';

export const TRADE_ORDER_PREFS_SKIP_CONFIRM_LABEL =
  'Skip place-order confirmation dialog';
export const TRADE_ORDER_PREFS_SKIP_CONFIRM_HINT =
  'When on, Place submits immediately after PIN unlock (still respects IBKR spend gates).';

export const SETTINGS_GEAR_LABEL = 'Settings';
export const SETTINGS_GEAR_TITLE = 'Open Settings';
export const SETTINGS_OVERLAY_TITLE = 'Settings';
export const SETTINGS_OVERLAY_LOADING = 'Loading settings…';
export const SETTINGS_CLOSE_LABEL = 'Close';

export const SETTINGS_GENERAL_EXCHANGE_TITLE = 'Exchange Filter';
export const SETTINGS_GENERAL_EXCHANGE_HINT =
  'Only rows from checked exchanges appear in Gappers, Gainers, After Hours, and Catalysts. Selection saves automatically.';
export const SETTINGS_GENERAL_API_TITLE = 'Scanner & API';

export const SETTINGS_ACCOUNT_TITLE = 'Account';
export const SETTINGS_ACCOUNT_OPEN_TRADING = 'Open Trading tab';
export const SETTINGS_ACCOUNT_DISCONNECTED = 'IB Gateway disconnected';
