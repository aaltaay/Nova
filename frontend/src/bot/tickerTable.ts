/**
 * The words and order of Tickers today (ADR 043), pure: which ticker comes first, which of a row's reasons
 * every ticker shares (said once, in grey) and which are its own, the stock's Buy / Sell from its mode, and
 * a trigger's result in words.
 */
import type { StockModeName, StockModeRow } from './stockModesApi';
import type { Cells, TickerRow, TickerTrigger } from './triggersApi';

export type Side = 'you' | 'nova';

/** The gates whose red is the same for every ticker now: said once by the answer line, greyed per row. */
export const SHARED_GATES = new Set(['bot_on', 'bot_window', 'trades_today']);

const SIDES: Record<StockModeName, [Side, Side]> = {
  signal: ['you', 'you'], approve: ['you', 'nova'], auto_entry: ['nova', 'you'], bot: ['nova', 'nova'],
};
export const WHO_WORDS: Record<string, string> = {
  'you/you': 'You trade it', 'nova/you': 'Auto-entry', 'you/nova': 'Nova exits', 'nova/nova': 'Bot',
};

/** Each square's question, on its column head. */
export const GATE_TIPS: Record<string, string> = {
  bot_on: "Was the Bot switch on for this venue?",
  strategy_on: "Was the setup's strategy at On (not Off or Eyes)?",
  grade: "Was the grade one the strategy lets Nova buy (A, or A and B)? C is never a trade.",
  setups_a_day: "Was it a setup the strategy buys on one stock in a day (the 1st, or the 1st and 2nd)?",
  bot_window: "Was it inside the strategy's bot window?",
  hot_list: "Was the ticker on today's hot list?",
  nova_buys: "Was the ticker's Buy set to Nova?",
  level2_line: "Did Nova hold the ticker's Level 2 line, so it could read the tape? Red is BLIND.",
  tape_go: "Did the tape read GO at the trigger?",
  trades_today: "Was there room under the day's cap of Nova's entries, with no trade open?",
};

/** Buy and Sell for a stock; You and You when the venue has no switch set for it. */
export function sidesOf(symbol: string, modes: readonly StockModeRow[]): [Side, Side] {
  const row = modes.find(m => m.symbol === symbol);
  return row ? SIDES[row.mode] : ['you', 'you'];
}

/** Listed first (the stocks Nova buys first, then by when they joined); then the rest by symbol. */
export function orderTickers(rows: readonly TickerRow[], modes: readonly StockModeRow[]): { listed: TickerRow[]; unlisted: TickerRow[] } {
  const novaBuys = (t: TickerRow) => (sidesOf(t.symbol, modes)[0] === 'nova' ? 0 : 1);
  const listed = rows.filter(t => t.listed).sort((a, b) => novaBuys(a) - novaBuys(b) || (a.listed!.at - b.listed!.at));
  const unlisted = rows.filter(t => !t.listed).sort((a, b) => a.symbol.localeCompare(b.symbol));
  return { listed, unlisted };
}

/** A row's reds, split into its own and the ones every ticker shares, in the gates' order. */
export function splitReasons(cells: Cells, order: readonly string[]): { own: string[]; shared: string[] } {
  const own: string[] = [];
  const shared: string[] = [];
  for (const id of order) {
    const c = cells[id];
    if (!c || c.ok !== false) continue;
    (SHARED_GATES.has(id) ? shared : own).push(c.why || id.replace(/_/g, ' '));
  }
  return { own, shared };
}

export function resultWords(t: TickerTrigger): { text: string; tone: 'win' | 'loss' | 'open' } {
  const r = t.r === null ? '' : ` ${t.r >= 0 ? '+' : ''}${t.r.toFixed(2)}R`;
  if (t.outcome === 'target_first') return { text: `target${r}`, tone: 'win' };
  if (t.outcome === 'stop_first') return { text: `stop${r}`, tone: 'loss' };
  return { text: t.outcome ? `${t.outcome.replace(/_/g, ' ')}${r}` : 'not scored yet', tone: 'open' };
}

/** A ticker's day in one line: how many triggers, how many hit target, the net R. */
export function daySummary(t: TickerRow): string {
  const n = t.triggers.length;
  const hit = t.triggers.filter(x => x.outcome === 'target_first').length;
  const net = t.triggers.reduce((s, x) => s + (x.r ?? 0), 0);
  return n ? `${n} today · ${hit} hit · ${net >= 0 ? '+' : ''}${net.toFixed(1)}R` : '–';
}
