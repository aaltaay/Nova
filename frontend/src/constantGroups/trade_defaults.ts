/**
 * Trade > Stocks default order values (Settings).
 * ManualOrderTicket reads these via tradeDefaultsPrefs localStorage.
 */

export const TRADE_DEFAULTS_STORAGE_KEY = 'nova.trade.defaults.v1';

export type TradeDefaultOrderType = 'MKT' | 'LMT' | 'STP';
export type TradeDefaultTradingHours = 'rth' | 'extended';
/** Keep in sync with backend constants_ibkr.IBKR_ORDER_TIFS (#91). */
export type TradeDefaultTif = 'DAY' | 'GTC';
export const TRADE_DEFAULT_TIFS: readonly TradeDefaultTif[] = ['DAY', 'GTC'];
export type TradeDefaultLimitSource = 'ask_bid' | 'last' | 'mid';

export const TRADE_DEFAULT_ORDER_TYPE: TradeDefaultOrderType = 'MKT';
export const TRADE_DEFAULT_QUANTITY = 100;
/** Ticket Extended Hours checkbox default -- on. Saved prefs still win. */
export const TRADE_DEFAULT_EXTENDED_HOURS = true;
export const TRADE_DEFAULT_TRADING_HOURS: TradeDefaultTradingHours =
  TRADE_DEFAULT_EXTENDED_HOURS ? 'extended' : 'rth';
export const TRADE_DEFAULT_TIF: TradeDefaultTif = 'DAY';
export const TRADE_DEFAULT_LIMIT_SOURCE: TradeDefaultLimitSource = 'ask_bid';
export const TRADE_DEFAULT_STOP_OFFSET_PCT = 1;

export const TRADE_DEFAULTS_SECTION_TITLE = 'Default Order Values';
export const TRADE_DEFAULTS_ORDER_TYPE_LABEL = 'Order Type';
export const TRADE_DEFAULTS_QUANTITY_LABEL = 'Quantity';
export const TRADE_DEFAULTS_HOURS_LABEL = 'Extended Hours';
export const TRADE_DEFAULTS_TIF_LABEL = 'Time-in-Force';
export const TRADE_DEFAULTS_LIMIT_SOURCE_LABEL = 'Limit Price';
export const TRADE_DEFAULTS_STOP_OFFSET_LABEL = 'Stop Offset (%)';
export const TRADE_DEFAULTS_EH_HINT =
  'Default on. Uncheck for Regular Hours only. IBKR may reject some Market or Stop + EH combinations -- Nova shows that error after Place.';
export const TRADE_DEFAULTS_TIF_HINT =
  'DAY expires at the close. GTC keeps working until it fills or you cancel it. Applies to the entry and to any protective legs.';

/**
 * Default protective legs (#91). OFF by default: nothing changes until the
 * operator turns them on. When on, an opening Limit entry goes out as one
 * bracket through the same execution service -- never a second place path.
 */
export const TRADE_DEFAULT_PROTECTIVE_LEGS = false;
export const TRADE_DEFAULT_TAKE_PROFIT_PCT = 2;
export const TRADE_DEFAULT_STOP_LOSS_PCT = 1;
/** Offsets are percentages of the entry price and must stay inside this band. */
export const TRADE_DEFAULT_LEG_PCT_MIN = 0.01;
export const TRADE_DEFAULT_LEG_PCT_MAX = 99;

export const TRADE_DEFAULTS_LEGS_LABEL = 'Attach default TP / SL';
export const TRADE_DEFAULTS_TAKE_PROFIT_LABEL = 'Take Profit (%)';
export const TRADE_DEFAULTS_STOP_LOSS_LABEL = 'Stop Loss (%)';
export const TRADE_DEFAULTS_LEGS_HINT =
  'Off by default. When on, an opening Limit entry goes out as a bracket: take profit above and stop loss below (mirrored for a short). Market, Stop and Trail entries are refused while this is on rather than sent without a stop; exits never get legs; Sim has no brackets.';
export const TRADE_DEFAULTS_LEGS_OFFSET_HINT =
  'Percent of the entry price. Rounded to the nearest cent (four decimals under $1).';

/** Ticket notes -- why legs are (or are not) attaching to this order. */
export const TICKET_LEGS_EXIT_NOTE =
  'Exit order — default TP / SL attach to opening entries only.';
export const TICKET_LEGS_SIM_NOTE =
  'Sim has no brackets — default TP / SL are not attached in Sim.';
export const TICKET_LEGS_LIMIT_ONLY_ERROR =
  'Default TP / SL is on: protective legs need a Limit entry. Switch the ticket to Limit, or turn the defaults off in Settings > Trade.';
export const TICKET_LEGS_NO_PRICE_ERROR =
  'Default TP / SL is on: enter the limit price so Nova can work out the take profit and stop loss.';
export const TICKET_LEGS_OFFSET_ERROR =
  'Default TP / SL offsets are too small for this price — raise them in Settings > Trade.';

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
