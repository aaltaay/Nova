/**
 * The words and order of Tickers today (ADR 044), pure: which ticker comes first, which of a row's reasons
 * every ticker shares (said once, in grey) and which are its own, the stock's Entry / Exit from its mode, and
 * a trigger's result in words. Both sides (ADR 049, #778 step 5): the squares of every trade end with "not
 * against you"; the shorts-only block follows.
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
  'you/you': 'You trade it', 'nova/you': 'Auto-entry', 'you/nova': 'Bot exits', 'nova/nova': 'Bot',
};

/** Each square's question, on its column head. */
export const GATE_TIPS: Record<string, string> = {
  bot_on: "Was the Bot switch on for this venue?",
  strategy_on: "Was the setup's strategy at On (not Off or Eyes)?",
  grade: "Was the grade one the strategy lets the bot trade (A, or A and B)? C is never a trade.",
  setups_a_day: "Was it a setup the strategy trades on one stock in a day (the 1st, or the 1st and 2nd)?",
  bot_window: "Was it inside the strategy's bot window?",
  nova_buys: "Was the ticker's Entry set to Bot (and today's 04:00 reset of yesterday's bot entries done)?",
  level2_line: "Did Nova hold the ticker's Level 2 line, so it could read the tape? Red is BLIND.",
  tape_go: "Did the tape read GO at the trigger?",
  trades_today: "Was there room under the day's cap of Nova's trades, longs and shorts together, with no trade open?",
  not_against: 'Did you hold none of the stock the other way? The bot never enters against your position: no short '
    + 'while you hold it long, no buy while you hold it short.',
  short_borrow: 'Shorts only: did IBKR list shares to borrow, enough for the order and the short already held?',
  short_ssr: 'Shorts only: was SSR on? Never red: under SSR a short sells only above the bid, so the bot sells at the '
    + 'ask (amber).',
  short_halt: 'Shorts only: no halt, and not within 10 minutes of an up-halt\'s resumption?',
  short_margin: 'Shorts only: did the margin leave a 25% cushion before IBKR would liquidate?',
  short_hours: 'Shorts only: was it before 15:50 ET (12:50 on an early close), the last new short?',
};

/** Buy and Sell for a stock; You and You when the venue has no switch set for it. */
export function sidesOf(symbol: string, modes: readonly StockModeRow[]): [Side, Side] {
  const row = modes.find(m => m.symbol === symbol);
  return row ? SIDES[row.mode] : ['you', 'you'];
}

/** A row with a "now" (or a ★ / ☆): today's tickers -- listed, or set to bot buy. */
const isToday = (t: TickerRow) => t.listed !== null || t.now !== null;

/** Today's tickers first -- the stocks the bot buys first, then by when they joined the hot list (bot-buy stocks
 * off the list before the listed ones) -- then the rest (triggered only) by symbol. */
export function orderTickers(rows: readonly TickerRow[], modes: readonly StockModeRow[]): { today: TickerRow[]; others: TickerRow[] } {
  const botBuys = (t: TickerRow) => (sidesOf(t.symbol, modes)[0] === 'nova' ? 0 : 1);
  const joined = (t: TickerRow) => t.listed?.at ?? 0;
  const today = rows.filter(isToday).sort((a, b) => botBuys(a) - botBuys(b) || joined(a) - joined(b));
  const others = rows.filter(t => !isToday(t)).sort((a, b) => a.symbol.localeCompare(b.symbol));
  return { today, others };
}

/** A red square in a few words: what "What stops it" says; the backend's whole sentence is its hover. */
export interface Stop { id: string; word: string; why: string }

/** The words for a red square; `t` adds the trigger's own grade or tape where the gate is about them. */
export function stopWord(id: string, t?: { grade?: string | null; tape?: string | null } | null): string {
  switch (id) {
    case 'bot_on': return 'Bot off';
    case 'strategy_on': return 'strategy not On';
    case 'grade': return t?.grade ? `grade ${t.grade}` : 'grade';
    case 'setups_a_day': return 'setups a day';
    case 'bot_window': return 'outside its bot window';
    case 'nova_buys': return 'Entry is You';
    case 'level2_line': return 'BLIND: no Level 2 line';
    case 'tape_go': return t?.tape ? `tape ${t.tape.toUpperCase()}` : 'tape not GO';
    case 'trades_today': return "the day's trades used";
    case 'not_against': return 'you held it the other way';
    case 'short_borrow': return 'no borrow';
    case 'short_ssr': return 'SSR';
    case 'short_halt': return 'halt';
    case 'short_margin': return 'margin';
    case 'short_hours': return 'after the last short';
    default: return id.replace(/_/g, ' ');
  }
}

/** Every red of a row, in the gates' order: a past trigger's, where nothing is shared. */
export function allStops(cells: Cells, order: readonly string[], t?: { grade?: string | null; tape?: string | null } | null): Stop[] {
  return order.filter(id => cells[id]?.ok === false).map(id => ({ id, word: stopWord(id, t), why: cells[id].why }));
}

/** A row's reds in the gates' order, split into its own and the ones every ticker shares now. */
export function splitReasons(cells: Cells, order: readonly string[], t?: { grade?: string | null; tape?: string | null } | null):
{ own: Stop[]; shared: Stop[] } {
  const own: Stop[] = [];
  const shared: Stop[] = [];
  for (const id of order) {
    const c = cells[id];
    if (!c || c.ok !== false) continue;
    (SHARED_GATES.has(id) ? shared : own).push({ id, word: stopWord(id, t), why: c.why });
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
