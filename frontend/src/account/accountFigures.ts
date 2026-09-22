/**
 * Pure figures behind the Account page: the left-column rows that add up to
 * Day's P&L, the per-symbol and per-source splits, and the component rings.
 * No React, no fetch. Every figure names its source; nothing is inferred.
 */
import {
  ACCOUNT_ROWS_TOLERANCE_USD,
  ACCOUNT_SOURCE_AUTO_PAPER,
  ACCOUNT_SOURCE_BOT,
  ACCOUNT_SOURCE_MANUAL,
} from '../constantGroups/account_page';
import { JOURNAL_CALENDAR_TIMEZONE } from '../constantGroups/market_ui';
import type { HeaderAccountFigures } from '../components/headerAccountFigures';
import type {
  HistoryBySource,
  HistoryComponents,
  HistoryDaily,
  HistoryFill,
  PracticeHistory,
} from './accountHistoryTypes';

const PRACTICE_DAY_ROLLOVER_HOURS = 4;

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

/** ET calendar date, YYYY-MM-DD. */
export function easternDate(at: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: JOURNAL_CALENDAR_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(at);
}

/** The practice day `now` belongs to (rolls at 04:00 ET), keyed like `daily[].date`. */
export function todayPracticeDate(now: Date = new Date()): string {
  return easternDate(new Date(now.getTime() - PRACTICE_DAY_ROLLOVER_HOURS * 3_600_000));
}

/** This ledger's row for the practice day, never an archived one. */
export function todayDailyRow(history: PracticeHistory | null, today: string): HistoryDaily | null {
  return history?.daily.find((d) => d.date === today && !d.archived) ?? null;
}

export type RowsReconcile = 'ok' | 'residual' | 'unknown';

export interface AccountDetailRows {
  openPnl: number | null;
  dayPnl: number | null;
  realizedToday: number | null;
  buyingPower: number | null;
  excessLiquidity: number | null;
  commissionsToday: number | null;
  feesToday: number | null;
  /** Whether realized + open - commissions - fees lands on Day's P&L. */
  reconcile: RowsReconcile;
  residual: number | null;
}

/**
 * The rows under the two cards. On a practice venue realized / commissions /
 * fees are today's ledger-history row (a day with no fill has no row, so a
 * loaded history with no row is an honest zero). On Live the IBKR summary's
 * RealizedPnL is the day's; IBKR exposes no fee split, so those stay null.
 */
export function accountDetailRows(
  figures: HeaderAccountFigures,
  today: HistoryDaily | null,
  historyLoaded: boolean,
): AccountDetailRows {
  const practice = figures.source === 'practice';
  const fromHistory = (n: number | undefined): number | null =>
    today ? finite(n) : historyLoaded ? 0 : null;
  const realizedToday = practice ? fromHistory(today?.realized) : figures.realizedPnl;
  const commissionsToday = practice ? fromHistory(today?.commissions) : null;
  const feesToday = practice ? fromHistory(today?.fees) : null;
  const openPnl = figures.openPnl;
  const dayPnl = figures.dayPnl;
  let reconcile: RowsReconcile = 'unknown';
  let residual: number | null = null;
  if (
    realizedToday != null && openPnl != null && dayPnl != null
    && commissionsToday != null && feesToday != null
  ) {
    residual = realizedToday + openPnl - commissionsToday - feesToday - dayPnl;
    reconcile = Math.abs(residual) < ACCOUNT_ROWS_TOLERANCE_USD ? 'ok' : 'residual';
  }
  return {
    openPnl,
    dayPnl,
    realizedToday,
    buyingPower: figures.buyingPower,
    excessLiquidity: figures.excessLiquidity,
    commissionsToday,
    feesToday,
    reconcile,
    residual,
  };
}

/* ------------------------------------------------------------ per symbol */
export interface SymbolPnlRow {
  symbol: string;
  realized: number;
  open: number | null;
  costs: number;
  net: number;
}

export function symbolPnlRows(
  fills: HistoryFill[],
  positions: ReadonlyArray<{ symbol: string; unrealized: number | null }>,
): { rows: SymbolPnlRow[]; total: SymbolPnlRow } {
  const bySymbol = new Map<string, SymbolPnlRow>();
  const rowFor = (symbol: string): SymbolPnlRow => {
    let row = bySymbol.get(symbol);
    if (!row) {
      row = { symbol, realized: 0, open: null, costs: 0, net: 0 };
      bySymbol.set(symbol, row);
    }
    return row;
  };
  for (const fill of fills) {
    const row = rowFor(fill.symbol.toUpperCase());
    row.realized += fill.realized;
    row.costs += fill.commission + fill.fees;
  }
  for (const position of positions) {
    const open = finite(position.unrealized);
    if (open == null) continue;
    const row = rowFor(position.symbol.toUpperCase());
    row.open = (row.open ?? 0) + open;
  }
  const rows = [...bySymbol.values()]
    .map((row) => ({ ...row, net: row.realized + (row.open ?? 0) - row.costs }))
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
  const total = rows.reduce<SymbolPnlRow>(
    (acc, row) => ({
      symbol: acc.symbol,
      realized: acc.realized + row.realized,
      open: row.open == null ? acc.open : (acc.open ?? 0) + row.open,
      costs: acc.costs + row.costs,
      net: acc.net + row.net,
    }),
    { symbol: 'total', realized: 0, open: null, costs: 0, net: 0 },
  );
  return { rows, total };
}

