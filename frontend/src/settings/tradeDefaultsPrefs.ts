/**
 * Owns per-venue Trade > Stocks defaults in localStorage (ADR 042).
 * Venue/version changes invalidate readers. The migration receipt binds the
 * old shared values to one confirmed venue even if a later write or cleanup fails.
 */
import {
  TRADE_DEFAULT_LEG_PCT_MAX,
  TRADE_DEFAULT_LEG_PCT_MIN,
  TRADE_DEFAULT_LIMIT_SOURCE,
  TRADE_DEFAULT_ORDER_TYPE,
  TRADE_DEFAULT_PROTECTIVE_LEGS,
  TRADE_DEFAULT_QUANTITY,
  TRADE_DEFAULT_SHORT_STOP_OFFSET,
  TRADE_DEFAULT_SHORT_STOP_OFFSET_MAX,
  TRADE_DEFAULT_SHORT_STOP_OFFSET_MIN,
  TRADE_DEFAULT_STOP_LOSS_PCT,
  TRADE_DEFAULT_STOP_OFFSET_PCT,
  TRADE_DEFAULT_TAKE_PROFIT_PCT,
  TRADE_DEFAULT_TIF,
  TRADE_DEFAULT_TIFS,
  TRADE_DEFAULT_TRADING_HOURS,
  TRADE_DEFAULTS_STORAGE_KEY,
  TRADE_DEFAULTS_VENUE_STORAGE_PREFIX,
  TRADE_DEFAULTS_SCHEMA_VERSION,
  TRADE_DEFAULTS_MIGRATION_KEY,
  TRADE_DEFAULTS_MIGRATION_VERSION,
  TRADE_DEFAULTS_CHANGED_EVENT,
  type TradeDefaultLimitSource,
  type TradeDefaultOrderType,
  type TradeDefaultTif,
  type TradeDefaultTradingHours,
} from '../constantGroups/trade_defaults';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { isSampleView } from '../sample_data/sampleNav';

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
  /** ADR 048: a short's buy stop starts this many dollars over its limit (the ticket, each Short hotkey). */
  shortStopOffset: number;
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
    shortStopOffset: TRADE_DEFAULT_SHORT_STOP_OFFSET,
  };
}

/** A short's buy stop offset, in dollars inside its band; anything else is the default. */
export function shortStopOffsetOf(value: unknown): number {
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= TRADE_DEFAULT_SHORT_STOP_OFFSET_MIN &&
    value <= TRADE_DEFAULT_SHORT_STOP_OFFSET_MAX
    ? value
    : TRADE_DEFAULT_SHORT_STOP_OFFSET;
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
    shortStopOffset: shortStopOffsetOf(o.shortStopOffset),
  };
}

export function tradeDefaultsStorageKey(venue: DeskVenue): string {
  return `${TRADE_DEFAULTS_VENUE_STORAGE_PREFIX}${venue}`;
}

function jsonRecord(raw: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

function knownPrefs(value: unknown): TradeDefaultsPrefs | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.v !== undefined && record.v !== 1) {
    console.warn('[Nova] refusing unknown stock defaults version', record.v);
    return null;
  }
  return parseTradeDefaultsPrefs(record);
}

function destinationPrefs(raw: string | null, venue: DeskVenue): TradeDefaultsPrefs | null {
  const record = jsonRecord(raw);
  if (!record) return null;
  if (record.schema_version !== TRADE_DEFAULTS_SCHEMA_VERSION || record.venue !== venue) {
    console.warn('[Nova] refusing stock defaults with unknown schema or venue ownership');
    return null;
  }
  return knownPrefs(record.prefs);
}

function persistVerified(key: string, serialized: string): boolean {
  localStorage.setItem(key, serialized);
  return localStorage.getItem(key) === serialized;
}

function serializePrefs(venue: DeskVenue, prefs: TradeDefaultsPrefs): string {
  return JSON.stringify({ schema_version: TRADE_DEFAULTS_SCHEMA_VERSION, venue, prefs });
}

