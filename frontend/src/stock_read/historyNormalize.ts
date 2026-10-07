/** Wire -> types for the stock read's History sheet (`GET /api/stock-read/{symbol}/history`, ADR 036): the
 * daily bars, the +40% runs, the last split and what Nova holds of the symbol. A field the wire lacks or
 * mistypes is dropped or null -- never guessed. */
import { list, normalizeRow, num, obj, str } from './normalize';
import type { DailyBar, RunDay, SplitFact, StockHistory } from './types';

function dailyBar(raw: unknown): DailyBar | null {
  const b = obj(raw);
  const o = num(b?.o);
  const h = num(b?.h);
  const l = num(b?.l);
  const c = num(b?.c);
  if (!b || typeof b.d !== 'string' || o === null || h === null || l === null || c === null) return null;
  return { d: b.d, o, h, l, c, v: num(b.v) ?? 0 };
}

function runDay(raw: unknown): RunDay | null {
  const x = obj(raw);
  const prior = num(x?.prior_close);
  const high = num(x?.high);
  const close = num(x?.close);
  const run = num(x?.run_pct);
  if (!x || typeof x.date !== 'string' || prior === null || high === null || close === null || run === null) {
    return null;
  }
  return {
    date: x.date,
    prior_close: prior,
    high,
    close,
    run_pct: run,
    close_pct: num(x.close_pct) ?? close / prior - 1,
    today: x.today === true,
  };
}

function split(raw: unknown): SplitFact | null {
  const s = obj(raw);
  if (!s) return null;
  return {
    factor: str(s.factor),
    ts: num(s.ts),
    reverse: typeof s.reverse === 'boolean' ? s.reverse : null,
    days_ago: num(s.days_ago),
  };
}

export function normalizeHistory(raw: unknown): StockHistory | null {
  const r = obj(raw);
  if (!r || typeof r.symbol !== 'string') return null;
  return {
    symbol: r.symbol,
    daily: list(r.daily, dailyBar),
    runs: list(r.runs, runDay),
    split: split(r.split),
    holdings: list(r.holdings, normalizeRow),
  };
}
