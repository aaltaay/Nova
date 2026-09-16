export type AdviseStatus = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
export type AdviseStance = 'LONG' | 'SHORT' | 'HOLD';

export interface AdviseTicketPrefill {
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: 'MKT' | 'LMT' | 'STP';
  quantity_value: string;
  limit_price: string;
  places: false;
}

export interface AdviseResult {
  stance: AdviseStance | null;
  reasons: string[];
  risks: string[];
  ticket: AdviseTicketPrefill | null;
}

export interface AdviseEvent {
  type: string;
  ts?: number;
  agent?: string;
  content?: string;
  message?: string;
  stance?: AdviseStance;
  reasons?: string[];
  risks?: string[];
  ticket?: AdviseTicketPrefill | null;
}

export interface AdviseRun {
  id: number;
  symbol: string;
  session_date: string;
  created_ts: number;
  finished_ts: number | null;
  model: string;
  graph_version: number;
  depth: number;
  status: AdviseStatus;
  fail_reason: string | null;
  transcript: AdviseEvent[];
  result: AdviseResult;
  prompt_tokens?: number;
  completion_tokens?: number;
  actual_usd?: number | null;
  from_book?: boolean;
  stale?: boolean;
  stale_nudge?: string | null;
  disclaimer: string;
  places: false;
}

export interface AdviseEstimate {
  symbol: string;
  depth: number;
  model: string;
  model_label: string;
  llm_calls: number;
  est_usd: number;
  est_minutes: number;
  summary: string;
  disclaimer: string;
  note: string;
}