/* ------------------------------------------------------------- by source */
export type SourceKind = 'manual' | 'bot' | 'auto_paper' | 'other';

export interface SourceCard {
  kind: SourceKind;
  source: string | null;
  botId: string | null;
  label: string;
  fills: number;
  realized: number;
  commissions: number;
  fees: number;
  /** realized less commissions and fees; null when the source placed nothing. */
  net: number | null;
  /** Share of the summed |net| across sources with fills; 0 with none. */
  share: number;
}

export function sourceKind(source: string | null): SourceKind {
  if (source === 'manual') return 'manual';
  if (source === 'bot') return 'bot';
  if (source === 'auto_paper') return 'auto_paper';
  return 'other';
}

export function sourceLabel(source: string | null, botId: string | null): string {
  const kind = sourceKind(source);
  if (kind === 'manual') return ACCOUNT_SOURCE_MANUAL;
  if (kind === 'bot') return botId ? `${ACCOUNT_SOURCE_BOT} · ${botId}` : ACCOUNT_SOURCE_BOT;
  if (kind === 'auto_paper') return ACCOUNT_SOURCE_AUTO_PAPER;
  return source ?? '—';
}

/** Manual, Bot and Auto Paper are always shown -- a source that placed nothing is stated. */
export function sourceCards(bySource: HistoryBySource[]): SourceCard[] {
  const cards: SourceCard[] = bySource.map((entry) => ({
    kind: sourceKind(entry.source),
    source: entry.source,
    botId: entry.bot_id,
    label: sourceLabel(entry.source, entry.bot_id),
    fills: entry.fills,
    realized: entry.realized,
    commissions: entry.commissions,
    fees: entry.fees,
    net: entry.fills ? entry.realized - entry.commissions - entry.fees : null,
    share: 0,
  }));
  const canonical: Array<[SourceKind, string]> = [
    ['manual', 'manual'],
    ['bot', 'bot'],
    ['auto_paper', 'auto_paper'],
  ];
  for (const [kind, source] of canonical) {
    if (!cards.some((c) => c.kind === kind)) {
      cards.push({
        kind, source, botId: null, label: sourceLabel(source, null),
        fills: 0, realized: 0, commissions: 0, fees: 0, net: null, share: 0,
      });
    }
  }
  const total = cards.reduce((sum, c) => sum + Math.abs(c.net ?? 0), 0);
  const order: Record<SourceKind, number> = { manual: 0, bot: 1, auto_paper: 2, other: 3 };
  return cards
    .map((c) => ({ ...c, share: total > 0 && c.net != null ? Math.abs(c.net) / total : 0 }))
    .sort((a, b) => order[a.kind] - order[b.kind]);
}

/* ------------------------------------------------------------ components */
export type ComponentId = 'realized' | 'unrealized' | 'commissions' | 'fees' | 'bot';

export interface ComponentRing {
  id: ComponentId;
  value: number;
  /** Share of |realized| + |unrealized| + commissions + fees; bot = share of gross realized. */
  share: number;
  tone: 'up' | 'down' | 'flat' | 'bot';
}

export function componentRings(components: HistoryComponents, fills: HistoryFill[]): ComponentRing[] {
  const total = Math.abs(components.realized) + Math.abs(components.unrealized)
    + Math.abs(components.commissions) + Math.abs(components.sec_finra_fees);
  const grossRealized = fills.reduce((sum, f) => sum + Math.abs(f.realized), 0);
  const share = (n: number): number => (total > 0 ? Math.abs(n) / total : 0);
  const tone = (n: number): 'up' | 'down' | 'flat' => (n > 0 ? 'up' : n < 0 ? 'down' : 'flat');
  return [
    { id: 'realized', value: components.realized, share: share(components.realized), tone: tone(components.realized) },
    { id: 'unrealized', value: components.unrealized, share: share(components.unrealized), tone: tone(components.unrealized) },
    { id: 'commissions', value: -components.commissions, share: share(components.commissions), tone: components.commissions ? 'down' : 'flat' },
    { id: 'fees', value: -components.sec_finra_fees, share: share(components.sec_finra_fees), tone: components.sec_finra_fees ? 'down' : 'flat' },
    {
      id: 'bot',
      value: components.bot_realized,
      share: grossRealized > 0 ? Math.abs(components.bot_realized) / grossRealized : 0,
      tone: 'bot',
    },
  ];
}

export const isBotFill = (fill: HistoryFill): boolean => fill.source === 'bot' || fill.bot_id != null;

export function botIds(fills: HistoryFill[]): string[] {
  return [...new Set(fills.filter(isBotFill).map((f) => f.bot_id).filter((id): id is string => !!id))];
}

export const sellCount = (fills: HistoryFill[]): number => fills.filter((f) => f.side === 'SELL').length;

/** Net P&L of the range on this ledger: realized + open, less commissions and fees. */
export function rangeNetPnl(components: HistoryComponents): number {
  return components.realized + components.unrealized - components.commissions - components.sec_finra_fees;
}
