/** One auxiliary integration chip from `/api/health` → integrations. */
export interface IntegrationChipStatus {
  status: 'ok' | 'off' | 'error' | 'unknown' | string;
  detail?: string;
}

/** Shared health payload shape from `/api/health` and scanner endpoints. */
export interface HealthStatus {
  status: string;
  latency_ms: number;
  /** Probe that owns the top-level health status (currently Alpaca account API). */
  health_source?: string;
  /** Source of latency_ms; omit the RTT in UI when absent or unrecognized. */
  latency_source?: string;
  /** Explicit market-data owner; independent from health/latency probes. */
  market_data_source?: string;
  message?: string;
  feed_fell_back?: boolean;
  /**
   * Client-side outage flag when disconnected (stable for UI + console grep).
   * Examples: API_DOWN, API_WEDGED, API_HTTP, API_UNREACHABLE.
   */
  flag?: string;
  /** Remediation one-liner for the active flag (tooltip). */
  flag_hint?: string;
  /** Aux APIs (Alpaca news/meta, OpenAI/Lincoln, yfinance, archive) — not price feed. */
  integrations?: Record<string, IntegrationChipStatus>;
  /** Process identity — lets restart tooling prove a NEW process answered. */
  instance_id?: string;
  pid?: number;
  parent_pid?: number;
  started_at?: number;
  reload?: boolean;
  /** Event-loop lag sample (backend/loop_lag.py). */
  loop_lag_ms?: { last_ms: number; max_ms: number; samples: number };
}
