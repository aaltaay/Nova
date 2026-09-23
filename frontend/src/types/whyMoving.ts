/** `GET /api/why/{symbol}` (ADR 028; AGENTS.md §3 "Why it's moving"): a rules read of what drove a mover. */

export type WhyCheckState = 'yes' | 'no' | 'unknown';

export interface WhyCheck {
  /** news | halts | float | float_rotation | reverse_split | short_interest | borrow | volume */
  id: string;
  label: string;
  state: WhyCheckState;
  value: string | null;
  detail: string | null;
  source: string;
  /** Epoch seconds the fact is as of, when known. */
  as_of: number | null;
}

export interface WhyLikely {
  /** not_moving | news_pending | news | short_squeeze | routine_news | split_squeeze | low_float_momentum | thin_trading | unexplained */
  kind: string;
  label: string;
  detail: string | null;
  /** `possible` when a deciding fact is unknown. */
  confidence: 'likely' | 'possible';
}

export interface WhyMovingRead {
  schema_version: number;
  symbol: string;
  generated_at: number;
  rules_version: string;
  likely: WhyLikely;
  checks: WhyCheck[];
}
