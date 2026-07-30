/**
 * Read/write Trade > Stocks defaults in localStorage.
 */
import {
  TRADE_DEFAULT_LIMIT_SOURCE,
  TRADE_DEFAULT_ORDER_TYPE,
  TRADE_DEFAULT_QUANTITY,
  TRADE_DEFAULT_STOP_OFFSET_PCT,
  TRADE_DEFAULT_TIF,
  TRADE_DEFAULT_TRADING_HOURS,
  TRADE_DEFAULTS_STORAGE_KEY,
  type TradeDefaultLimitSource,
  type TradeDefaultOrderType,
  type TradeDefaultTif,
  type TradeDefaultTradingHours,
} from '../constantGroups/trade_defaults';

export interface TradeDefaultsPrefs {
  v: 1;
  orderType: TradeDefaultOrderType;
  quantity: number;
  tradingHours: TradeDefaultTradingHours;
  tif: TradeDefaultTif;
  limitPriceSource: TradeDefaultLimitSource;
  stopOffsetPct: number;
}

export function defaultTradeDefaultsPrefs(): TradeDefaultsPrefs {
  return {
    v: 1,
    orderType: TRADE_DEFAULT_ORDER_TYPE,
    quantity: TRADE_DEFAULT_QUANTITY,
    tradingHours: TRADE_DEFAULT_TRADING_HOURS,
    tif: TRADE_DEFAULT_TIF,
    limitPriceSource: TRADE_DEFAULT_LIMIT_SOURCE,
    stopOffsetPct: TRADE_DEFAULT_STOP_OFFSET_PCT,
  };
}

function isOrderType(v: unknown): v is TradeDefaultOrderType {
  return v === 'MKT' || v === 'LMT' || v === 'STP';
}

function isHours(v: unknown): v is TradeDefaultTradingHours {
  return v === 'rth' || v === 'extended';
}

function isLimitSource(v: unknown): v is TradeDefaultLimitSource {
  return v === 'ask_bid' || v === 'last' || v === 'mid';
}

export function parseTradeDefaultsPrefs(raw: unknown): TradeDefaultsPrefs {
  const fallback = defaultTradeDefaultsPrefs();
  if (!raw || typeof raw !== 'object') return fallback;
  const o = raw as Record<string, unknown>;
  const quantity =
    typeof o.quantity === 'number' && Number.isFinite(o.quantity) && o.quantity > 0
      ? Math.floor(o.quantity)
      : fallback.quantity;
  const stopOffsetPct =
    typeof o.stopOffsetPct === 'number' &&
    Number.isFinite(o.stopOffsetPct) &&
    o.stopOffsetPct >= 0
      ? o.stopOffsetPct
      : fallback.stopOffsetPct;
  return {
    v: 1,
    orderType: isOrderType(o.orderType) ? o.orderType : fallback.orderType,
    quantity,
    tradingHours: isHours(o.tradingHours) ? o.tradingHours : fallback.tradingHours,
    tif: 'DAY',
    limitPriceSource: isLimitSource(o.limitPriceSource)
      ? o.limitPriceSource
      : fallback.limitPriceSource,
    stopOffsetPct,
  };
}

export function readTradeDefaultsPrefs(): TradeDefaultsPrefs {
  try {
    const raw = localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY);
    if (!raw) return defaultTradeDefaultsPrefs();
    return parseTradeDefaultsPrefs(JSON.parse(raw) as unknown);
  } catch {
    return defaultTradeDefaultsPrefs();
  }
}

export function writeTradeDefaultsPrefs(prefs: TradeDefaultsPrefs): void {
  try {
    const next = parseTradeDefaultsPrefs(prefs);
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* private mode / quota */
  }
}
