/** Who trades the stock (ADR 037): the wire shapes of `GET /api/stock-mode/{symbol}` (AGENTS.md §3, "Who trades the
 * stock"). Its own endpoint beside the read's (`types.ts`, which re-exports these, so either import works). */
export type StockModeName = 'signal' | 'approve' | 'auto_entry' | 'bot';
export type StockSide = 'you' | 'nova';

export interface StockModeApproval {
  setup_id: string;
  setup_type: string | null;
  entry: number;
  stop: number;
  target: number;
  /** Two halves (#845): the plan's target 2 the bracket sells the rest at; null or absent: every share at target 1. */
  target2?: number | null;
  /** The share sold at target 1 (0.5 with a target 2); null or absent when the approval does not say. */
  target1_fraction?: number | null;
  qty: number;
  approved_at: number;
  state: 'waiting' | 'sent' | 'withdrawn';
  reason: string | null;
}

/** One sale of a trade that sells in two halves (#681, #845): which leg sold, how many, where. */
export interface StockModeHalf {
  leg: string;
  qty: number;
  price: number | null;
}

export interface StockModeTrade {
  /** `exit`: Nova holds the exit of a stock you bought (ADR 037 amendment 2026-10-01) -- or the cover of one you
   * shorted (`side: 'short'`, ADR 048). */
  kind: 'auto_entry' | 'approve' | 'bot' | 'exit';
  /** Long or short (ADR 048); a trade made before shorts, or a wire without it, is a long. */
  side?: 'long' | 'short';
  state: 'entering' | 'holding' | 'closed' | 'missed' | 'handed';
  venue: string | null;
  venue_day: string | null;
  setup_id: string | null;
  setup_type: string | null;
  qty: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  entry_order_id: number | null;
  target_order_id: number | null;
  stop_order_id: number | null;
  fill_price: number | null;
  filled_at: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  /** Who sells it: Nova holds the exits (Approve's bracket, the bot), or the operator does. */
  exits: StockSide;
  sent_at: number | null;
  closed_at: number | null;
  note: string | null;
  /** The bot is selling it now. */
  exiting: boolean;
  /** Nova's exit: the stop is raised as 1-minute candles close over round numbers. */
  trail: boolean;
  /** Nova's exit: each raise of its stop. */
  raised: { at: number; from: number; to: number; round: number }[];
  /** Two halves (#681, #845): target 2 and its order (null: every share at target 1), the shares each half sells
   * and where each part sold. Absent from a fixture or an older backend. */
  target2?: number | null;
  target2_order_id?: number | null;
  target1_qty?: number | null;
  target2_qty?: number | null;
  halves?: StockModeHalf[];
}

/** Something that keeps Nova from acting on the stock (`warn` / `bad`), or a fact beside it (`info`). The
 * view lists every one, not the first (ADR 042 draft). */
export interface StockModeNote {
  id: string;
  tone: 'info' | 'warn' | 'bad';
  text: string;
}

/** What Nova would send for the stock's plan in a Nova mode: the sleeve's risk over the risk a share,
 * capped by the sleeve's max shares or the budget left. `qty` under 1 is a stated skip. */
export interface StockModeSize {
  qty: number;
  by_risk: number | null;
  capped_by: 'max_shares' | 'budget' | null;
  text: string | null;
}

/** Nova's automatic buys today on the venue (the bot and Auto-entry share one count); `cap` null when the
 * backend does not say it. */
export interface StockModeEntries {
  count: number;
  cap: number | null;
}

export interface StockModeBot {
  on_list: boolean;
  playing: boolean;
  reason: string | null;
  /** The setup the stock's plan follows is at effective Strategy; null when unknown or no plan. */
  setup_at_strategy: boolean | null;
  /** The bot is Activated; null from a backend that does not say. */
  active: boolean | null;
  /** Legacy: the retired chosen setup (null on a newer backend). */
  setup: string | null;
}

export interface StockModeView {
  symbol: string;
  generated_at: number;
  venue: 'live' | 'paper' | 'sim' | null;
  mode: StockModeName;
  buy: StockSide;
  sell: StockSide;
  /** The venue sleeve's risk per trade (read-only here). */
  risk_usd: number | null;
  set_at: number | null;
  /** Why Nova cannot take each side now; null: it can. `modes` per mode (ADR 052: on a Sim replay only Bot). */
  locks: { buy: string | null; sell: string | null; modes?: Partial<Record<StockModeName, string | null>> };
  notes: StockModeNote[];
  approval: StockModeApproval | null;
  trade: StockModeTrade | null;
  /** Null in Signal only, with no plan, or from a backend that does not size. */
  size: StockModeSize | null;
  /** Null from a backend older than the shared count. */
  entries_today: StockModeEntries | null;
  /** Legacy: this stock's Nova entries today (one release). */
  nova_entries_today: number;
  last_event: { ts: number; tone: 'info' | 'ok' | 'warn' | 'bad'; text: string } | null;
  bot: StockModeBot | null;
}
