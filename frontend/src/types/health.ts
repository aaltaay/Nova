/** Shared health payload shape from `/api/health` and scanner endpoints. */
export interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
  feed_fell_back?: boolean;
  /**
   * Client-side outage flag when disconnected (stable for UI + console grep).
   * Examples: API_DOWN, API_WEDGED, API_HTTP, API_UNREACHABLE.
   */
  flag?: string;
  /** Remediation one-liner for the active flag (tooltip). */
  flag_hint?: string;
}
