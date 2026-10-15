/**
 * What the desk says when an order fills (operator ask, 2026-10-14: "when we execute a trade, I want the speaker to
 * say, 'Purchased 100 shares' ... When we sell, I want it to say that as well").
 *
 * Read from the order rows the desk already polls -- the same rows the orders dock shows -- so the voice says only
 * what filled, never what was sent. An order whose `filled_qty` grew since the last read says the shares filled
 * since. The first full read of a venue seeds silently (fills from before are old news), and a fill that shrinks (a
 * Sim rewind) re-bases without a word. Schema: architecture/schema/desk-ops.md, "The desk's voice and the header mute".
 */
import type { IbkrOrder } from './types';

/** What the voice needs from the account snapshot (ibkrAccountPoller). */
export interface FillVoiceSnap {
  venue: string | null;
  /** Both order lists answered at least once on this venue. */
  ordersRead: boolean;
  orders: readonly IbkrOrder[];
  closedOrders: readonly IbkrOrder[];
}

export interface FillVoiceState {
  venue: string | null;
  seeded: boolean;
  /** Shares filled per order, as last read. */
  filled: Map<string, number>;
}

/** Sentences in one read before the rest are counted instead of said. */
const MAX_SENTENCES = 3;
const EPS = 1e-9;

/** Sells that flatten what is held. `all_stop` / `bot_trip` are rows from before ADR 056: a flatten, never the bot's. */
const FLATTEN_ORIGINS = new Set(['ticket_flatten', 'emergency_kill', 'all_stop', 'bot_trip']);
/** The daily loss limit's Auto sell (ADR 056): it sells every position opened today, yours and the bots'. */
const LOSS_LIMIT_ORIGIN = 'loss_limit';
const BOT_ORIGINS = new Set(['bot', 'auto_entry', 'approve', 'bot_api', 'nova_exit']);
const TARGET_ROLES = new Set(['target', 'target2']);

export function newFillVoiceState(): FillVoiceState {
  return { venue: null, seeded: false, filled: new Map() };
}

/** "SOFI" -> "S O F I": a ticker said letter by letter, never as a word. */
export function spellTicker(symbol: string): string {
  return symbol
    .toUpperCase()
    .replace(/[^A-Z0-9.]/g, '')
    .split('')
    .map(c => (c === '.' ? 'dot' : c))
    .join(' ');
}

function sharesWords(n: number): string {
  const rounded = Math.round(n * 10_000) / 10_000;
  return `${rounded.toLocaleString('en-US')} ${rounded === 1 ? 'share' : 'shares'}`;
}

function orderKey(row: IbkrOrder): string {
  // order_id is this session's id for Nova's own orders; an order recovered from IBKR may carry only its permId.
  if (Number(row.order_id) > 0) return `id:${row.order_id}`;
  if (Number(row.perm_id) > 0) return `perm:${row.perm_id}`;
  return `row:${row.symbol}|${row.side}|${row.submitted_at ?? ''}`;
}

function filledOf(row: IbkrOrder): number {
  const n = Number(row.filled_qty);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

interface Said {
  lead: string;
  verb: string;
  symbol: string;
  partial: boolean;
  shares: number;
}

/** The sentence's parts for one order's fill: lead ("Stop hit."), verb ("Bot sold"), and whether more may come. */
function describe(row: IbkrOrder, working: boolean, filled: number): Omit<Said, 'shares'> {
  const side = String(row.side ?? '').toUpperCase();
  const origin = String(row.order_origin ?? '').toLowerCase();
  const legRole = String((row as { leg_role?: string | null }).leg_role ?? '').toLowerCase();
  const orderType = String(row.order_type ?? '').toUpperCase();
  const shortEntry = side === 'SELL' && row.short_entry === true;
  const covers = side === 'BUY' && row.effect === 'closes';
  // A SELL closes unless it opens a short; a BUY closes only when it covers one (a buy stop that opens is no stop-out).
  const closes = side === 'SELL' ? !shortEntry : covers;
  const stop = closes && (legRole === 'stop' || (!legRole && orderType.startsWith('STP')));

  const lossLimit = origin === LOSS_LIMIT_ORIGIN;
  let lead = '';
  if (lossLimit) lead = 'Loss limit.';
  else if (FLATTEN_ORIGINS.has(origin)) lead = 'Flatten.';
  else if (stop) lead = 'Stop hit.';
  else if (TARGET_ROLES.has(legRole)) lead = 'Target hit.';

  // The loss limit only ever closes: its BUY covers a short.
  let verb = side === 'SELL' ? (shortEntry ? 'Shorted' : 'Sold') : (covers || lossLimit ? 'Covered' : 'Bought');
  // A flatten or the loss limit sold the account, whoever opened the position: never "Bot sold".
  const flattens = lossLimit || FLATTEN_ORIGINS.has(origin);
  const bot = !flattens
    && (Boolean(row.bot_id) || BOT_ORIGINS.has(origin) || String(row.order_source ?? '').toLowerCase() === 'bot');
  if (bot) verb = `Bot ${verb.toLowerCase()}`;

  const qty = Number(row.qty);
  const partial = working && Number.isFinite(qty) && filled < qty - EPS;
  return { lead, verb, symbol: String(row.symbol ?? '').toUpperCase(), partial };
}

function sentence(s: Said): string {
  const body = `${s.verb} ${sharesWords(s.shares)} of ${spellTicker(s.symbol)}${s.partial ? ', partial' : ''}.`;
  return s.lead ? `${s.lead} ${body}` : body;
}

/**
 * The sentences this read adds, in the order the rows came. Updates `state`: the venue it is on, and every
 * order's shares as read now.
 */
export function readFills(state: FillVoiceState, snap: FillVoiceSnap): string[] {
  if (snap.venue !== state.venue) {
    state.venue = snap.venue;
    state.seeded = false;
    state.filled.clear();
  }
  if (!snap.ordersRead) return [];

  // An order moving from working to closed may sit in both lists for one read: the larger fill is the truth.
  const now = new Map<string, { row: IbkrOrder; working: boolean; filled: number }>();
  const take = (row: IbkrOrder, working: boolean) => {
    const key = orderKey(row);
    const filled = filledOf(row);
    const had = now.get(key);
    if (!had || filled > had.filled) now.set(key, { row, working, filled });
  };
  snap.closedOrders.forEach(row => take(row, false));
  snap.orders.forEach(row => take(row, true));

  if (!state.seeded) {
    state.seeded = true;
    for (const [key, { filled }] of now) state.filled.set(key, filled);
    return [];
  }

  const said = new Map<string, Said>();
  for (const [key, { row, working, filled }] of now) {
    const before = state.filled.get(key) ?? 0;
    state.filled.set(key, filled);
    if (filled <= before + EPS) continue; // unchanged, or a rewind took shares back
    const parts = describe(row, working, filled);
    const group = `${parts.lead}|${parts.verb}|${parts.symbol}|${parts.partial}`;
    const prior = said.get(group);
    if (prior) prior.shares += filled - before;
    else said.set(group, { ...parts, shares: filled - before });
  }

  const lines = [...said.values()].map(sentence);
  if (lines.length <= MAX_SENTENCES) return lines;
  const rest = lines.length - (MAX_SENTENCES - 1);
  return [...lines.slice(0, MAX_SENTENCES - 1), `And ${rest} more fills.`];
}
