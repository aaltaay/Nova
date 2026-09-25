/** Wire -> types for who trades the stock (ADR 037). A field the wire lacks or mistypes is null; a
 * payload that is not a stock's view is null -- never guessed into Signal only. */
import { list, num, obj, str } from './normalize';
import type {
  StockModeApproval,
  StockModeName,
  StockModeNote,
  StockModeTrade,
  StockModeView,
  StockSide,
} from './types';

const MODES: ReadonlySet<string> = new Set<StockModeName>(['signal', 'approve', 'auto_entry', 'bot']);
const VENUES: ReadonlySet<string> = new Set(['live', 'paper', 'sim']);
const TRADE_KINDS: ReadonlySet<string> = new Set(['auto_entry', 'approve', 'bot']);
const TRADE_STATES: ReadonlySet<string> = new Set(['entering', 'holding', 'closed', 'missed', 'handed']);
const APPROVAL_STATES: ReadonlySet<string> = new Set(['waiting', 'sent', 'withdrawn']);
const EVENT_TONES: ReadonlySet<string> = new Set(['info', 'ok', 'warn', 'bad']);

function side(v: unknown): StockSide | null {
  return v === 'you' || v === 'nova' ? v : null;
}

function approval(raw: unknown): StockModeApproval | null {
  const a = obj(raw);
  const entry = num(a?.entry);
  const stop = num(a?.stop);
  const target = num(a?.target);
  const qty = num(a?.qty);
  if (!a || typeof a.setup_id !== 'string' || entry === null || stop === null || target === null || qty === null) {
    return null;
  }
  return {
    setup_id: a.setup_id,
    setup_type: str(a.setup_type),
    entry,
    stop,
    target,
    qty,
    approved_at: num(a.approved_at) ?? 0,
    state: (typeof a.state === 'string' && APPROVAL_STATES.has(a.state) ? a.state : 'waiting') as StockModeApproval['state'],
    reason: str(a.reason),
  };
}

function trade(raw: unknown): StockModeTrade | null {
  const t = obj(raw);
  if (!t || typeof t.kind !== 'string' || !TRADE_KINDS.has(t.kind)) return null;
  if (typeof t.state !== 'string' || !TRADE_STATES.has(t.state)) return null;
  return {
    kind: t.kind as StockModeTrade['kind'],
    state: t.state as StockModeTrade['state'],
    venue: str(t.venue),
    venue_day: str(t.venue_day),
    setup_id: str(t.setup_id),
    setup_type: str(t.setup_type),
    qty: num(t.qty),
    entry: num(t.entry),
    stop: num(t.stop),
    target: num(t.target),
    entry_order_id: num(t.entry_order_id),
    target_order_id: num(t.target_order_id),
    stop_order_id: num(t.stop_order_id),
    fill_price: num(t.fill_price),
    filled_at: num(t.filled_at),
    exit_price: num(t.exit_price),
    exit_reason: str(t.exit_reason),
    // A trade whose seller the wire does not name is the operator's: Nova never claims an exit.
    exits: side(t.exits) ?? 'you',
    sent_at: num(t.sent_at),
    closed_at: num(t.closed_at),
    note: str(t.note),
    exiting: t.exiting === true,
  };
}

const UNREADABLE_LOCK = 'The desk could not read whether Nova may take this side.';

/** Null only when the wire says null: a missing or mistyped lock stays locked. */
function lock(locks: Record<string, unknown> | null, key: 'buy' | 'sell'): string | null {
  if (locks && locks[key] === null) return null;
  return str(locks?.[key]) ?? UNREADABLE_LOCK;
}

function note(raw: unknown): StockModeNote | null {
  const n = obj(raw);
  if (!n || typeof n.id !== 'string' || typeof n.text !== 'string') return null;
  return { id: n.id, tone: n.tone === 'warn' ? 'warn' : 'info', text: n.text };
}

export function normalizeStockMode(raw: unknown): StockModeView | null {
  const v = obj(raw);
  if (!v || typeof v.symbol !== 'string' || typeof v.mode !== 'string' || !MODES.has(v.mode)) return null;
  const buy = side(v.buy);
  const sell = side(v.sell);
  if (!buy || !sell) return null;
  const locks = obj(v.locks);
  const event = obj(v.last_event);
  const bot = obj(v.bot);
  return {
    symbol: v.symbol,
    generated_at: num(v.generated_at) ?? 0,
    venue: typeof v.venue === 'string' && VENUES.has(v.venue) ? (v.venue as StockModeView['venue']) : null,
    mode: v.mode as StockModeName,
    buy,
    sell,
    risk_usd: num(v.risk_usd),
    set_at: num(v.set_at),
    // A view without its locks is read as locked: Nova never looks free to trade by omission.
    locks: { buy: lock(locks, 'buy'), sell: lock(locks, 'sell') },
    notes: list(v.notes, note),
    approval: approval(v.approval),
    trade: trade(v.trade),
    nova_entries_today: num(v.nova_entries_today) ?? 0,
    last_event: event && typeof event.text === 'string'
      ? {
        ts: num(event.ts) ?? 0,
        tone: (typeof event.tone === 'string' && EVENT_TONES.has(event.tone) ? event.tone : 'info') as 'info' | 'ok' | 'warn' | 'bad',
        text: event.text,
      }
      : null,
    bot: bot
      ? { on_list: bot.on_list === true, playing: bot.playing === true, reason: str(bot.reason), setup: str(bot.setup) }
      : null,
  };
}
