/**
 * One practice day, broken down from the ledger history: what the Calendar's
 * hover card and day panel show. The day's totals are the history's own
 * `daily` rows (net, commissions, fees, fills); the stocks and trades are read
 * from this ledger's `fills`, each on the practice day it landed in (04:00 ET
 * rollover, the backend's `_day_of`). A trade is one stock from flat back to
 * flat and counts on the day it closes. An archived ledger sends only its day
 * totals, so its days list no stocks or trades -- stated, never guessed. Pure.
 */
import { deskTradingDay } from '../utils/deskTradingDay';
import { isBotFill } from './accountFigures';
import type { HistoryDaily, HistoryFill } from './accountHistoryTypes';

/** Shares left on a position below this are float noise, not a holding. */
const FLAT_EPS = 1e-9;

export interface DayTrade {
  symbol: string;
  side: 'long' | 'short';
  /** Shares bought into a long (sold into a short), adds included. */
  shares: number;
  openTs: number;
  closeTs: number;
  /** Net of commissions and fees, as the ledger books every fill. */
  net: number;
  commission: number;
  fees: number;
  fills: number;
  /** Any of its fills came from a bot. */
  bot: boolean;
}

export interface DayStock {
  symbol: string;
  /** Trades in this stock that closed this day. */
  trades: number;
  fills: number;
  bought: number;
  sold: number;
  avgBuy: number | null;
  avgSell: number | null;
  net: number;
  commission: number;
  fees: number;
}

export interface DayBreakdown {
  date: string;
  /** Net P&L: the ledger's realized is already after commissions and fees (QA V1). */
  net: number;
  /** Before commissions and fees: net + commissions + fees. */
  gross: number;
  commissions: number;
  fees: number;
  fills: number;
  /** This ledger's fills that day: the ones the Fills tab can list. */
  listedFills: number;
  /** Every row of the day belongs to an archived ledger. */
  archived: boolean;
  /** This ledger's fills are listed; false when only an archived ledger traded the day. */
  detailed: boolean;
  /** An archived ledger traded part of the day: its share is in the totals only. */
  partial: boolean;
  sharesBought: number;
  sharesSold: number;
  botFills: number;
  trades: DayTrade[];
  won: number;
  lost: number;
  /** Worst net first. */
  stocks: DayStock[];
}

/** The practice day a fill landed in, keyed like `daily[].date`. */
export const fillDay = (ts: number): string => deskTradingDay(ts * 1000);

const cents = (n: number): number => Math.round(n * 100) / 100;

function openTrade(fill: HistoryFill, side: 'long' | 'short'): DayTrade {
  return {
    symbol: fill.symbol, side, shares: 0, openTs: fill.ts, closeTs: fill.ts,
    net: 0, commission: 0, fees: 0, fills: 0, bot: false,
  };
}

/**
 * Every round trip in `fills`, in close order: a stock's position walked fill
 * by fill from flat. A fill that crosses flat closes the trade and opens the
 * other side with what is left.
 */
export function roundTrips(fills: readonly HistoryFill[]): DayTrade[] {
  const held = new Map<string, number>();
  const open = new Map<string, DayTrade>();
  const closed: DayTrade[] = [];
  const ordered = [...fills].sort((a, b) => a.ts - b.ts);
  for (const fill of ordered) {
    const signed = fill.side === 'BUY' ? fill.qty : -fill.qty;
    const before = held.get(fill.symbol) ?? 0;
    const after = before + signed;
    const trade = open.get(fill.symbol) ?? openTrade(fill, signed > 0 ? 'long' : 'short');
    trade.net += fill.realized;
    trade.commission += fill.commission;
    trade.fees += fill.fees;
    trade.fills += 1;
    if (isBotFill(fill)) trade.bot = true;
    if ((signed > 0) === (trade.side === 'long')) trade.shares += fill.qty;
    const flat = Math.abs(after) < FLAT_EPS;
    const crossed = !flat && before !== 0 && Math.sign(after) !== Math.sign(before);
    if (flat || crossed) {
      closed.push({ ...trade, closeTs: fill.ts });
      open.delete(fill.symbol);
    } else {
      open.set(fill.symbol, trade);
    }
    if (crossed) {
      const next = openTrade(fill, after > 0 ? 'long' : 'short');
      next.shares = Math.abs(after);
      open.set(fill.symbol, next);
    }
    held.set(fill.symbol, flat ? 0 : after);
  }
  return closed;
}

