/**
 * The Congress page's wire (ADR 066; architecture/schema/congress.md). Dates are YYYY-MM-DD, times epoch seconds.
 */

export type Party = 'D' | 'R' | 'I' | string;
export type Chamber = 'senate' | 'house';
export type Period = 'ytd' | '90d' | '30d';
export type Filter = 'all' | 'house' | 'senate' | 'buys' | 'sells' | 'options' | 'late';
export type SourceState = 'off' | 'needs_consent' | 'waiting' | 'reading' | 'ok' | 'failing';

export interface Member {
  bioguide: string;
  name: string;
  party: Party | null;
  caucus: string | null;
  state: string | null;
  district: number | null;
  chamber: Chamber;
  current: boolean;
  left: string | null;
  photo: boolean;
}

export interface Consent {
  state: 'needed' | 'given';
  accepted_at: number | null;
  text: string;
  cite: string;
}

export interface Source {
  id: 'house' | 'senate' | 'roster' | 'photos';
  name: string;
  url: string;
  state: SourceState;
  read_at: number | null;
  next_at: number | null;
  error: string | null;
  done: number;
  todo: number;
  reports?: number;
  electronic?: number;
  paper?: number;
  unread?: number;
  trades?: number;
}

export interface TopTrade {
  ticker: string | null;
  asset: string;
  side: string;
  kind: string;
  gift: boolean;
  amount: string;
  lag_days: number | null;
}

export interface ReportRow {
  id: string;
  chamber: Chamber;
  member: Member | null;
  filer: string | null;
  filed: string;
  kind: 'electronic' | 'paper';
  read: boolean;
  url: string;
  amends: string | null;
  trades: number;
  top: TopTrade | null;
}

export interface Traded {
  ticker: string;
  asset: string;
  members: number;
  buyers: string[];
  sellers: string[];
  buys: number;
  sells: number;
}

export interface Weeks {
  from: string;
  buy: number[];
  sell: number[];
}

export interface Active extends Member {
  trades: number;
  buys: number;
  sells: number;
  median_lag_days: number | null;
  late: number;
  weeks: Weeks;
  top: string[];
}

export interface Lag {
  bucket_days: number;
  buckets: number[];
  median_days: number | null;
  within_week_pct: number | null;
  after_limit_pct: number | null;
  limit_days: number;
  trades: number;
}

export interface Seats {
  senate: Member[];
  house: Member[];
  delegates: Member[];
  former: Member[];
  empty: { senate: number; house: number };
}

export interface Board {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  today: string;
  year: number;
  consent: Consent;
  sources: Source[];
  counts: Record<Filter, number>;
  periods: Record<Period, { from: string }>;
  seats: Seats;
  reported: Record<Period, Record<string, 'trades' | 'paper'>>;
  just_reported: ReportRow[];
  most_traded: Record<Period, Traded[]>;
  most_active: Active[];
  lag: Lag;
}

export interface MemberStats extends Member {
  committees: string[];
  ytd: { trades: number; buys: number; sells: number; reports: number; paper: number };
  last_filed: string | null;
  median_lag_days: number | null;
  late: number;
}

export interface Trade {
  id: string;
  report: string;
  chamber: Chamber;
  bioguide: string | null;
  filer: string;
  filed: string;
  tx: string;
  notified: string | null;
  lag_days: number | null;
  late: boolean;
  owner: 'self' | 'spouse' | 'joint' | 'child';
  ticker: string | null;
  asset: string;
  asset_type: string | null;
  kind: 'stock' | 'option' | 'other';
  side: 'buy' | 'sell' | 'exchange' | 'other';
  partial: boolean;
  gift: boolean;
  amount: { text: string; low: number | null; high: number | null };
  description: string;
  status: string | null;
  url: string;
  member?: Member | null;
}

export interface MemberReport {
  id: string;
  chamber: Chamber;
  filed: string;
  kind: 'electronic' | 'paper';
  read: boolean;
  error: string | null;
  url: string;
  amends: string | null;
  amended_by: string | null;
  trades: number;
}

export interface MembersAnswer {
  schema_version: number;
  generated_at: number;
  year: number;
  members: MemberStats[];
}

export interface MemberAnswer {
  schema_version: number;
  generated_at: number;
  member: MemberStats;
  weeks: Weeks;
  trades: Trade[];
  reports: MemberReport[];
}

export interface TickerAnswer {
  schema_version: number;
  generated_at: number;
  ticker: string;
  asset: string | null;
  buyers: string[];
  sellers: string[];
  trades: Trade[];
}

/** What the page shows below its tabs. */
export type View =
  | { kind: 'trades' }
  | { kind: 'members' }
  | { kind: 'following' }
  | { kind: 'member'; bioguide: string }
  | { kind: 'ticker'; ticker: string };
