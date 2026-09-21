/**
 * Read/write Trade > Stocks defaults in localStorage.
 */
import {
  TRADE_DEFAULT_LEG_PCT_MAX,
  TRADE_DEFAULT_LEG_PCT_MIN,
  TRADE_DEFAULT_LIMIT_SOURCE,
  TRADE_DEFAULT_ORDER_TYPE,
  TRADE_DEFAULT_PROTECTIVE_LEGS,
  TRADE_DEFAULT_QUANTITY,
  TRADE_DEFAULT_STOP_LOSS_PCT,
  TRADE_DEFAULT_STOP_OFFSET_PCT,
  TRADE_DEFAULT_TAKE_PROFIT_PCT,
  TRADE_DEFAULT_TIF,
  TRADE_DEFAULT_TIFS,
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
  /** #91: attach default protective legs to opening Limit entries. */
  protectiveLegs: boolean;
  takeProfitPct: number;
  stopLossPct: number;
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
    protectiveLegs: TRADE_DEFAULT_PROTECTIVE_LEGS,
    takeProfitPct: TRADE_DEFAULT_TAKE_PROFIT_PCT,
    stopLossPct: TRADE_DEFAULT_STOP_LOSS_PCT,
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

function isTif(v: unknown): v is TradeDefaultTif {
  return TRADE_DEFAULT_TIFS.includes(v as TradeDefaultTif);
}

/** A leg offset only counts as one when it is a real percentage of the entry. */
function legPct(value: unknown, fallback: number): number {
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= TRADE_DEFAULT_LEG_PCT_MIN &&
    value <= TRADE_DEFAULT_LEG_PCT_MAX
    ? value
    : fallback;
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
    tif: isTif(o.tif) ? o.tif : fallback.tif,
    limitPriceSource: isLimitSource(o.limitPriceSource)
      ? o.limitPriceSource
      : fallback.limitPriceSource,
    stopOffsetPct,
    // Missing or unreadable legs settings stay OFF -- never invent a bracket.
    protectiveLegs: o.protectiveLegs === true,
    takeProfitPct: legPct(o.takeProfitPct, fallback.takeProfitPct),
    stopLossPct: legPct(o.stopLossPct, fallback.stopLossPct),
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