function stocksOf(fills: readonly HistoryFill[], trades: readonly DayTrade[]): DayStock[] {
  const rows = new Map<string, DayStock & { buyCost: number; sellValue: number }>();
  for (const fill of fills) {
    const row = rows.get(fill.symbol) ?? {
      symbol: fill.symbol, trades: 0, fills: 0, bought: 0, sold: 0, avgBuy: null, avgSell: null,
      net: 0, commission: 0, fees: 0, buyCost: 0, sellValue: 0,
    };
    if (fill.side === 'BUY') {
      row.bought += fill.qty;
      row.buyCost += fill.qty * fill.price;
    } else {
      row.sold += fill.qty;
      row.sellValue += fill.qty * fill.price;
    }
    row.fills += 1;
    row.net += fill.realized;
    row.commission += fill.commission;
    row.fees += fill.fees;
    rows.set(fill.symbol, row);
  }
  for (const trade of trades) {
    const row = rows.get(trade.symbol);
    if (row) row.trades += 1;
  }
  return [...rows.values()]
    .map(({ buyCost, sellValue, ...row }) => ({
      ...row,
      avgBuy: row.bought > 0 ? buyCost / row.bought : null,
      avgSell: row.sold > 0 ? sellValue / row.sold : null,
    }))
    .sort((a, b) => a.net - b.net || a.symbol.localeCompare(b.symbol));
}

/** Every day the history has a `daily` row for, broken down. */
export function dayBreakdowns(history: { daily: readonly HistoryDaily[]; fills: readonly HistoryFill[] }): Map<string, DayBreakdown> {
  const fillsByDay = new Map<string, HistoryFill[]>();
  for (const fill of history.fills) {
    const day = fillDay(fill.ts);
    const list = fillsByDay.get(day) ?? [];
    list.push(fill);
    fillsByDay.set(day, list);
  }
  const tradesByDay = new Map<string, DayTrade[]>();
  for (const trade of roundTrips(history.fills)) {
    const day = fillDay(trade.closeTs);
    const list = tradesByDay.get(day) ?? [];
    list.push(trade);
    tradesByDay.set(day, list);
  }
  const rowsByDay = new Map<string, HistoryDaily[]>();
  for (const row of history.daily) {
    const list = rowsByDay.get(row.date) ?? [];
    list.push(row);
    rowsByDay.set(row.date, list);
  }
  const out = new Map<string, DayBreakdown>();
  for (const [date, rows] of rowsByDay) {
    const net = rows.reduce((s, r) => s + r.realized, 0);
    const commissions = rows.reduce((s, r) => s + r.commissions, 0);
    const fees = rows.reduce((s, r) => s + r.fees, 0);
    const fills = fillsByDay.get(date) ?? [];
    const trades = tradesByDay.get(date) ?? [];
    const detailed = rows.some((r) => !r.archived);
    out.set(date, {
      date,
      net,
      gross: net + commissions + fees,
      commissions,
      fees,
      fills: rows.reduce((s, r) => s + r.fills, 0),
      listedFills: fills.length,
      archived: !detailed,
      detailed,
      partial: detailed && rows.some((r) => r.archived),
      sharesBought: fills.reduce((s, f) => s + (f.side === 'BUY' ? f.qty : 0), 0),
      sharesSold: fills.reduce((s, f) => s + (f.side === 'SELL' ? f.qty : 0), 0),
      botFills: fills.filter(isBotFill).length,
      trades,
      won: trades.filter((t) => cents(t.net) > 0).length,
      lost: trades.filter((t) => cents(t.net) < 0).length,
      stocks: stocksOf(fills, trades),
    });
  }
  return out;
}

export interface MonthDayTotals {
  net: number;
  gross: number;
  commissions: number;
  fees: number;
  fills: number;
  trades: number;
  won: number;
  lost: number;
  /** Days an archived ledger traded, alone or beside this one: their trades are not all counted. */
  incompleteDays: number;
}

/**
 * The totals of `dates`' breakdowns (a month's cells). Commissions include an
 * archived ledger's, its trades do not, so a cost per trade is only fair when
 * `incompleteDays` is 0.
 */
export function monthDayTotals(days: ReadonlyMap<string, DayBreakdown>, dates: readonly string[]): MonthDayTotals {
  const total: MonthDayTotals = { net: 0, gross: 0, commissions: 0, fees: 0, fills: 0, trades: 0, won: 0, lost: 0, incompleteDays: 0 };
  for (const date of dates) {
    const day = days.get(date);
    if (!day) continue;
    total.net += day.net;
    total.gross += day.gross;
    total.commissions += day.commissions;
    total.fees += day.fees;
    total.fills += day.fills;
    total.trades += day.trades.length;
    total.won += day.won;
    total.lost += day.lost;
    if (!day.detailed || day.partial) total.incompleteDays += 1;
  }
  return total;
}