/** The caller supplies a backend-confirmed venue; null never adopts or writes. */
export function readTradeDefaultsPrefs(venue: DeskVenue | null): TradeDefaultsPrefs {
  const fallback = defaultTradeDefaultsPrefs();
  if (!venue || isSampleView()) return fallback;
  try {
    const key = tradeDefaultsStorageKey(venue);
    const saved = localStorage.getItem(key);
    const existing = destinationPrefs(saved, venue);
    const legacyRaw = localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY);
    const legacy = knownPrefs(jsonRecord(legacyRaw));
    // An unreadable/unknown destination is preserved, never repaired by a read.
    if (!legacy || (saved !== null && !existing)) return existing ?? fallback;
    const receiptRaw = localStorage.getItem(TRADE_DEFAULTS_MIGRATION_KEY);
    const receipt = jsonRecord(receiptRaw);
    if (receiptRaw !== null && receipt?.schema_version !== TRADE_DEFAULTS_MIGRATION_VERSION) {
      console.warn('[Nova] refusing unknown stock defaults migration receipt');
      return existing ?? fallback;
    }
    if (receiptRaw !== null && (
      receipt?.venue !== venue
    )) return existing ?? fallback;
    if (receiptRaw === null && !persistVerified(TRADE_DEFAULTS_MIGRATION_KEY, JSON.stringify({
      schema_version: TRADE_DEFAULTS_MIGRATION_VERSION, venue,
    }))) return existing ?? fallback;
    const next = existing ?? legacy;
    if (!existing && !persistVerified(key, serializePrefs(venue, next))) return fallback;
    // Both receipt and destination now exist. A failed removal leaves the
    // legacy copy recoverable, but the receipt forbids another venue adopting it.
    try { localStorage.removeItem(TRADE_DEFAULTS_STORAGE_KEY); } catch { /* retry next read */ }
    return next;
  } catch {
    return destinationPrefs(safeGet(tradeDefaultsStorageKey(venue)), venue) ?? fallback;
  }
}

function safeGet(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

/** Stable primitive for React readers, including migration changes. */
export function tradeDefaultsPrefsSnapshot(venue: DeskVenue | null): string {
  if (!venue || isSampleView()) return '';
  return JSON.stringify([
    safeGet(tradeDefaultsStorageKey(venue)),
    safeGet(TRADE_DEFAULTS_STORAGE_KEY),
    safeGet(TRADE_DEFAULTS_MIGRATION_KEY),
  ]);
}

export function subscribeTradeDefaultsPrefs(listener: () => void): () => void {
  const storage = (event: StorageEvent) => {
    if (event.storageArea && event.storageArea !== localStorage) return;
    if (event.key === null || event.key === TRADE_DEFAULTS_STORAGE_KEY ||
      event.key === TRADE_DEFAULTS_MIGRATION_KEY || event.key.startsWith(TRADE_DEFAULTS_VENUE_STORAGE_PREFIX)) listener();
  };
  window.addEventListener('storage', storage);
  window.addEventListener(TRADE_DEFAULTS_CHANGED_EVENT, listener);
  return () => {
    window.removeEventListener('storage', storage);
    window.removeEventListener(TRADE_DEFAULTS_CHANGED_EVENT, listener);
  };
}

export function writeTradeDefaultsPrefs(venue: DeskVenue | null, prefs: TradeDefaultsPrefs): boolean {
  if (!venue || isSampleView()) return false;
  try {
    const key = tradeDefaultsStorageKey(venue);
    const saved = localStorage.getItem(key);
    // A fallback shown by this older UI never authorizes replacing unknown
    // versions, foreign ownership or corrupt data already in the destination.
    if (saved !== null && !destinationPrefs(saved, venue)) return false;
    if (!persistVerified(key, serializePrefs(venue, parseTradeDefaultsPrefs(prefs)))) return false;
    window.dispatchEvent(new Event(TRADE_DEFAULTS_CHANGED_EVENT));
    return true;
  } catch {
    return false;
  }
}
