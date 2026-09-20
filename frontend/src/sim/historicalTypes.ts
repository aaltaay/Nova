export interface HistoricalWindow { symbol: string; date: string; start: string; end: string }
export interface HistoricalSelection extends HistoricalWindow {
  coverage_through: number;
  trade_count?: number;
  download_status?: string;
  job_id?: string | null;
}
export interface HistoricalJob extends HistoricalWindow {
  id: string; kind: string; status: string; count: number; pages: number; error: string | null;
  cursor?: number; start_ts?: number; end_ts?: number; volume?: number; updated?: number;
  progress_pct?: number; downloaded_through?: number; eta_seconds?: number | null;
  stale?: boolean; age_seconds?: number; started?: number;
}
export interface HistoricalStatus {
  jobs: HistoricalJob[];
  selection?: HistoricalSelection | null;
  default_date?: string;
}
