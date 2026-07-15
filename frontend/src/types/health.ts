/** Shared health payload shape from `/api/health` and scanner endpoints. */
export interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
  feed_fell_back?: boolean;
}
