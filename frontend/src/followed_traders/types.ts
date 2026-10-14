/** `GET /api/followed-traders/day` (architecture/schema/followed-traders.md). Times are epoch seconds. */

export type FeedState = 'ok' | 'unreachable' | 'bad_answer';
export type PricesState = 'live' | 'past_day' | 'replay_desk' | 'ibkr_down' | 'not_asked';
export type NowState = 'live' | 'waiting' | 'no_trade' | 'no_line' | 'off';
export type ExitState = 'pending' | 'at' | 'range' | 'unavailable';

export interface FollowedNow {
  state: NowState;
  price: number | null;
  trade_ts: number | null;
  why: string | null;
}

export interface FollowedExit {
  state: ExitState;
  price: number | null;
  low: number | null;
  high: number | null;
  from_ts: number | null;
  to_ts: number | null;
  trade_ts: number | null;
  source: 'ibkr_trades' | 'ibkr_1min_bars' | null;
  why: string | null;
}

export interface PointPl {
  per_share: number;
  pct: number;
}

export interface RangePl {
  low_per_share: number;
  high_per_share: number;
  low_pct: number;
  high_pct: number;
}

export type TradeResult = 'win' | 'loss' | 'scratch' | 'unscored';

export interface FollowedRecord {
  wins: number;
  losses: number;
  scratches: number;
  unscored: number;
  open: number;
  /** Wins over wins plus losses, percent points; null with neither. */
  win_rate: number | null;
}

export interface FollowedTrade {
  id: string;
  trader: string;
  side: 'long' | 'short';
  symbol: string;
  status: 'open' | 'closed' | 'unknown';
  entry: { first_price: number; avg_price: number; ts: number; since_ts: number | null; known: boolean };
  adds: { ts: number; price: number; prev_price: number | null }[];
  now: FollowedNow | null;
  exit: FollowedExit | null;
  pl: PointPl | RangePl | null;
  held: { min_sec: number | null; max_sec: number | null };
  /** Null while open. */
  result: TradeResult | null;
  evidence: { entry: string | null; exit: string | null };
}

export interface FollowedTrader {
  name: string;
  /** This API's path to the trader's photo that day; null when the feed has none. */
  face: string | null;
  record: FollowedRecord;
  open: FollowedTrade[];
  closed: FollowedTrade[];
}

export interface FollowedCapture {
  live: boolean;
  clock: string | null;
  updated_at: number | null;
  age_sec: number | null;
  bar_visible: boolean;
  title: string | null;
  /** The stream the feed reads: a YouTube video id, or null when it names none (an older backend sends no field). */
  video_id?: string | null;
  traders: string[];
  /** The feed's own reason it cannot read, shown as it is. */
  problem: string | null;
  problem_at: number | null;
  /** Each trader's bar as the feed last confirmed it; null when the feed does not report it. */
  bar: FollowedBarSlot[] | null;
}

export interface BarPosition {
  side: 'long' | 'short';
  symbol: string;
  price: number;
}

export interface FollowedBarSlot {
  trader: string;
  positions: BarPosition[];
  /** This API's path to the trader's slot as last seen; null when the feed names none. */
  image: string | null;
  /** This API's path to the trader's photo on the feed's today; null without one (absent from an older backend). */
  face?: string | null;
}

export interface FollowedDay {
  schema_version: number;
  generated_at: number;
  feed: { state: FeedState; error: string | null };
  date: string | null;
  /** The desk's trading day, turning at 04:00 ET like the rest of the desk; null while the feed is down. */
  today: string | null;
  /** When today ends (the next 04:00 ET), epoch seconds; null while the feed is down (absent from an older backend). */
  resets_at?: number | null;
  dates: string[];
  capture: FollowedCapture | null;
  prices: { state: PricesState; why: string | null } | null;
  overall: FollowedRecord | null;
  traders: FollowedTrader[];
}

export type RecordRange = 'day' | 'week' | 'all';

/** `GET /api/followed-traders/record`. */
export interface FollowedRecords {
  schema_version: number;
  generated_at: number;
  feed: { state: FeedState; error: string | null };
  range: RecordRange;
  from: string | null;
  to: string | null;
  dates: string[];
  pending: number;
  overall: FollowedRecord | null;
  traders: { name: string; record: FollowedRecord }[];
}

export interface FollowedRead {
  ts: number;
  until_ts: number | null;
  /** False: the name was not read on that frame (the bar off screen, or the tag read as another name). */
  seen: boolean;
  positions: BarPosition[];
  unparsed: string[];
}

/** `GET /api/followed-traders/reads`. */
export interface FollowedReads {
  schema_version: number;
  generated_at: number;
  feed: { state: FeedState; error: string | null };
  date: string;
  trader: string;
  available: boolean;
  why: string | null;
  reads: FollowedRead[];
  truncated: boolean;
}
